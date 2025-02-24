from app.internal.was import get_release_url


def test_get_release_url():
    expect = "http://was.local/api/ota?version=local&platform=ESP32-S3-BOX-3"
    assert expect == get_release_url("ws://was.local/ws", "local", "ESP32-S3-BOX-3")

    expect = "http://was.local:8502/api/ota?version=local&platform=ESP32-S3-BOX-3"
    assert expect == get_release_url("ws://was.local:8502/ws", "local", "ESP32-S3-BOX-3")

    expect = "https://was.local/api/ota?version=local&platform=ESP32-S3-BOX-3"
    assert expect == get_release_url("wss://was.local/ws", "local", "ESP32-S3-BOX-3")

    expect = "https://was.local:8503/api/ota?version=local&platform=ESP32-S3-BOX-3"
    assert expect == get_release_url("wss://was.local:8503/ws", "local", "ESP32-S3-BOX-3")
