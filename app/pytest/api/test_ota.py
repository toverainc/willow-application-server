import json
import unittest

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestOta(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestOta, self).__init__(*args, **kwargs)

        from app.main import app
        self.client = TestClient(app)

    def test_get_ota(self):
        mock_uri_bad = "/api/ota?platform=ESP32-S3-BOX-3&version=0.0.0-mock.0/../../.."
        mock_uri_good = "/api/ota?platform=ESP32-S3-BOX-3&version=0.0.0-mock.0"
        mock_releases_willow = [{
            "name": "0.0.0-mock.0",
            "tag_name": "0.0.0-mock.0",
            "assets": [
                {
                    "browser_download_url": "bogus",
                    "platform": "ESP32-S3-BOX-3",
                }
            ]
        }]
        mock_response = MagicMock()
        mock_response.content = b"mocked data"

        with patch("app.routers.ota.get_releases_willow", return_value=mock_releases_willow):
            # patch os.path.isfile so we call get_releases_willow()
            # this will write mock_response to storage/ota/0.0.0-mock.0/ESP32-S3-BOX-3.bin
            with patch("os.path.isfile", return_value=False):
                with patch("app.routers.ota.get", return_value=mock_response):
                    response = self.client.get(mock_uri_good)

                    assert response.status_code == 404

            # os.path.isfile is not patched here so we serve the file content
            response = self.client.get(mock_uri_good)

            assert response.status_code == 200
            assert response.content == b"mocked data"

            # use bad URL that tries to read data outside OTA_DIR
            response = self.client.get(mock_uri_bad)

            json_response = json.loads(response.content)
            print(json_response)

            assert response.status_code == 400
            assert json_response['detail'].startswith("invalid asset path")


if __name__ == '__main__':
    unittest.main()