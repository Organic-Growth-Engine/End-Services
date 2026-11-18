"""Tests run against a mocked X API, so they never spend credits.

X API calls are intercepted at the HTTP layer with `responses`, which means the
real xdk SDK (including OAuth 1.0a signing) runs. Media downloads use an httpx
mock transport.
"""

import base64
import json
import time

import httpx
import pytest
import responses
from fastapi.testclient import TestClient

import config
import main
import routes
import x_client
from publisher import XPublisher

API = "https://api.x.com"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"1" * 50


@pytest.fixture
def x():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def files():
    """URL -> (body, content type) served to the publisher's downloader."""
    return {}


@pytest.fixture
def client(monkeypatch, files):
    for name in ("API_KEY", "API_SECRET", "ACCESS_TOKEN", "ACCESS_TOKEN_SECRET"):
        monkeypatch.setattr(config, name, f"test-{name.lower()}")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(x_client.asyncio, "sleep", no_sleep)

    def serve(request: httpx.Request) -> httpx.Response:
        if str(request.url) not in files:
            return httpx.Response(404)
        body, mime = files[str(request.url)]
        return httpx.Response(200, content=body, headers={"content-type": mime})

    http = httpx.AsyncClient(transport=httpx.MockTransport(serve))
    main.app.dependency_overrides[routes.get_publisher] = lambda: XPublisher(
        routes.get_client(), http
    )
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def post_created(x, post_id="100", text="hello"):
    x.post(f"{API}/2/tweets", json={"data": {"id": post_id, "text": text}}, status=201)


def sent_posts(x):
    return [
        json.loads(c.request.body)
        for c in x.calls
        if c.request.url == f"{API}/2/tweets"
    ]


# Text posts


def test_text_post_is_signed_with_oauth1(client, x):
    post_created(x)
    response = client.post("/publish", json={"text": "hello"})
    assert response.status_code == 200
    assert response.json() == {"posts": [{"id": "100", "text": "hello"}]}
    request = x.calls[0].request
    assert json.loads(request.body) == {"text": "hello"}
    assert request.headers["Authorization"].startswith("OAuth ")
    assert 'oauth_consumer_key="test-api_key"' in request.headers["Authorization"]


def test_flags_and_poll_are_passed_through(client, x):
    post_created(x)
    poll = {"options": ["Yes", "No"], "duration_minutes": 60}
    response = client.post(
        "/publish",
        json={
            "text": "vote",
            "poll": poll,
            "made_with_ai": True,
            "paid_partnership": False,
            "reply_settings": "following",
        },
    )
    assert response.status_code == 200
    assert sent_posts(x)[0] == {
        "text": "vote",
        "poll": poll,
        "made_with_ai": True,
        "paid_partnership": False,
        "reply_settings": "following",
    }


@pytest.mark.parametrize(
    "text, ok",
    [
        ("a" * 280, True),
        ("a" * 281, False),
        ("👨‍👩‍👧‍👦" * 140, True),  # every emoji counts as 2
        ("👨‍👩‍👧‍👦" * 141, False),
        ("日本" * 70, True),  # CJK counts as 2
        ("日本" * 70 + "a", False),
    ],
)
def test_weighted_character_limit(client, x, text, ok):
    post_created(x)
    response = client.post("/publish", json={"text": text})
    assert (response.status_code == 200) is ok


def test_needs_text_or_media(client):
    assert client.post("/publish", json={"text": "   "}).status_code == 422
    assert client.post("/publish", json={}).status_code == 422


def test_unknown_fields_are_rejected(client):
    assert client.post("/publish", json={"text": "hi", "quote": "1"}).status_code == 422


def test_more_than_one_cashtag_is_rejected(client):
    response = client.post("/publish", json={"text": "$TSLA and $AAPL"})
    assert response.status_code == 422
    assert "cashtag" in response.text


# URL cost guard


@pytest.mark.parametrize("text", ["read https://example.com/post", "see example.com"])
def test_urls_need_allow_url(client, x, text):
    response = client.post("/publish", json={"text": text})
    assert response.status_code == 422
    assert "allow_url" in response.text
    assert not x.calls

    post_created(x)
    assert (
        client.post("/publish", json={"text": text, "allow_url": True}).status_code
        == 200
    )


def test_url_in_thread_needs_allow_url(client, x):
    response = client.post(
        "/publish", json={"text": "one", "thread": [{"text": "https://example.com"}]}
    )
    assert response.status_code == 422
    assert "thread[0]" in response.text


# Media


