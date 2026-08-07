"""
Tests for Puff path sandbox security.
Run:  cd puff && python tests/test_sandbox.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure we can import from the puff directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security import safe_path, can_write, is_safe, READABLE_DIRS, WRITABLE_DIRS, WORK_ROOT, PERM_CONFIG


class TestPathSandbox(unittest.TestCase):
    """Verify that safe_path() blocks traversal attacks and bad paths."""

    def test_safe_relative_read(self):
        """Relative paths inside WORK_ROOT should resolve safely."""
        puff_dir = Path(__file__).resolve().parent.parent  # tests/ -> puff/
        result = safe_path("README.md", base=puff_dir)
        self.assertTrue(result.exists())
        self.assertIn("README.md", str(result))

    def test_traversal_dotdot_blocked(self):
        """../../../etc/passwd should be blocked."""
        with self.assertRaises(PermissionError):
            safe_path("../../../etc/passwd")

    def test_traversal_encoded_handled(self):
        """URL-encoded slashes (%2F) are treated literally, not as traversal."""
        # The sandbox does not URL-decode — %2F is a literal filename char.
        # This means the path stays inside WORK_ROOT and is safe.
        result = safe_path("..%2F..%2F..%2FWindows")
        self.assertIn(str(WORK_ROOT), str(result),
                      "Encoded path should resolve inside WORK_ROOT")

    def test_absolute_outside_blocked(self):
        """Absolute paths outside readable dirs should be blocked."""
        # Use Windows absolute path (works cross-platform: pathlib handles it)
        bad_path = "C:\\Windows\\System32\\config"
        with self.assertRaises(PermissionError):
            safe_path(bad_path)

    def test_is_safe_true(self):
        """is_safe should return True for paths under allowed dirs."""
        self.assertTrue(is_safe(WORK_ROOT / "README.md", READABLE_DIRS))

    def test_is_safe_false(self):
        """is_safe should return False for paths outside allowed dirs."""
        self.assertFalse(is_safe(Path("C:\\Windows\\System32"), READABLE_DIRS))

    def test_can_write_true(self):
        """can_write should allow writes inside WORK_ROOT."""
        self.assertTrue(can_write(WORK_ROOT / "test.txt"))

    def test_can_write_false(self):
        """can_write should deny writes outside writable dirs."""
        self.assertFalse(can_write(Path("C:\\Windows\\System32\\test.txt")))

    def test_writable_subset_of_readable(self):
        """Writable dirs must be a subset of readable dirs."""
        for wd in WRITABLE_DIRS:
            self.assertIn(wd, READABLE_DIRS,
                          f"{wd} is writable but not readable — config error")

    def test_read_write_sandbox_integration(self):
        """Full integration: resolve a path, verify it can be read but external paths fail."""
        puff_dir = Path(__file__).resolve().parent.parent
        # Valid read
        result = safe_path("README.md", base=puff_dir)
        self.assertTrue(can_write(result))  # README is inside WORK_ROOT

        # External write blocked
        self.assertFalse(can_write(Path("C:\\Windows\\System32\\test.txt")))

    def test_forbidden_paths_configured(self):
        """PERM_CONFIG must list critical forbidden paths."""
        forbidden = PERM_CONFIG.get("forbidden_paths", [])
        self.assertIn(".git", forbidden)
        self.assertIn(".env", forbidden)
        self.assertIn("secrets", forbidden)

    def test_max_file_size_configured(self):
        """PERM_CONFIG must cap file sizes at a reasonable limit."""
        max_size = PERM_CONFIG.get("max_file_size", 0)
        self.assertGreater(max_size, 0)
        self.assertLess(max_size, 100_000_000)  # shouldn't be unreasonably large


class TestRateLimiter(unittest.TestCase):
    """Verify rate limiter behavior."""

    def test_allows_calls_within_limit(self):
        from security import RateLimiter
        rl = RateLimiter(max_calls=5, window=60)
        for _ in range(5):
            self.assertTrue(rl.ok(), "Should allow calls within limit")

    def test_blocks_when_exceeded(self):
        from security import RateLimiter
        rl = RateLimiter(max_calls=3, window=60)
        for _ in range(3):
            self.assertTrue(rl.ok())
        self.assertFalse(rl.ok(), "Should block when limit exceeded")


class TestSoulHotReload(unittest.TestCase):
    """Verify SOUL.md hot reload mechanism."""

    def setUp(self):
        """Reset the shared soul cache before each test."""
        import security
        security._soul_mtime = 0
        security._soul_cache = ""

    def test_load_soul_creates_temp(self):
        """load_soul should read content from a file."""
        from security import hot_load_soul
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test Soul\nYou are a test agent.")
            tmp_path = Path(f.name)
        try:
            content = hot_load_soul(tmp_path)
            self.assertIn("Test Soul", content)
            self.assertIn("test agent", content)
        finally:
            tmp_path.unlink()

    def test_load_soul_missing_file_returns_fallback(self):
        """load_soul on missing file should return fallback text."""
        from security import hot_load_soul
        content = hot_load_soul(Path("/nonexistent/soul.md"))
        self.assertTrue(len(content) > 0, "Should return fallback text")


if __name__ == "__main__":
    unittest.main()
