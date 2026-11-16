from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    internal_api_key: str = "prod-internal-secret-key-9988"

    external_a2a_endpoint: str = "http://localhost:9000/.well-known/agent-card.json"
    external_a2a_token: str = "a2a-shared-bearer-token-7766"
    external_a2a_timeout: int = 90

    model_config = SettingsConfigDict(
        env_file=(".env", str(ROOT_ENV)),
        extra="ignore",
    )

settings = Settings()