"""
The bridge server.

Twilio places the call and opens a websocket to us, streaming the live phone audio
as base64 G.711 u-law (8kHz) frames. We forward those frames to OpenAI's Realtime
API, which "hears" the office agent and speaks back as the patient. OpenAI's audio
comes back to us, and we relay it down to Twilio so the agent hears the patient.

Turn-taking / barge-in is handled by OpenAI's server-side voice-activity detection
(server VAD): it decides when the patient should start/stop talking based on the
incoming audio, which gives natural, human-like turns without us hand-rolling it.

We also capture every transcript event (both the agent's speech, transcribed, and
the patient's own speech) and write a clean turn-by-turn transcript per call.
"""
import asyncio
import base64
import json
import time
import os
from datetime import datetime

import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect

from twilio.rest import Client
from .config import Config
from .scenarios import get_scenario, build_instructions

config = Config.load()
app = FastAPI()

# Realtime config: which model events we care about logging.
OPENAI_WS_URL = f"wss://api.openai.com/v1/realtime?model={config.realtime_model}"

# In-memory store of transcript turns keyed by Twilio call SID, flushed to disk on hangup.
_transcripts: dict[str, list[dict]] = {}
_scenario_for_call: dict[str, str] = {}
_seq_counter: dict[str, int] = {}
_agent_speech_start: dict[str, float] = {}  # call_sid -> ts when agent last started speaking


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    """
    Twilio hits this when the outbound call connects. We return TwiML that tells
    Twilio to open a bidirectional media stream to our /media-stream websocket.
    The scenario id is passed through as a query param so the right persona loads.
    """
    scenario_id = request.query_params.get("scenario", "01_schedule_simple")
    ws_url = config.public_url.replace("https://", "wss://").replace("http://", "ws://")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}/media-stream">
      <Parameter name="scenario" value="{scenario_id}" />
    </Stream>
  </Connect>
