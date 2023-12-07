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
    # work around probably SQLModel bug during select
    # AttributeError: 'ConfigTable' object has no attribute '__pydantic_extra__'. Did you mean: '__pydantic_private__'?
    __pydantic_extra__ = None
    __table_args__ = (UniqueConstraint("config_type", "config_name"), )
    __tablename__ = "willow_config"

    id: Optional[int] = Field(default=None, primary_key=True)
    config_type: WillowConfigType
    config_name: str
    config_namespace: Optional[WillowConfigNamespaceType] = None
    config_value: Optional[str] = None


class WillowClientTable(SQLModel, table=True):
    __tablename__ = "willow_clients"

    id: Optional[int] = Field(default=None, primary_key=True)
    mac_addr: str = Field(unique=True)
    label: str
