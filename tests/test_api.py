"""
Tests for Puff API connectivity and configuration.
Run:  cd puff && python -m pytest tests/test_api.py -v
Or:   python tests/test_api.py
"""
import os
import sys
import json
import unittest
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestApiConfig(unittest.TestCase):
    """Verify API configuration is valid."""

    def test_api_key_set(self):
        """DEEPSEEK_API_KEY must be set in environment."""
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            self.skipTest("DEEPSEEK_API_KEY not set — skipping live API test")
        self.assertTrue(key.startswith("sk-"), "API key should start with sk-")
        self.assertGreater(len(key), 20, "API key too short")

    def test_api_base_valid(self):
        """DEEPSEEK_BASE_URL should be a valid URL."""
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.assertTrue(base.startswith("https://"), "API base should use HTTPS")

    def test_model_configured(self):
        """PUFF_MODEL should be set to a known model."""
        model = os.environ.get("PUFF_MODEL", "deepseek-v4-flash")
        self.assertIn("deepseek", model.lower())


class TestApiConnectivity(unittest.TestCase):
    """Verify API endpoint is reachable (requires DEEPSEEK_API_KEY)."""

    def setUp(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            self.skipTest("DEEPSEEK_API_KEY not set — skipping live API test")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("PUFF_MODEL", "deepseek-v4-flash")

    def test_api_chat_completion(self):
        """Send a minimal chat completion and verify response structure."""
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "user", "content": "回复'pong'"}
            ],
            "max_tokens": 10,
            "temperature": 0,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )

        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            self.fail(f"API returned HTTP {e.code}: {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            self.fail(f"Cannot reach API: {e.reason}")

        self.assertIn("choices", data, "Response missing 'choices' key")
        self.assertGreater(len(data["choices"]), 0, "No choices in response")
        msg = data["choices"][0]["message"]
        self.assertIn("content", msg, "Message missing 'content'")
        self.assertIsInstance(msg["content"], str)


class TestModuleImports(unittest.TestCase):
    """Verify all required modules and functions can be imported."""

    def test_puff_imports(self):
        """Core modules should be importable."""
        import security
        self.assertTrue(hasattr(security, "safe_path"))
        self.assertTrue(hasattr(security, "can_write"))
        self.assertTrue(hasattr(security, "api_limiter"))
        self.assertTrue(hasattr(security, "hot_load_soul"))
        self.assertTrue(hasattr(security, "PERM_CONFIG"))

    def test_security_constants(self):
        """Security module constants should be properly typed."""
        from security import WORK_ROOT, READABLE_DIRS, WRITABLE_DIRS
        self.assertIsInstance(WORK_ROOT, Path)
        self.assertIsInstance(READABLE_DIRS, list)
        self.assertIsInstance(WRITABLE_DIRS, list)
        self.assertGreater(len(READABLE_DIRS), 0)
        self.assertGreater(len(WRITABLE_DIRS), 0)


if __name__ == "__main__":
    unittest.main()
