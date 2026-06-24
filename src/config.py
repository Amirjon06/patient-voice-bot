"""
Central configuration. All secrets come from environment variables (.env).
Nothing sensitive is hard-coded here.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


@dataclass
class Config:
    # --- Twilio (telephony) ---
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str          # YOUR Twilio number (the single caller number)

    # --- OpenAI (the "patient" brain + voice) ---
    openai_api_key: str
    realtime_model: str
    voice: str                       # OpenAI realtime voice name

    # --- Public URL of THIS server (where Twilio streams audio to) ---
    # During local testing this is your ngrok https URL.
    public_url: str

    # --- Server ---
    port: int

    @classmethod
    def load(cls) -> "Config":
        return cls(
            twilio_account_sid=_require("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=_require("TWILIO_AUTH_TOKEN"),
            twilio_from_number=_require("TWILIO_FROM_NUMBER"),
            openai_api_key=_require("OPENAI_API_KEY"),
            realtime_model=os.getenv("REALTIME_MODEL", "gpt-4o-realtime-preview-2024-12-17"),
            voice=os.getenv("REALTIME_VOICE", "alloy"),
            public_url=_require("PUBLIC_URL").rstrip("/"),
            port=int(os.getenv("PORT", "5050")),
        )
