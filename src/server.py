"""
Server entrypoint. Runs the FastAPI bridge that Twilio streams audio to.

Run this in one terminal (it must stay up while you place calls):
    python -m src.server

Then place calls from a second terminal with:  python -m src.call ...
"""
import uvicorn
from .config import Config

if __name__ == "__main__":
    config = Config.load()
    print(f"Bridge server starting on port {config.port}")
    print(f"Twilio should reach this at: {config.public_url}")
    uvicorn.run("src.bridge:app", host="0.0.0.0", port=config.port, log_level="info")
