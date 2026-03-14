"""Application configuration loaded from environment variables.

ADK uses these environment variables automatically (no code changes dev vs prod):
  GOOGLE_GENAI_USE_VERTEXAI — "FALSE" for dev (Google AI Studio), "TRUE" for prod (Vertex AI)
  GOOGLE_API_KEY — API key for Google AI Studio (dev mode)
  GOOGLE_CLOUD_PROJECT — GCP project ID (prod mode)
  GOOGLE_CLOUD_LOCATION — GCP region e.g. us-central1 (prod mode)
"""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve .env from project root (matches docker-compose which uses root .env)
_env_path = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ADK / Gemini (model for live streaming; API key via GOOGLE_API_KEY for ADK)
    agent_model: str = "gemini-2.0-flash-live-001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"

    # External services
    click_agent_url: str = "http://localhost:8001"
    extension_ws_path: str = "/ws/extension"

    # Audio
    send_sample_rate: int = 16000
    receive_sample_rate: int = 24000

    # Screen capture
    frame_rate: int = 1
    frame_size: int = 768

    # Server
    host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 3000

    class Config:
        env_file = str(_env_path) if _env_path.exists() else ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
