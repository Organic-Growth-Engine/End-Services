import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError

import api
import config
import youtube_uploader as uploader

CREDS = {"client_id": "test-id", "client_secret": "test-secret", "refresh_token": "test-refresh"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)
        patcher = patch.object(api, "upload_video", return_value={"video_id": "abc"})
        self.send = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, credentials=None, video=b"video", **metadata):
        return self.client.post("/uploading", files={
            "file": ("clip.mp4", video, "video/mp4"),
            "channel_credentials": ("channel.json", json.dumps(CREDS) if credentials is None else credentials, "application/json"),
        }, data=metadata)

    def test_video_and_credentials_only_no_headers(self):
        paths = []
        def capture(path, creds, **metadata):
            paths.append(path)
            self.assertEqual(path.read_bytes(), b"video")
            self.assertEqual(creds, CREDS)
            self.assertEqual(metadata["title"], "clip")
            self.assertEqual(metadata["privacy"], "private")
            return {"video_id": "abc"}
        self.send.side_effect = capture
        self.assertEqual(self.post().status_code, 201)
        self.assertFalse(paths[0].exists())

    def test_each_request_uses_its_own_credentials(self):
        self.assertEqual(self.post().status_code, 201)
        other = dict(CREDS, refresh_token="other-channel")
        self.assertEqual(self.post(json.dumps(other)).status_code, 201)
        self.assertEqual(self.send.call_args_list[0].args[1], CREDS)
        self.assertEqual(self.send.call_args_list[1].args[1], other)

    def test_invalid_credentials_json(self):
        for value in ("invalid", "[]", "x" * (64 * 1024 + 1)):
            with self.subTest(value=value[:10]):
                self.assertEqual(self.post(value).status_code, 400)
        self.send.assert_not_called()

    def test_required_inputs(self):
        self.assertEqual(self.client.post("/uploading").status_code, 422)
        self.assertEqual(self.client.post("/uploading", files={"file": ("clip.mp4", b"video")}).status_code, 422)
        self.send.assert_not_called()

    def test_size_limit(self):
        with patch.object(config, "MAX_VIDEO_BYTES", 1):
            self.assertEqual(self.post().status_code, 413)
        self.send.assert_not_called()

    def test_failure_cleanup_and_safe_response(self):
        paths = []
        def fail(path, *args, **kwargs):
            paths.append(path)
            raise OSError("private upstream detail")
        self.send.side_effect = fail
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private upstream detail", response.text)
        self.assertFalse(paths[0].exists())

    def test_streams_closed(self):
        from starlette.datastructures import UploadFile
        video = UploadFile(io.BytesIO(b"video"), filename="clip.mp4")
        creds = UploadFile(io.BytesIO(b"invalid"), filename="channel.json")
        with self.assertRaises(api.HTTPException):
            api.upload(video, creds)
        self.assertTrue(video.file.closed)
        self.assertTrue(creds.file.closed)

    def test_openapi_has_single_endpoint_and_no_api_key(self):
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(set(schema["paths"]), {"/uploading"})
        operation = schema["paths"]["/uploading"]["post"]
        self.assertNotIn("parameters", operation)
        ref = operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
        self.assertEqual(set(schema["components"]["schemas"][ref]["required"]), {"file", "channel_credentials"})


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