</Response>"""
    return HTMLResponse(content=twiml, media_type="application/xml")


@app.websocket("/media-stream")
async def media_stream(twilio_ws: WebSocket):
    """Bidirectional bridge between one Twilio call and one OpenAI realtime session."""
    await twilio_ws.accept()
    print("[bridge] Twilio media stream connected")

    call_sid: str | None = None
    stream_sid: str | None = None
    scenario_id = "01_schedule_simple"

    async with websockets.connect(
        OPENAI_WS_URL,
        extra_headers={
            "Authorization": f"Bearer {config.openai_api_key}",
        },
    ) as openai_ws:

        async def init_openai_session(sid: str):
            scenario = get_scenario(sid)
            session_update = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": config.realtime_model,
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcmu"},
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 600,
                            },
                            "transcription": {"model": "whisper-1"},
                        },
                        "output": {
                            "format": {"type": "audio/pcmu"},
                            "voice": config.voice,
                            "speed": 0.95,
                        },
                    },
                    "instructions": build_instructions(scenario),
                },
            }
            await openai_ws.send(json.dumps(session_update))
            await openai_ws.send(json.dumps({"type": "response.create"}))
            print(f"[bridge] OpenAI session initialized for scenario '{sid}'")

        # ---- Twilio -> OpenAI ----
        async def twilio_to_openai():
            nonlocal call_sid, stream_sid, scenario_id
            try:
                async for message in twilio_ws.iter_text():
                    data = json.loads(message)
                    event = data.get("event")

                    if event == "start":
                        stream_sid = data["start"]["streamSid"]
                        call_sid = data["start"]["callSid"]
                        params = data["start"].get("customParameters", {})
                        scenario_id = params.get("scenario", "01_schedule_simple")
                        _transcripts.setdefault(call_sid, [])
                        _scenario_for_call[call_sid] = scenario_id
                        print(f"[bridge] Call started sid={call_sid} scenario={scenario_id}")
                        await init_openai_session(scenario_id)

                    elif event == "media":
                        # Forward caller audio to OpenAI's input buffer.
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }))

                    elif event == "stop":
                        print("[bridge] Twilio stream stopped")
                        break
            except WebSocketDisconnect:
                print("[bridge] Twilio disconnected")
            finally:
                if call_sid:
                    _flush_transcript(call_sid)

        # ---- Idle / silence watcher ----
        # If the office side stays quiet too long after speaking, the patient
        # checks in like a real caller ("hello? you still there?").
        idle_task = {"t": None}

        async def _idle_then_checkin():
            try:
                await asyncio.sleep(12.0)
                print("[bridge] Silence detected - patient checking in")
                await openai_ws.send(json.dumps({
                    "type": "response.create",
                    "response": {
                        "instructions": (
                            "There has been a long silence. Check if the other "
                            "person is still there, like a real caller would: "
                            "say something brief like 'Hello? Are you still there?' "
                            "or 'Sorry, can you still hear me?'"
                        ),
                    },
                }))
            except asyncio.CancelledError:
                pass

        def arm_idle():
            cancel_idle()
            idle_task["t"] = asyncio.create_task(_idle_then_checkin())

        def cancel_idle():
            if idle_task["t"] and not idle_task["t"].done():
                idle_task["t"].cancel()
            idle_task["t"] = None

        # ---- OpenAI -> Twilio ----
        async def openai_to_twilio():
            nonlocal call_sid
            try:
                async for raw in openai_ws:
                    evt = json.loads(raw)
                    etype = evt.get("type")
                    if etype and "delta" not in etype:
                        print(f"[openai-event] {etype}")

                    # Patient (our bot) audio -> down to Twilio so the agent hears it.
                    if etype in ("response.audio.delta", "response.output_audio.delta") and stream_sid:
                        await twilio_ws.send_text(json.dumps({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": evt["delta"]},
                        }))

                    # Patient's own words (what our bot said).
                    elif etype in ("response.audio_transcript.done", "response.output_audio_transcript.done"):
                        said = evt.get("transcript", "").strip()
                        if call_sid:
                            _transcripts[call_sid].append({
                                "speaker": "patient_bot",
                                "text": said,
                                "ts": time.time(),
                            })
                        # If the patient said goodbye, hang up like a real caller would.
                        low = said.lower()
                        if call_sid and any(w in low for w in ("bye", "goodbye", "see you", "take care")):
                            async def _end_call(sid=call_sid):
                                await asyncio.sleep(1.8)  # let the audio finish playing
                                try:
                                    Client(config.twilio_account_sid,
                                           config.twilio_auth_token).calls(sid).update(status="completed")
                                    print(f"[bridge] Auto hung up call {sid} after goodbye")
                                except Exception as e:
                                    print(f"[bridge] hangup failed: {e}")
                            asyncio.create_task(_end_call())

                    # The office agent's speech, transcribed by Whisper.
                    elif etype == "conversation.item.input_audio_transcription.completed":
                        if call_sid:
                            _transcripts[call_sid].append({
                                "speaker": "office_agent",
                                "text": evt.get("transcript", "").strip(),
                                "ts": _agent_speech_start.get(call_sid, time.time()),
                            })

                    # When the caller starts talking, cancel any in-progress bot speech
                    # so we get clean barge-in instead of two voices overlapping.
                    elif etype == "input_audio_buffer.speech_started" and stream_sid:
                        if call_sid:
                            _agent_speech_start[call_sid] = time.time()
                        await twilio_ws.send_text(json.dumps({
                            "event": "clear",
                            "streamSid": stream_sid,
                        }))



                    elif etype == "error":
                        print(f"[bridge] OpenAI error: {evt.get('error')}")
            except websockets.exceptions.ConnectionClosed:
                print("[bridge] OpenAI connection closed")

        await asyncio.gather(twilio_to_openai(), openai_to_twilio())


def _next_seq(call_sid: str) -> int:
    n = _seq_counter.get(call_sid, 0)
    _seq_counter[call_sid] = n + 1
    return n


def _flush_transcript(call_sid: str):
    """Write the collected turns to transcripts/<scenario>_<callsid>.txt"""
    turns = _transcripts.get(call_sid, [])
    if not turns:
        return
    scenario_id = _scenario_for_call.get(call_sid, "unknown")
    os.makedirs("transcripts", exist_ok=True)
    path = f"transcripts/{scenario_id}_{call_sid}.txt"

    # Sort by timestamp so turns read in order regardless of event arrival.
    turns_sorted = sorted(turns, key=lambda t: t.get("ts", 0))
    with open(path, "w") as f:
        f.write(f"Scenario: {scenario_id}\nCall SID: {call_sid}\n")
        f.write(f"Generated: {datetime.utcnow().isoformat()}Z\n")
        f.write("=" * 60 + "\n\n")
        for t in turns_sorted:
            label = "PATIENT (bot)" if t["speaker"] == "patient_bot" else "OFFICE AGENT"
            f.write(f"{label}: {t['text']}\n\n")
    print(f"[bridge] Transcript written -> {path}")
