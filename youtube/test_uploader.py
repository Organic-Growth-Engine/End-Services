import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError

import api
import config
import youtube_uploader as uploader


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.secret = patch.object(config, 'UPLOAD_API_SECRET', 'test-secret')
        self.secret.start()
        self.addCleanup(self.secret.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)
        self.headers = {'X-API-Key': 'test-secret'}
        self.upload = patch.object(api, 'upload_video', return_value={'video_id': 'abc'})
        self.send = self.upload.start()
        self.addCleanup(self.upload.stop)

    def post(self, body=b'video', **fields):
        return self.client.post('/upload', headers=self.headers,
                                files={'file': ('clip.mp4', body, 'video/mp4')},
                                data={'title': 'Test', **fields})

    def test_success_and_cleanup(self):
        paths = []
        def capture(path, *args):
            paths.append(path)
            self.assertEqual(path.read_bytes(), b'video')
            self.assertEqual(args[2], 'private')
            return {'video_id': 'abc'}
        self.send.side_effect = capture
        self.assertEqual(self.post().status_code, 201)
        self.assertFalse(paths[0].exists())

    def test_auth_before_body(self):
        self.assertEqual(self.client.post('/upload', content=b'invalid').status_code, 401)
        with patch.object(config, 'UPLOAD_API_SECRET', ''):
            self.assertEqual(self.post().status_code, 503)
        self.send.assert_not_called()
        self.assertEqual(self.client.get('/health').status_code, 200)

    def test_invalid_metadata_and_empty_file(self):
        for fields in ({'title': ' '}, {'title': 'x'*101}, {'description': 'é'*2501},
                       {'privacy': 'invalid'}, {'tags': 'x'*501}):
            with self.subTest(fields=fields):
                self.assertEqual(self.post(**fields).status_code, 400)
        self.assertEqual(self.post(body=b'').status_code, 400)
        self.send.assert_not_called()

    def test_limits_and_bad_length(self):
        with patch.object(api, 'MAX_VIDEO_BYTES', 4):
            self.assertEqual(self.post().status_code, 413)
        for length, status in [('garbage', 400), ('-1', 400), (str(10**15), 413)]:
            response = self.client.post('/upload', headers={**self.headers, 'Content-Length': length})
            self.assertEqual(response.status_code, status)
        self.send.assert_not_called()

    def test_stream_limit_without_content_length(self):
        def chunks():
            yield b'--test\r\nContent-Disposition: form-data; name="file"; filename="a.mp4"\r\n\r\n'
            yield b'x' * 1000
            yield b'\r\n--test--\r\n'
        with patch.object(api, 'MAX_VIDEO_BYTES', 100), patch.object(api, 'MULTIPART_OVERHEAD_BYTES', 100):
            response = self.client.post('/upload', headers={**self.headers,
                'Content-Type': 'multipart/form-data; boundary=test'}, content=chunks())
        self.assertEqual(response.status_code, 413)
        self.assertFalse(api.UPLOAD_SLOT.locked())
        self.send.assert_not_called()

    def test_extra_files_and_oversized_fields(self):
        response = self.client.post('/upload', headers=self.headers, data={'title': 'Test'},
            files=[('file', ('a.mp4', b'a')), ('extra', ('b.mp4', b'b'))])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post(description='x'*20000).status_code, 400)
        self.send.assert_not_called()

    def test_busy_rejected_before_parsing(self):
        with api.UPLOAD_SLOT:
            response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers['Retry-After'], '30')
        self.send.assert_not_called()

    def test_failure_cleanup_and_safe_errors(self):
        paths = []
        def fail(path, *args):
            paths.append(path)
            raise OSError('sensitive upstream detail')
        self.send.side_effect = fail
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('sensitive', response.text)
        self.assertFalse(paths[0].exists())
        self.assertFalse(api.UPLOAD_SLOT.locked())


class UploaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.video = self.folder / 'clip.mp4'
        self.video.write_bytes(b'video')
        self.token = patch.object(uploader, 'TOKEN', self.folder / 'token.json')
        self.token.start()
        self.addCleanup(self.token.stop)

    def test_missing_login(self):
        with self.assertRaises(RuntimeError):
            uploader.credentials()

    def test_atomic_token_failure_preserves_previous(self):
        uploader.TOKEN.write_text('old')
        creds = Mock()
        creds.to_json.return_value = 'new'
        with patch.object(uploader.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                uploader.save_credentials(creds)
        self.assertEqual(uploader.TOKEN.read_text(), 'old')
        self.assertEqual(list(self.folder.glob('.token-*')), [])

    def test_revoked_token_interactive_recovery(self):
        uploader.TOKEN.write_text('{}')
        old = Mock(expired=True, refresh_token='refresh')
        old.refresh.side_effect = RefreshError('revoked')
        fresh = Mock(valid=True)
        fresh.to_json.return_value = '{"valid":true}'
        flow = Mock()
        flow.run_local_server.return_value = fresh
        with patch.object(uploader.Credentials, 'from_authorized_user_file', return_value=old), \
             patch.object(uploader.InstalledAppFlow, 'from_client_config', return_value=flow), \
             patch.object(config, 'CLIENT_ID', 'id'), patch.object(config, 'CLIENT_SECRET', 'secret'):
            with self.assertRaises(RuntimeError):
                uploader.credentials()
            self.assertIs(uploader.credentials(interactive=True), fresh)
        self.assertEqual(uploader.TOKEN.read_text(), '{"valid":true}')

    def test_corrupt_token_can_relogin(self):
        uploader.TOKEN.write_text('invalid JSON')
        with self.assertRaisesRegex(RuntimeError, 'login again'):
            uploader.credentials()

    def test_cli_limit_precedes_google_call(self):
        with patch.object(config, 'MAX_VIDEO_BYTES', 1), patch.object(uploader, 'build') as build:
            with self.assertRaises(ValueError):
                uploader.upload_video(self.video, 'Test')
            build.assert_not_called()

    def test_google_client_closed_when_media_creation_fails(self):
        youtube = Mock()
        with patch.object(uploader, 'credentials'), patch.object(uploader, 'build', return_value=youtube), \
             patch.object(uploader, 'MediaFileUpload', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                uploader.upload_video(self.video, 'Test')
        youtube.close.assert_called_once()

    def test_upload_and_failure_close_all_resources(self):
        for failure in (False, True):
            with self.subTest(failure=failure):
                youtube = Mock()
                request = youtube.videos.return_value.insert.return_value
                request.next_chunk.side_effect = OSError('network') if failure else [(None, {'id':'abc'})]
                stream = io.BytesIO(b'video')
                media = Mock()
                media.stream.return_value = stream
                with patch.object(uploader, 'credentials'), patch.object(uploader, 'build', return_value=youtube), \
                     patch.object(uploader, 'MediaFileUpload', return_value=media):
                    if failure:
                        with self.assertRaises(OSError):
                            uploader.upload_video(self.video, 'Test')
                    else:
                        result = uploader.upload_video(self.video, 'Test')
                        self.assertEqual(result['video_id'], 'abc')
                        self.assertEqual(youtube.videos.return_value.insert.call_args.kwargs['body']['status']['privacyStatus'], 'private')
                self.assertTrue(stream.closed)
                youtube.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
