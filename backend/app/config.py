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
    auth_rate_limit: int = Field(default=20, ge=1, le=1000)

    def signing_key(self) -> str:
        value = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
        if len(value.encode("utf-8")) < 32 or value.startswith("replace-"):
            raise ValueError("JWT_SECRET must be a randomly generated secret of at least 32 bytes")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
