"""
Recording fetcher.

Twilio stores call recordings server-side. This pulls them down as mp3 into
recordings/, named to match the scenario + call SID so they line up with the
transcripts in transcripts/.

Usage:
    python -m src.fetch_recordings              # fetch all recordings
    python -m src.fetch_recordings --sid CAxxxx # fetch one call's recording
"""
import argparse
import os

import requests
from twilio.rest import Client

from .config import Config


def fetch(target_sid: str | None = None):
    config = Config.load()
    client = Client(config.twilio_account_sid, config.twilio_auth_token)
    os.makedirs("recordings", exist_ok=True)

    recordings = client.recordings.list(limit=200)
    if not recordings:
        print("No recordings found on this Twilio account yet.")
        return

    count = 0
    for rec in recordings:
        if target_sid and rec.call_sid != target_sid:
            continue

        # mp3 is fetched by appending .mp3 to the recording media URI.
        media_url = (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{config.twilio_account_sid}/Recordings/{rec.sid}.mp3"
        )
        resp = requests.get(
            media_url,
            auth=(config.twilio_account_sid, config.twilio_auth_token),
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"  ! Failed to fetch {rec.sid} (HTTP {resp.status_code})")
            continue

        out_path = f"recordings/call_{rec.call_sid}.mp3"
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"  saved {out_path}  ({rec.duration}s)")
        count += 1

    print(f"\nDone. {count} recording(s) saved to recordings/")
    if not count and target_sid:
        print(f"(No recording matched call SID {target_sid} — it may still be processing.)")


def main():
    parser = argparse.ArgumentParser(description="Fetch Twilio call recordings as mp3")
    parser.add_argument("--sid", help="Only fetch recording for this call SID")
    args = parser.parse_args()
    fetch(args.sid)


if __name__ == "__main__":
    main()
