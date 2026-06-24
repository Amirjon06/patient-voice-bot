# Architecture

**How it works.** The bot makes a real outbound phone call through Twilio from a single
caller number. When the call connects, Twilio requests TwiML from this app's
`/incoming-call` endpoint, which opens a bidirectional **media stream** (a websocket) back
to the bridge server. From that point the server has the live phone audio in both
directions as 8kHz G.711 µ-law frames. It forwards the inbound audio (the office agent's
voice) to the **OpenAI Realtime API**, which is configured with a "patient" persona and a
concrete goal for the call. The Realtime model "hears" the agent and streams spoken audio
back, which the bridge relays down to Twilio so the agent hears the patient. The result is
a genuine, low-latency two-way voice conversation rather than a record-then-respond loop.

**Key design choices.** I used the Realtime API end-to-end (speech-in, speech-out in one
model) instead of stitching together separate STT → LLM → TTS services, because chaining
those adds latency and seams at exactly the points the challenge grades hardest: natural
pacing and turn-taking. Turn-taking and barge-in are delegated to the Realtime API's
**server-side voice-activity detection** — when the agent speaks, the patient listens; when
the caller starts talking over a response, the bridge sends a `clear` to Twilio so the two
voices don't overlap. Scenarios are **prompts, not scripts**: each is a persona plus a goal,
so the bot improvises like a real caller and actively steers toward an outcome (book, refill,
cancel, etc.) instead of reading fixed lines — which is explicitly what the brief asks for.
Recording uses Twilio's dual-channel recording so each side is cleanly separated in the mp3,
while transcripts are built from the Realtime transcription events. Because the two
transcription streams (the bot's own speech and the agent's Whisper-transcribed audio)
arrive with different latencies, turns are ordered by a timestamp captured when each
speaker *starts* talking rather than when its transcription arrives, which keeps the
written record in true conversational order. Secrets live only in
`.env` (with a committed `.env.example`), and the whole thing is two small runnable modules —
a server and a CLI — to stay easy to read and operate rather than over-engineered.