def test_image_upload_with_alt_text(client, x, files):
    files["https://cdn.test/a.png"] = (PNG, "image/png")
    x.post(f"{API}/2/media/upload/initialize", json={"data": {"id": "111"}})
    x.post(f"{API}/2/media/upload/111/append", json={})
    x.post(f"{API}/2/media/upload/111/finalize", json={"data": {"id": "111"}})
    x.post(f"{API}/2/media/metadata", json={"data": {"id": "111"}})
    post_created(x)

    response = client.post(
        "/publish",
        json={
            "text": "pic",
            "media": [
                {"type": "image", "url": "https://cdn.test/a.png", "alt_text": "A cat"}
            ],
        },
    )
    assert response.status_code == 200, response.text

    assert json.loads(x.calls[0].request.body) == {
        "media_type": "image/png",
        "total_bytes": len(PNG),
        "media_category": "tweet_image",
    }
    assert base64.b64decode(json.loads(x.calls[1].request.body)["media"]) == PNG
    # Finalize had no processing_info, so the media is ready without polling.
    assert not [c for c in x.calls if c.request.method == "GET"]
    assert json.loads(x.calls[3].request.body) == {
        "id": "111",
        "metadata": {"alt_text": {"text": "A cat"}},
    }
    assert sent_posts(x)[0]["media"] == {"media_ids": ["111"]}


