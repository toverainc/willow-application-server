import json

from pathlib import Path

from app.internal.config import WillowConfig


def test_config():
    default_config_path = Path("default_config.json")
    default_config = default_config_path.read_text()
    default_config_dict = json.loads(default_config)

    config = WillowConfig.model_validate(default_config_dict)

    assert config.model_dump(exclude_none=True) == default_config_dict
