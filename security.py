"""
Puff Security Module — path sandbox, rate limiter, logging, SOUL hot reload.
"""
import os, sys, time, logging, threading
from pathlib import Path

# ── Logging setup ───────────────────────────────────────────────────────────
try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(Path(__file__).parent / "puff.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ]
    )
except Exception:
    # CI/test environments may not have write access
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
log = logging.getLogger("puff.security")

# ── Path Sandbox ───────────────────────────────────────────────────────────
WORK_ROOT = Path(os.environ.get("PUFF_WORK_ROOT", str(
    Path(__file__).resolve().parent.parent  # clawd/
))).resolve()

READABLE_DIRS = [WORK_ROOT, Path.home() / "Desktop", Path.home() / "Documents"]
WRITABLE_DIRS = [WORK_ROOT]
DELETE_REQUIRES_CONFIRM = True
_last_delete_request = None  # (path, timestamp)

def is_safe(target: Path, allowed: list[Path]) -> bool:
    try:
        r = target.resolve()
    except (OSError, RuntimeError):
        return False
    for d in allowed:
        try:
            r.relative_to(d.resolve())
            return True
        except ValueError:
            continue
    return False

def resolve(path_str: str, base: Path = None) -> Path:
    if base is None:
        base = WORK_ROOT
    cleaned = path_str.replace("\\", "/").lstrip("/")
    if Path(path_str).is_absolute():
        if not is_safe(Path(path_str), READABLE_DIRS):
            raise PermissionError(f"路径越权: {path_str}")
        return Path(path_str).resolve()
    target = (base / cleaned).resolve()
    if not is_safe(target, READABLE_DIRS):
        raise PermissionError(f"路径穿越被拦截: {path_str}")
    return target

def can_write(target: Path) -> bool:
    return is_safe(target, WRITABLE_DIRS)

def confirm_delete(path_str: str) -> bool:
    """Return True only if PERM_CONFIG allows delete."""
    global _last_delete_request
    now = time.time()
    _last_delete_request = (path_str, now)
    if PERM_CONFIG.get("allow_delete", False):
        log.info(f"Delete confirmed by config: {path_str}")
        return True
    log.warning(f"Delete blocked by PERM_CONFIG: {path_str}")
    return False

# ── Rate Limiter ───────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, max_calls=15, window=60.0):
        self.max = max_calls
        self.window = window
        self.calls = []
        self._lock = threading.Lock()

    def ok(self) -> bool:
        with self._lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.window]
            if len(self.calls) >= self.max:
                return False
            self.calls.append(now)
            return True

api_limiter = RateLimiter(15, 60)

# ── SOUL Hot Reload ────────────────────────────────────────────────────────
_soul_mtime = 0
_soul_cache = ""

def load_soul(path: Path) -> str:
    global _soul_mtime, _soul_cache
    try:
        if path.exists():
            mtime = path.stat().st_mtime
            if mtime != _soul_mtime:
                _soul_cache = path.read_text(encoding="utf-8")
                _soul_mtime = mtime
                log.info("SOUL.md reloaded")
    except Exception as e:
        log.error(f"SOUL load failed: {e}")
    return _soul_cache or "你是 Puff，泡芙 AI 公司的创意总监。"

# ── File Permissions Config ────────────────────────────────────────────────
PERM_CONFIG = {
    "allow_delete": False,        # require explicit --allow-delete flag
    "max_file_size": 2_000_000,   # 2MB
    "allowed_extensions": None,   # None = all text files
    "forbidden_paths": [          # never allow access to these
        ".git", ".env", "secrets", "credentials", ".ssh", ".claude",
    ],
}

# ── Public API aliases ──────────────────────────────────────────────────────
safe_path = resolve        # canonical name for puff.py consumers
hot_load_soul = load_soul  # canonical name for puff.py consumers
