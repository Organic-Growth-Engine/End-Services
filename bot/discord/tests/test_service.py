"""Discord's REST API is faked with httpx.MockTransport; nothing is sent."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

import config
import main
import publisher


def fake_discord(handler):
    """Swap the app's Discord client for one backed by ``handler``."""
    seen: list[httpx.Request] = []

    def record(request):
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(base_url=config.API_BASE_URL, transport=httpx.MockTransport(record))
    return client, seen


def created(request):
    channel = request.url.path.split("/")[-2]
    return httpx.Response(200, json={"id": f"msg-{channel}"})


@pytest.fixture
def api():
    with TestClient(main.app) as client:
        yield client


def test_config_parses_channel_ids():
    assert config._parse_channel_ids('["111", 222, "111"]') == ["111", "222"]
    with pytest.raises(ValueError):
        config._parse_channel_ids('["#general"]')
    with pytest.raises(ValueError):
        config._parse_channel_ids("111")


def test_publishes_to_every_channel(api):
    main.app.state.client, seen = fake_discord(created)
    body = {
        "content": "Launch day",
        "media": [
            {"type": "image", "url": "https://cdn.example.com/a.jpg", "alt_text": "cat"},
            {"type": "video", "url": "https://cdn.example.com/v.mp4"},
        ],
    }
    response = api.post("/publish", json=body)

    assert response.status_code == 200
    assert response.json() == {
        "published": 2, "total": 2,
        "results": [
            {"channel_id": "111", "ok": True, "message_id": "msg-111", "error": None},
            {"channel_id": "222", "ok": True, "message_id": "msg-222", "error": None},
        ],
    }
    assert {r.url.path for r in seen} == {"/api/v10/channels/111/messages", "/api/v10/channels/222/messages"}
    sent = json.loads(seen[0].content)
    assert sent == {
        "allowed_mentions": {"parse": []},
        "content": "Launch day\nhttps://cdn.example.com/v.mp4",
        "embeds": [{"image": {"url": "https://cdn.example.com/a.jpg"}, "title": "cat"}],
    }


def test_partial_and_total_failure(api):
    def one_forbidden(request):
        if "/222/" in request.url.path:
            return httpx.Response(403, json={"message": "Missing Access", "code": 50001})
        return created(request)

    main.app.state.client, _ = fake_discord(one_forbidden)
    response = api.post("/publish", json={"content": "hi"})
    assert response.status_code == 200
    assert response.json()["published"] == 1
    assert response.json()["results"][1]["error"] == "Discord HTTP 403: Missing Access"

    main.app.state.client, _ = fake_discord(lambda r: httpx.Response(404, json={"message": "Unknown Channel"}))
    response = api.post("/publish", json={"content": "hi"})
    assert response.status_code == 502
    assert response.json()["detail"]["published"] == 0


def test_retries_rate_limit_but_not_network_errors(api, monkeypatch):
    async def no_sleep(_):
        pass

    monkeypatch.setattr(publisher.asyncio, "sleep", no_sleep)
    calls = {"n": 0}

    def limited_once(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"message": "rate limited", "retry_after": 0.5})
        return created(request)

    main.app.state.client, _ = fake_discord(limited_once)
    monkeypatch.setattr(config, "CHANNEL_IDS", ["111"])
    assert api.post("/publish", json={"content": "hi"}).json()["published"] == 1
    assert calls["n"] == 2

    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    main.app.state.client, seen = fake_discord(timeout)
    response = api.post("/publish", json={"content": "hi"})
    assert response.status_code == 502 and len(seen) == 1  # no retry


@pytest.mark.parametrize("body", [
    {}, {"content": "  "}, {"content": "x" * 2001},
    {"media": [{"type": "image", "url": "https://e.com/a.jpg"}] * 11},
    {"content": "hi", "extra": 1},
])
def test_rejects_invalid_posts(api, body):
    main.app.state.client, seen = fake_discord(created)
    assert api.post("/publish", json=body).status_code == 422
    assert seen == []
