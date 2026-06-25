# Patient Voice Bot — AI Engineering Challenge

An automated voice bot that **calls a medical-office AI agent and role-plays as a patient**.
It holds a natural spoken conversation, records both sides, transcribes them turn-by-turn,
and produces the material to find bugs in the agent's behavior.

It is built on **Twilio** (telephony) + the **OpenAI Realtime API** (the patient's brain
and voice). Twilio places the call and streams live audio over a websocket to a small local
server; that server bridges the audio to the Realtime API, which listens to the office agent
and speaks back as the patient in real time. Server-side voice-activity detection handles
natural turn-taking and barge-in.

The 10 final calls (audio + transcripts) used for this submission live in **`submission/`**.

---

## What you need

1. **A Twilio account** with a voice-capable phone number (your single caller number).
2. **An OpenAI API key** with Realtime API access.
3. **ngrok** (or any tunnel) so Twilio can reach your local server during testing.
4. **Python 3.10+**

---

## Setup (one time)

```bash
# 1. Clone and enter
git clone <your-repo-url> && cd patient-voice-bot

# 2. Create a virtualenv and install deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure secrets
cp .env.example .env
#   then edit .env and fill in your Twilio + OpenAI values

# 4. Start a tunnel so Twilio can reach your machine
ngrok http 5050
#   copy the https URL it prints into PUBLIC_URL in your .env
```

---

## Run

You need **two terminals**.

**Terminal 1 — start the bridge server (leave it running):**
```bash
python -m src.server
```

**Terminal 2 — place a call:**
```bash
# List all scenarios
python -m src.call --list

# Self-test FIRST: call your own phone and talk to the bot
python -m src.call --to +1YOURCELL --scenario 01_schedule_new

# Real assessment call
python -m src.call --to +18054398008 --scenario 01_schedule_new
```

**After calls finish, pull the audio:**
```bash
python -m src.fetch_recordings
```

Transcripts land in `transcripts/`, recordings (mp3) in `recordings/`.

---

## Scenarios

Ten distinct patient scenarios, each a persona with a goal (prompts, not scripts — the bot
improvises and steers toward its outcome like a real caller):

| ID | Scenario |
|----|----------|
| 01_schedule_new        | New-patient appointment scheduling |
| 02_reschedule          | Reschedule an existing appointment |
| 03_cancel              | Cancel an appointment (unsure of date) |
| 04_refill              | Medication refill request |
| 05_hours_location      | Office hours + parking question |
| 06_insurance           | Insurance coverage / copay question |
| 07_weekend_trap        | Edge case: insists on a closed-Sunday slot |
| 08_test_results        | Asking for lab results over the phone |
| 09_referral_billing    | Referral request + a billing question |
| 10_hard_name_interrupt | Edge case: hard-to-spell name + interruptions |

---

## Recommended workflow

1. **Test against your own cell phone first** until the conversation feels lucid and the
   pacing is natural. Don't record real calls until the bot sounds good.
2. Once it's solid, point it at the assessment number and bank your 10+ calls.
3. Review transcripts + recordings, log issues in `BUG_REPORT.md`.

> **Audio format:** Twilio recordings download as `.mp3`, which the brief accepts. For
> `.ogg`, convert with `ffmpeg -i in.mp3 out.ogg`.

---

## Project layout

```
src/
  config.py            env/secrets loading
  scenarios.py         the 10 patient personas + goals
  bridge.py            Twilio <-> OpenAI Realtime audio bridge (FastAPI)
  server.py            runs the bridge
  call.py              CLI to place outbound calls
  fetch_recordings.py  downloads call recordings as mp3
submission/
  recordings/          the 10 final call recordings (mp3)
  transcripts/         the 10 final transcripts
ARCHITECTURE.md        how it works + design choices
BUG_REPORT.md          issues found in the agent
```