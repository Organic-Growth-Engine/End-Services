import unittest
from unittest.mock import patch

import demo


class DemoTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("CLIENT_ID", "test-id"), ("CLIENT_SECRET", "test-secret"),
                            ("UPLOAD_API_SECRET", ""), ("PORT", 8001)):
            patcher = patch.object(demo.config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_demo(self, token_exists, args=None, auth_error=None):
        with patch.object(demo.TOKEN.__class__, "exists", return_value=token_exists), \
             patch("sys.argv", ["demo.py", *(args or [])]), \
             patch.object(demo, "credentials", side_effect=auth_error) as auth, \
             patch.object(demo.uvicorn, "run") as serve, \
             patch("builtins.print"), patch("builtins.input") as prompt, \
             patch.object(demo, "getpass") as secret_prompt:
            if auth_error:
                with self.assertRaises(SystemExit) as error:
                    demo.main()
                self.assertEqual(error.exception.code, 1)
                serve.assert_not_called()
            else:
                demo.main()
                serve.assert_called_once_with("api:app", host="127.0.0.1", port=8001, workers=1)
                self.assertTrue(demo.config.UPLOAD_API_SECRET)
            prompt.assert_not_called()
            secret_prompt.assert_not_called()
            return auth

    def test_first_run_authorizes_before_starting(self):
        self.run_demo(False).assert_called_once_with(interactive=True)

    def test_saved_authorization_is_validated(self):
        self.run_demo(True).assert_called_once_with()

    def test_login_option_uses_interactive_recovery(self):
        self.run_demo(True, ["--login"]).assert_called_once_with(interactive=True)

    def test_authorization_failure_does_not_start_service(self):
        self.run_demo(True, auth_error=RuntimeError("invalid token"))

    def test_configured_api_key_is_preserved(self):
        demo.config.UPLOAD_API_SECRET = "configured-demo-key"
        self.run_demo(True)
        self.assertEqual(demo.config.UPLOAD_API_SECRET, "configured-demo-key")


if __name__ == "__main__":
    unittest.main()
