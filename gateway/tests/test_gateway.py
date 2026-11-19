"""Gateway tests. The platform services are faked with httpx.MockTransport."""

import asyncio
import json

import httpx
import pytest

from gateway import adapters
from gateway.jobs import JobStore, run_job
from gateway.schemas import JobStatus, PostRequest, TargetStatus

CREDS = {"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"}
VIDEO = {"type": "video", "url": "https://cdn.example.com/clip.mp4"}


def run(post: dict, handler) -> tuple[dict, list[httpx.Request]]:
    """Run one job against fake services; return the job and the requests sent."""
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async def go():
        request = PostRequest.model_validate(post)
        job = JobStore(10).create(request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as client:
            await run_job(job, request, client)
        return job.model_dump(mode="json")

    return asyncio.run(go()), seen


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True, "path": request.url.path})


def by_port(request: httpx.Request) -> str:
    return {8001: "youtube", 8000: "x", 8002: "telegram", 8003: "facebook", 8004: "instagram",
            8005: "discord"}[
        request.url.port
    ]


def test_posts_to_every_platform_and_maps_fields():
    job, seen = run(
        {"text": "Launch day\nmore", "media": [VIDEO], "youtube": {"credentials": CREDS}},
        ok,
    )
    assert job["status"] == JobStatus.SUCCEEDED
    assert {p: t["status"] for p, t in job["targets"].items()} == {
        "youtube": "succeeded", "x": "succeeded", "telegram": "succeeded",
        "facebook": "succeeded", "instagram": "succeeded", "discord": "succeeded",
    }
    calls = {by_port(r): r for r in seen}

    yt = calls["youtube"]
    assert yt.url.path == "/upload"
    assert yt.url.params["url"] == VIDEO["url"]
    assert yt.url.params["title"] == "Launch day"  # first line of text
    assert yt.url.params["description"] == "Launch day\nmore"
    assert json.loads(yt.content) == CREDS  # credentials are the body

    assert json.loads(calls["x"].content) == {
        "text": "Launch day\nmore", "media": [VIDEO], "allow_url": False,
    }
    assert json.loads(calls["facebook"].content) == {
        "message": "Launch day\nmore", "media": [{"type": "VIDEO", "url": VIDEO["url"]}],
    }
    # A single Instagram video is published as a reel.
    assert json.loads(calls["instagram"].content) == {
        "caption": "Launch day\nmore", "media": [{"type": "REELS", "url": VIDEO["url"]}],
    }
    assert json.loads(calls["discord"].content) == {
        "content": "Launch day\nmore", "media": [VIDEO],
    }
    tg = json.loads(calls["telegram"].content)
    assert tg["content"] == "Launch day\nmore"
    assert tg["media"] == [{"type": "video", "url": VIDEO["url"]}]


def test_skips_platforms_the_post_does_not_suit():
    # Text only, no credentials: YouTube can't take it, the rest can.
    job, seen = run({"text": "hello"}, ok)
    yt = job["targets"]["youtube"]
    assert yt["status"] == TargetStatus.SKIPPED and "credentials" in yt["detail"]
    assert job["targets"]["instagram"]["status"] == TargetStatus.SKIPPED  # no media
    assert {by_port(r) for r in seen} == {"x", "telegram", "facebook", "discord"}
    assert job["status"] == JobStatus.SUCCEEDED

    job, _ = run({"text": "doc", "media": [{"type": "document", "url": "https://e.com/a.pdf"}]}, ok)
    assert job["targets"]["x"]["status"] == TargetStatus.SKIPPED
    assert job["targets"]["telegram"]["status"] == TargetStatus.SUCCEEDED


def test_targets_limit_where_it_posts():
    job, seen = run({"text": "only x", "targets": ["x"]}, ok)
    assert list(job["targets"]) == ["x"]
    assert [by_port(r) for r in seen] == ["x"]


def test_partial_failure_is_reported_per_platform():
    def handler(request):
        if by_port(request) == "x":
            return httpx.Response(422, json={"detail": "text is 300 weighted characters"})
        return ok(request)

    job, _ = run({"text": "hi", "targets": ["x", "telegram"]}, handler)
    assert job["status"] == JobStatus.PARTIAL
    x = job["targets"]["x"]
    assert x["status"] == TargetStatus.FAILED and x["http_status"] == 422
    assert x["response"] == {"detail": "text is 300 weighted characters"}


def test_unreachable_service_fails_without_raising():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    job, _ = run({"text": "hi", "targets": ["telegram"]}, handler)
    assert job["status"] == JobStatus.FAILED
    assert "Could not reach" in job["targets"]["telegram"]["detail"]


