from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class WillowConfigNamespaceType(str, Enum):
    WAS = "WAS"
    WIFI = "WIFI"


class WillowConfigType(str, Enum):
    config = "config"
    multinet = "multinet"
    nvs = "nvs"


class WillowConfigTable(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("config_type", "config_name"), )
    __tablename__ = "willow_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    config_type: WillowConfigType
    config_name: str
    config_namespace: Optional[WillowConfigNamespaceType] = None
    config_value: Optional[str] = None
