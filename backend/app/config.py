from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "ai-rental-agent"
    jwt_audience: str = "ai-rental-agent-api"
    access_token_minutes: int = Field(default=30, ge=1, le=120)
    upload_dir: str = "backend/uploads"
    max_image_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    max_image_pixels: int = Field(default=20_000_000, ge=1, le=40_000_000)
    max_property_images: int = Field(default=30, ge=1, le=100)
    auth_rate_limit: int = Field(default=20, ge=1, le=1000)
    openai_api_key: SecretStr | None = None
    openai_model: str = Field(default="gpt-5.4-mini", min_length=1, max_length=100)
    assistant_enabled: bool = True
    assistant_timeout_seconds: int = Field(default=60, ge=5, le=120)
    assistant_max_turns: int = Field(default=6, ge=2, le=10)
    assistant_rate_limit: int = Field(default=10, ge=1, le=100)

    def assistant_available(self) -> bool:
        key = self.openai_api_key.get_secret_value().strip() if self.openai_api_key else ""
        return self.assistant_enabled and bool(key) and not key.startswith("replace-")

    def signing_key(self) -> str:
        value = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
        if len(value.encode("utf-8")) < 32 or value.startswith("replace-"):
            raise ValueError("JWT_SECRET must be a randomly generated secret of at least 32 bytes")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
