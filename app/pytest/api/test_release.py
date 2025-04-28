import json
import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.pytest.mock import mock_releases_willow


client = TestClient(app)


mock_releases_was = [{
    "name": "0.0.0-mock.0",
    "tag_name": "0.0.0-mock.0",
    "assets": [
        {
            "browser_download_url": "bogus",
            "platform": "ESP32-S3-BOX-3",
            "was_url": "http://was.local/api/ota?version=0.0.0-mock.0&platform=ESP32-S3-BOX-3",
            "cached": True
        }
    ]
}]


class TestRelease(unittest.TestCase):
    def test_get_release(self):
        with patch("app.routers.release.get_was_url", return_value=None):
            response = client.get("/api/release?type=was")

            assert response.status_code == 500

        with patch("app.routers.release.get_releases_willow", return_value=mock_releases_willow):
            response = client.get("/api/release?type=willow")

            assert response.status_code == 200
            assert json.loads(response.content) == mock_releases_willow

            with patch("app.routers.release.get_was_url", return_value="ws://was.local/ws"):
                response = client.get("/api/release?type=was")

                assert response.status_code == 200
                assert json.loads(response.content) == mock_releases_was
