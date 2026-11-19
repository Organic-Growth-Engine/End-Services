import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError

from youtube import config
from youtube import main as api
from youtube import youtube_uploader as uploader

CREDS = {"client_id": "test-id", "client_secret": "test-secret", "refresh_token": "test-refresh"}


class ApiTests(unittest.TestCase):
    """POST /upload: download from a URL, upload, return the result, clean up."""

    URL = "https://cdn.example.com/clip.mp4"

    def setUp(self):
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)
        self.paths = []

        def fake_download(url, path):
            self.paths.append(path)
            path.write_bytes(b"video")
            return "video/mp4"

        for name, kwargs in (
            ("download_video", {"side_effect": fake_download}),
            ("upload_video", {"return_value": {"video_id": "abc", "url": "u", "status": {}, "message": "m"}}),
        ):
            patcher = patch.object(api, name, **kwargs)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def post(self, url=URL, credentials=CREDS, **params):
        query = {"url": url, "file_id": "1", "title": "Clip", "description": "d", **params}
        return self.client.post("/upload", params=query, json=credentials)

    def test_returns_result_and_removes_download(self):
        response = self.post()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["video_id"], "abc")
        path = self.upload_video.call_args.args[0]
        self.assertEqual(path.suffix, ".mp4")  # extension taken from the URL
        self.assertEqual(self.upload_video.call_args.args[1:], (CREDS, "Clip", "d"))
        self.assertFalse(path.exists())

    def test_unknown_extension_defaults_to_webm(self):
        self.post(url="https://cdn.example.com/video?id=1")
        self.assertEqual(self.paths[0].suffix, ".webm")

    def test_failures_are_mapped_and_cleaned_up(self):
        for error, status in ((ValueError("bad video"), 400), (RuntimeError("reconnect"), 409),
                              (OSError("private upstream detail"), 502)):
            with self.subTest(error=error):
                self.upload_video.side_effect = error
                response = self.post()
                self.assertEqual(response.status_code, status)
                self.assertNotIn("private upstream detail", response.text)
                self.assertFalse(self.paths[-1].exists())

    def test_download_failure_skips_upload(self):
        self.download_video.side_effect = ValueError("Video download failed with HTTP 404.")
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.upload_video.assert_not_called()

    def test_required_inputs(self):
        self.assertEqual(self.client.post("/upload").status_code, 422)
        self.download_video.assert_not_called()


class DownloadTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.out = Path(folder.name) / "clip.mp4"

    def download(self, handler, url="https://cdn.example.com/clip.mp4"):
        """Run download_video with httpx.stream served by ``handler``."""
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        with patch.object(uploader.httpx, "stream", lambda method, u, **kw: client.stream(method, u)):
            return uploader.download_video(url, self.out)

    def test_downloads_and_returns_content_type(self):
        content_type = self.download(lambda r: httpx.Response(200, content=b"video", headers={"Content-Type": "video/mp4"}))
        self.assertEqual(content_type, "video/mp4")
        self.assertEqual(self.out.read_bytes(), b"video")

    def test_rejects_and_cleans_up(self):
        cases = {
            "http error": lambda r: httpx.Response(404),
            "empty": lambda r: httpx.Response(200, content=b""),
            "too big": lambda r: httpx.Response(200, content=b"xx"),
        }
        for name, handler in cases.items():
            with self.subTest(name), patch.object(config, "MAX_VIDEO_BYTES", 1):
                with self.assertRaises(ValueError):
                    self.download(handler)
                self.assertFalse(self.out.exists())

    def test_rejects_non_http_urls(self):
        with self.assertRaises(ValueError):
            uploader.download_video("file:///etc/passwd", self.out)


class UploaderTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.video = Path(folder.name) / "clip.mp4"
        self.video.write_bytes(b"video")

    def test_invalid_credentials(self):
        for info in ({}, {"installed": CREDS}, dict(CREDS, refresh_token="")):
            with self.assertRaises(ValueError):
                uploader.load_credentials(info)

    def test_credentials_refresh_and_revocation(self):
        creds = Mock()
        type(creds).valid = property(lambda obj: getattr(obj, "refreshed", False))
        creds.refreshed = False
        creds.refresh.side_effect = lambda request: setattr(creds, "refreshed", True)
        with patch.object(uploader.Credentials, "from_authorized_user_info", return_value=creds):
            self.assertIs(uploader.load_credentials(CREDS), creds)
            creds.refresh.assert_called_once()
            creds.refreshed = False
            creds.refresh.side_effect = RefreshError("secret upstream detail")
            with self.assertRaisesRegex(RuntimeError, "reconnect"):
                uploader.load_credentials(CREDS)

    def test_credential_token_url_is_not_caller_controlled(self):
        info = dict(CREDS, token_uri="https://example.invalid", token="access", expiry="2099-01-01T00:00:00Z")
        creds = uploader.load_credentials(info)
        self.assertEqual(creds.token_uri, "https://oauth2.googleapis.com/token")

    def test_validation_precedes_google(self):
        with patch.object(uploader, "build") as build:
            for metadata in ({"title": " "}, {"privacy": "invalid"}, {"description": "x" * 5001}):
                with self.assertRaises(ValueError):
                    uploader.upload_video(self.video, CREDS, **metadata)
            with patch.object(config, "MAX_VIDEO_BYTES", 1):
                with self.assertRaises(ValueError):
                    uploader.upload_video(self.video, CREDS)
            self.video.write_bytes(b"")
            with self.assertRaises(ValueError):
                uploader.upload_video(self.video, CREDS)
            build.assert_not_called()

    def test_client_closed_when_media_creation_fails(self):
        client = Mock()
        with patch.object(uploader, "load_credentials"), patch.object(uploader, "build", return_value=client), patch.object(uploader, "MediaFileUpload", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                uploader.upload_video(self.video, CREDS)
        client.close.assert_called_once()

    def test_upload_and_failure_close_resources(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                client = Mock()
                request = client.videos.return_value.insert.return_value
                request.next_chunk.side_effect = OSError("network") if fail else [(None, {"id": "abc"})]
                stream = io.BytesIO(b"video")
                media = Mock()
                media.stream.return_value = stream
                with patch.object(uploader, "load_credentials"), patch.object(uploader, "build", return_value=client), patch.object(uploader, "MediaFileUpload", return_value=media):
                    if fail:
                        with self.assertRaises(OSError):
                            uploader.upload_video(self.video, CREDS)
                    else:
                        self.assertEqual(uploader.upload_video(self.video, CREDS)["video_id"], "abc")
                        body = client.videos.return_value.insert.call_args.kwargs["body"]
                        self.assertEqual(body["snippet"]["title"], "clip")
                        self.assertEqual(body["status"]["privacyStatus"], "private")
                self.assertTrue(stream.closed)
                client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