def test_video_chunked_upload_waits_for_processing(client, x, files, monkeypatch):
    monkeypatch.setattr(x_client, "CHUNK_SIZE", 20)
    files["https://cdn.test/v.mp4"] = (MP4, "video/mp4")
    x.post(f"{API}/2/media/upload/initialize", json={"data": {"id": "222"}})
    x.post(f"{API}/2/media/upload/222/append", json={})
    x.post(
        f"{API}/2/media/upload/222/finalize",
        json={
            "data": {
                "id": "222",
                "processing_info": {"state": "pending", "check_after_secs": 1},
            }
        },
    )
    x.get(
        f"{API}/2/media/upload",
        json={"data": {"id": "222", "processing_info": {"state": "in_progress"}}},
    )
    x.get(
        f"{API}/2/media/upload",
        json={"data": {"id": "222", "processing_info": {"state": "succeeded"}}},
    )
    post_created(x)

    response = client.post(
        "/publish", json={"media": [{"type": "video", "url": "https://cdn.test/v.mp4"}]}
    )
    assert response.status_code == 200, response.text

    init = json.loads(x.calls[0].request.body)
    assert init == {
        "media_type": "video/mp4",
        "total_bytes": len(MP4),
        "media_category": "tweet_video",
    }
    appends = [
        json.loads(c.request.body) for c in x.calls if c.request.url.endswith("/append")
    ]
    assert [a["segment_index"] for a in appends] == list(range(-(-len(MP4) // 20)))
    assert b"".join(base64.b64decode(a["media"]) for a in appends) == MP4
    status_calls = [c for c in x.calls if c.request.method == "GET"]
    assert len(status_calls) == 2
    assert "command=STATUS" in status_calls[0].request.url
    assert sent_posts(x)[0] == {"media": {"media_ids": ["222"]}}


def test_failed_video_processing(client, x, files):
    files["https://cdn.test/v.mp4"] = (MP4, "video/mp4")
    x.post(f"{API}/2/media/upload/initialize", json={"data": {"id": "222"}})
    x.post(f"{API}/2/media/upload/222/append", json={})
    x.post(
        f"{API}/2/media/upload/222/finalize",
        json={"data": {"id": "222", "processing_info": {"state": "failed"}}},
    )
    response = client.post(
        "/publish", json={"media": [{"type": "video", "url": "https://cdn.test/v.mp4"}]}
    )
    assert response.status_code == 502
    assert "could not process" in response.json()["detail"]
    assert not sent_posts(x)


@pytest.mark.parametrize(
    "media",
    [
        [{"type": "image", "url": f"https://cdn.test/{i}.png"} for i in range(5)],
        [
            {"type": "image", "url": "https://cdn.test/a.png"},
            {"type": "video", "url": "https://cdn.test/v.mp4"},
        ],
        [
            {"type": "gif", "url": "https://cdn.test/a.gif"},
            {"type": "gif", "url": "https://cdn.test/b.gif"},
        ],
    ],
)
def test_media_combinations_follow_x_rules(client, media):
    assert client.post("/publish", json={"media": media}).status_code == 422


def test_wrong_file_type_is_rejected_before_upload(client, x, files):
    files["https://cdn.test/a.png"] = (b"<html>", "text/html")
    response = client.post(
        "/publish", json={"media": [{"type": "image", "url": "https://cdn.test/a.png"}]}
    )
    assert response.status_code == 422
    assert "text/html" in response.text
    assert not x.calls


def test_oversized_image_is_rejected(client, x, files):
    files["https://cdn.test/big.png"] = (b"0" * (5 * 1024 * 1024 + 1), "image/png")
    response = client.post(
        "/publish",
        json={"media": [{"type": "image", "url": "https://cdn.test/big.png"}]},
    )
    assert response.status_code == 422
    assert "5 MB" in response.text
    assert not x.calls


def test_unreachable_media(client, x):
    response = client.post(
        "/publish",
        json={"media": [{"type": "image", "url": "https://cdn.test/missing.png"}]},
    )
    assert response.status_code == 422
    assert "HTTP 404" in response.text


# Threads and replies


def test_thread_chains_replies(client, x):
    for post_id in ("1", "2", "3"):
        post_created(x, post_id, f"post {post_id}")
    response = client.post(
        "/publish",
        json={
            "text": "post 1",
            "thread": [{"text": "post 2"}, {"text": "post 3"}],
            "made_with_ai": True,
        },
    )
    assert response.status_code == 200
    assert [p["id"] for p in response.json()["posts"]] == ["1", "2", "3"]
    bodies = sent_posts(x)
    assert "reply" not in bodies[0]
    assert bodies[1]["reply"] == {"in_reply_to_tweet_id": "1"}
    assert bodies[2]["reply"] == {"in_reply_to_tweet_id": "2"}
    assert all(body["made_with_ai"] for body in bodies)


def test_thread_failure_reports_published_posts(client, x):
    post_created(x, "1", "first")
    x.post(
        f"{API}/2/tweets",
        json={"title": "Forbidden", "detail": "Reply not permitted.", "status": 403},
        status=403,
    )
    response = client.post(
        "/publish", json={"text": "first", "thread": [{"text": "second"}]}
    )
    assert response.status_code == 502
    body = response.json()
    assert body["published"] == [{"id": "1", "text": "first"}]
    assert body["x_status"] == 403
    assert "post 2 of 2" in body["detail"]
    assert "Reply not permitted." in body["detail"]


def test_reply_to_existing_post(client, x):
    post_created(x)
    response = client.post("/publish", json={"text": "hi", "reply_to_post_id": "12345"})
    assert response.status_code == 200
    assert sent_posts(x)[0]["reply"] == {"in_reply_to_tweet_id": "12345"}
    assert (
        client.post(
            "/publish", json={"text": "hi", "reply_to_post_id": "abc"}
        ).status_code
        == 422
    )


# Errors from X


def test_rate_limit_returns_retry_after(client, x):
    x.post(
        f"{API}/2/tweets",
        json={
            "title": "Too Many Requests",
            "detail": "Too Many Requests",
            "status": 429,
        },
        status=429,
        headers={"x-rate-limit-reset": str(int(time.time()) + 120)},
    )
    response = client.post("/publish", json={"text": "hi"})
    assert response.status_code == 429
    assert 100 <= int(response.headers["Retry-After"]) <= 120


def test_x_error_detail_is_reported(client, x):
    x.post(
        f"{API}/2/tweets",
        json={
            "title": "Forbidden",
            "detail": "This user is not allowed to post a video longer than 20 minutes.",
            "status": 403,
        },
        status=403,
    )
    response = client.post("/publish", json={"text": "hi"})
    assert response.status_code == 502
    assert "longer than 20 minutes" in response.json()["detail"]


def test_missing_credentials(client, monkeypatch):
    monkeypatch.setattr(config, "ACCESS_TOKEN", "")
    response = client.get("/account")
    assert response.status_code == 502
    assert "X_ACCESS_TOKEN" in response.json()["detail"]


# Account and delete


def test_account(client, x):
    x.get(
        f"{API}/2/users/me",
        json={
            "data": {
                "id": "42",
                "name": "Bot",
                "username": "bot",
                "subscription_type": "None",
            }
        },
    )
    response = client.get("/account")
    assert response.status_code == 200
    assert response.json()["username"] == "bot"
    assert "user.fields=" in x.calls[0].request.url


def test_delete_post(client, x):
    x.delete(f"{API}/2/tweets/100", json={"data": {"deleted": True}})
    response = client.delete("/posts/100")
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert x.calls[0].request.headers["Authorization"].startswith("OAuth ")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_request_errors_are_reported_before_missing_credentials(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    response = client.post("/publish", json={"text": "see example.com"})
    assert response.status_code == 422
    assert "allow_url" in response.text
