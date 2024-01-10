from functools import lru_cache

from pydantic_settings import BaseSettings

from app.const import DB_URL


class Settings(BaseSettings):
    db_url: str = DB_URL
    was_version: str = "unknown"


@lru_cache
def get_settings():
    return Settings()
