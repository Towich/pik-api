from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения, читаемая из переменных окружения."""

    telegram_token: str
    telegram_chat_id: str

    pik_base_url: str = "https://api.pik.ru"
    yauza_block_id: int = 1220

    database_path: str = "pik_yauza.db"

    summary_interval_seconds: int = 3600  # 1 час

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton-доступ к настройкам."""

    return Settings() 