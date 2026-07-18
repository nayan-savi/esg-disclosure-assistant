import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from dotenv import load_dotenv

# Resolve the path to the backend/.env file and load it
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
env_path = os.path.join(backend_dir, ".env")
load_dotenv(dotenv_path=env_path)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore"
    )

    OPENAI_API_KEY: Optional[str] = None

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DATABASE_URL: Optional[str] = None

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            # Ensure it uses postgresql+psycopg
            url = self.DATABASE_URL
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

settings = Settings()
