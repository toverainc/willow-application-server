from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    was_version: str = "unknown"


@lru_cache
def get_settings():
    return Settings()
