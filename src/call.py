"""
Call launcher (CLI).

This is what YOU run. It tells Twilio to place an outbound call from your Twilio
number to a target number, and to record the whole thing. When the call connects,
Twilio fetches our /incoming-call TwiML which wires up the live audio bridge.

Usage:
    python -m src.call --scenario 01_schedule_simple --to +18054398008
    python -m src.call --list
    python -m src.call --to +1YOURCELL --scenario 01_schedule_simple   # self-test

IMPORTANT: For real submission calls, --to must be the assessment number
(+1-805-439-8008). For your own testing, point --to at your own cell phone first.
"""
import argparse
import sys
import time

from twilio.rest import Client

from .config import Config
from .scenarios import SCENARIOS, get_scenario

ASSESSMENT_NUMBER = "+18054398008"


def list_scenarios():
    print("\nAvailable scenarios:\n")
    for s in SCENARIOS:
        print(f"  {s.id:<28} {s.title}")
    print()


def place_call(to_number: str, scenario_id: str) -> str:
    config = Config.load()
    scenario = get_scenario(scenario_id)  # validates id early
    client = Client(config.twilio_account_sid, config.twilio_auth_token)

    # Twilio will GET this URL when the call answers. Scenario passed via query.
    twiml_url = f"{config.public_url}/incoming-call?scenario={scenario_id}"

    print(f"\nPlacing call:")
    print(f"  scenario : {scenario_id}  ({scenario.title})")
    print(f"  from     : {config.twilio_from_number}")
    print(f"  to       : {to_number}")
    if to_number == ASSESSMENT_NUMBER:
        print("  >> This is a REAL assessment call. It will be recorded.")
    else:
        print("  >> Test call (not the assessment number).")

    call = client.calls.create(
        to=to_number,
        from_=config.twilio_from_number,
        url=twiml_url,
        record=True,                      # records both legs -> fetchable as mp3
        recording_channels="dual",        # separate channels for each side
    )
    print(f"\nCall initiated. SID: {call.sid}")
    print("Watch the bridge server logs for live transcript + status.")
    print("After the call ends, run:  python -m src.fetch_recordings\n")
    return call.sid


def main():
    parser = argparse.ArgumentParser(description="Patient voice bot call launcher")
    parser.add_argument("--scenario", default="01_schedule_simple",
                        help="Scenario id (see --list)")
    parser.add_argument("--to", default=ASSESSMENT_NUMBER,
                        help="Destination number in E.164. Use your own cell for testing.")
    parser.add_argument("--list", action="store_true", help="List scenarios and exit")
    parser.add_argument("--all", action="store_true",
                        help="Run every scenario in sequence (spacing between calls)")
    parser.add_argument("--gap", type=int, default=20,
                        help="Seconds to wait between calls when using --all")
    args = parser.parse_args()

    if args.list:
        list_scenarios()
        return

    if args.all:
        for s in SCENARIOS:
            place_call(args.to, s.id)
            print(f"Waiting {args.gap}s before next call...")
            time.sleep(args.gap)
        return

    place_call(args.to, args.scenario)


if __name__ == "__main__":
    sys.exit(main())
