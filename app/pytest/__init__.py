from os import makedirs

import pytest


@pytest.fixture(scope="session", autouse=True)
def pre():
    makedirs("/app/static/admin", exist_ok=True)
