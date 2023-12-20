from typing import Optional

from pydantic import BaseModel


class SrModel(BaseModel):
    friendly_name: Optional[str] = None
    name: str = None
    url: str = None