def test_credentials_never_appear_in_the_job():
    job, _ = run({"text": "t", "media": [VIDEO], "youtube": {"credentials": CREDS}}, ok)
    assert "secret" not in json.dumps(job)


def test_disabled_platform_is_skipped(monkeypatch):
    monkeypatch.setitem(adapters.config.SERVICE_URLS, "x", None)
    job, seen = run({"text": "hi", "targets": ["x"]}, ok)
    assert job["targets"]["x"]["status"] == TargetStatus.SKIPPED
    assert seen == []


@pytest.mark.parametrize("post", [{}, {"text": "   "}, {"text": "a", "targets": []},
                                  {"text": "a", "targets": ["myspace"]}, {"text": "a", "extra": 1}])
def test_rejects_bad_requests(post):
    from fastapi.testclient import TestClient
    from gateway.main import app

    with TestClient(app) as client:
        assert client.post("/posts", json=post).status_code == 422


def test_api_returns_job_and_status_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from gateway import main

    async def fake_run_job(job, post, client):
        job.status = JobStatus.SUCCEEDED

    monkeypatch.setattr(main, "run_job", fake_run_job)
    with TestClient(main.app) as client:
        created = client.post("/posts", json={"text": "hi"})
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert set(created.json()["targets"]) == {
            "youtube", "x", "telegram", "facebook", "instagram", "discord",
        }
        assert client.get(f"/posts/{job_id}").status_code == 200
        assert client.get("/posts/nope").status_code == 404


IMG = {"type": "image", "url": "https://cdn.example.com/a.jpg", "alt_text": "a cat"}
IMG2 = {"type": "image", "url": "https://cdn.example.com/b.jpg"}


def test_meta_photo_posts_and_carousels():
    job, seen = run({"text": "pics", "media": [IMG, IMG2], "targets": ["facebook", "instagram"]}, ok)
    assert job["status"] == JobStatus.SUCCEEDED
    calls = {by_port(r): json.loads(r.content) for r in seen}
    assert calls["facebook"] == {"message": "pics", "media": [
        {"type": "IMAGE", "url": IMG["url"], "alt_text": "a cat"},
        {"type": "IMAGE", "url": IMG2["url"]},
    ]}
    assert calls["instagram"] == {"caption": "pics", "media": [
        {"type": "IMAGE", "url": IMG["url"], "alt_text": "a cat"},
        {"type": "IMAGE", "url": IMG2["url"]},
    ]}

    # A video inside an Instagram carousel stays VIDEO; Facebook can't mix them.
    job, seen = run({"media": [IMG, VIDEO], "targets": ["facebook", "instagram"]}, ok)
    assert job["targets"]["facebook"]["status"] == TargetStatus.SKIPPED
    assert [m["type"] for m in json.loads(seen[0].content)["media"]] == ["IMAGE", "VIDEO"]


def test_meta_skips_unsupported_media():
    gif = {"type": "gif", "url": "https://cdn.example.com/a.gif"}
    job, seen = run({"media": [gif], "targets": ["facebook", "instagram"]}, ok)
    assert job["targets"]["instagram"]["status"] == TargetStatus.SKIPPED
    assert json.loads(seen[0].content) == {"media": [{"type": "IMAGE", "url": gif["url"]}]}


def test_youtube_uses_env_credentials_by_default(monkeypatch):
    monkeypatch.setattr(adapters.config, "YOUTUBE_CREDENTIALS", CREDS)
    job, seen = run({"text": "t", "media": [VIDEO], "targets": ["youtube"]}, ok)
    assert job["targets"]["youtube"]["status"] == TargetStatus.SUCCEEDED
    assert json.loads(seen[0].content) == CREDS

    # Credentials in the request win over .env.
    other = dict(CREDS, refresh_token="other")
    _, seen = run({"text": "t", "media": [VIDEO], "targets": ["youtube"],
                   "youtube": {"credentials": other}}, ok)
    assert json.loads(seen[0].content) == other


def test_youtube_env_credentials_parsing(monkeypatch):
    from gateway import config

    for name in ("YOUTUBE_CREDENTIALS_JSON", "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET",
                 "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.setenv(name, "")
    assert config._youtube_credentials() is None
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    with pytest.raises(ValueError, match="YOUTUBE_CLIENT_SECRET"):
        config._youtube_credentials()
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "s")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "r")
    assert config._youtube_credentials() == {"client_id": "id", "client_secret": "s", "refresh_token": "r"}


def test_all_skipped_is_its_own_status():
    job, seen = run({"text": "hi", "targets": ["youtube", "instagram"]}, ok)
    assert job["status"] == JobStatus.SKIPPED and seen == []
