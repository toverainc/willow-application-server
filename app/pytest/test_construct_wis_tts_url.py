from app.internal.was import construct_wis_tts_url


def test_construct_wis_tts_url():
    expect = "http://wis.local/api/tts?text="
    assert expect == construct_wis_tts_url("http://wis.local/api/tts")
    assert expect ==  construct_wis_tts_url("http://wis.local/api/tts?text")
    assert expect == construct_wis_tts_url("http://wis.local/api/tts?text=")

    expect = "http://wis.local/api/tts?bar=baz&text="
    assert expect == construct_wis_tts_url("http://wis.local/api/tts?text&bar=baz")
    assert expect == construct_wis_tts_url("http://wis.local/api/tts?text=&bar=baz")
    assert expect == construct_wis_tts_url("http://wis.local/api/tts?text=foo&bar=baz")

    expect = "http://wis.local:19000/api/tts?text="
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts")
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts?text")
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts?text=")

    expect = "http://wis.local:19000/api/tts?bar=baz&text="
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts?text&bar=baz")
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts?text=&bar=baz")
    assert expect == construct_wis_tts_url("http://wis.local:19000/api/tts?text=foo&bar=baz")

    expect = "http://user:pass@wis.local/api/tts?text="
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts?text")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts?text=")

    expect = "http://user:pass@wis.local/api/tts?bar=baz&text="
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts?text&bar=baz")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts?text=&bar=baz")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local/api/tts?text=foo&bar=baz")

    expect = "http://user:pass@wis.local:19000/api/tts?text="
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts?text")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts?text=")

    expect = "http://user:pass@wis.local:19000/api/tts?bar=baz&text="
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts?text&bar=baz")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts?text=&bar=baz")
    assert expect == construct_wis_tts_url("http://user:pass@wis.local:19000/api/tts?text=foo&bar=baz")
