"""Start every configured service plus the gateway, with one combined log.

Used by ./run.sh. Standard library only, so it runs before any `uv sync`.

    ./run.sh                    # every service whose .env values are filled in
    ./run.sh telegram discord   # only these (plus the gateway)
"""

import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
LOG_DIR = ROOT / ".logs"
COLORS = ["\033[36m", "\033[33m", "\033[35m", "\033[32m", "\033[34m", "\033[31m", "\033[37m"]
RESET = "\033[0m"


@dataclass
class Service:
    name: str
    folder: str
    app: str  # uvicorn import string
    url_var: str  # the gateway setting that holds this service's URL
    default_url: str
    required: tuple[str, ...] = ()
    app_dir: str | None = None


SERVICES = [
    Service("youtube", "youtube", "youtube.main:app", "YOUTUBE_URL", "http://127.0.0.1:8001"),
    Service("x", "x", "main:app", "X_URL", "http://127.0.0.1:8000",
            ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"), app_dir="src"),
    Service("telegram", "bot/telegram", "api:app", "TELEGRAM_URL", "http://127.0.0.1:8002",
            ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_IDS")),
    Service("facebook", "meta_service/facebook", "main:app", "FACEBOOK_URL", "http://127.0.0.1:8003",
            ("FB_PAGE_ACCESS_TOKEN", "FB_PAGE_ID")),
    Service("instagram", "meta_service/instagram", "main:app", "INSTAGRAM_URL", "http://127.0.0.1:8004",
            ("IG_ACCESS_TOKEN", "IG_USER_ID")),
    Service("discord", "bot/discord", "main:app", "DISCORD_URL", "http://127.0.0.1:8005",
            ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_IDS")),
]


def read_env(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE reader; only used to see which values are filled in."""
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def setting(env: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, env.get(key, default))


def is_filled(value: str) -> bool:
    return value.strip() not in ("", "[]", "{}")


def stream(proc: subprocess.Popen, label: str, color: str, log_file: Path) -> None:
    with log_file.open("a") as log:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            sys.stdout.write(f"{color}{label:>9} |{RESET} {line}")
            sys.stdout.flush()


def wait_healthy(url: str, proc: subprocess.Popen, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def connect_discord_once(env_overrides: dict[str, str]) -> bool:
    """Discord needs one Gateway login before a bot can send messages."""
    marker = LOG_DIR / ".discord-connected"
    if marker.exists():
        return True
    print("discord: first run, connecting the bot to Discord once ...")
    result = subprocess.run(
        ["uv", "run", "--quiet", "python", "connect_once.py"],
        cwd=ROOT / "bot/discord", env={**os.environ, **env_overrides},
    )
    if result.returncode == 0:
        marker.touch()
        return True
    return False


def main() -> int:
    if not ENV_FILE.exists():
        print("No .env found. Run ./setup.sh first (it creates .env from .env.example).")
        return 1
    env = read_env(ENV_FILE)
    only = set(sys.argv[1:])
    unknown = only - {s.name for s in SERVICES}
    if unknown:
        print(f"Unknown service(s): {', '.join(sorted(unknown))}. "
              f"Choose from: {', '.join(s.name for s in SERVICES)}.")
        return 1
    LOG_DIR.mkdir(exist_ok=True)

    gateway_env: dict[str, str] = {}
    chosen: list[tuple[Service, str]] = []
    print("Services:")
    for service in SERVICES:
        url = setting(env, service.url_var, service.default_url).rstrip("/")
        missing = [k for k in service.required if not is_filled(setting(env, k))]
        if only and service.name not in only:
            reason = "not selected"
        elif not url:
            reason = f"disabled ({service.url_var} is empty)"
        elif missing:
            reason = f"skipped, fill in {', '.join(missing)}"
        else:
            reason = ""
        if reason:
            print(f"  - {service.name:9} {reason}")
            gateway_env[service.url_var] = ""  # gateway reports it as skipped
        else:
            print(f"  + {service.name:9} {url}")
            chosen.append((service, url))

    if any(s.name == "discord" for s, _ in chosen) and not connect_discord_once(gateway_env):
        print("  - discord   skipped: couldn't log in to Discord (check DISCORD_BOT_TOKEN)")
        chosen = [(s, u) for s, u in chosen if s.name != "discord"]
        gateway_env["DISCORD_URL"] = ""

    gateway_host = setting(env, "GATEWAY_HOST", "127.0.0.1")
    gateway_port = setting(env, "GATEWAY_PORT", "8080")
    gateway_url = f"http://{gateway_host}:{gateway_port}"

    procs: list[tuple[str, subprocess.Popen, str]] = []
    for index, (service, url) in enumerate([*chosen, (None, gateway_url)]):
        parsed = urlparse(url)
        if service is None:
            name, folder, cmd = "gateway", ROOT / "gateway", ["uv", "run", "--quiet", "gateway"]
        else:
            name, folder = service.name, ROOT / service.folder
            cmd = ["uv", "run", "--quiet", "uvicorn", service.app,
                   "--host", parsed.hostname or "127.0.0.1", "--port", str(parsed.port or 80)]
            if service.app_dir:
                cmd += ["--app-dir", service.app_dir]
        proc = subprocess.Popen(
            cmd, cwd=folder, env={**os.environ, **gateway_env, "PYTHONUNBUFFERED": "1"},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,  # so Ctrl+C here stops the whole process tree
        )
        threading.Thread(
            target=stream, args=(proc, name, COLORS[index % len(COLORS)], LOG_DIR / f"{name}.log"),
            daemon=True,
        ).start()
        procs.append((name, proc, url))

    def stop(*_):
        for _, proc, _ in procs:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
        for _, proc, _ in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)

    signal.signal(signal.SIGTERM, lambda *a: (stop(), sys.exit(0)))
    try:
        ready = {name: wait_healthy(url, proc) for name, proc, url in procs}
        print("\n" + "─" * 60)
        for name, _, url in procs:
            print(f"  {'ready ' if ready[name] else 'FAILED'}  {name:9} {url}")
        print(f"\n  Post to every platform:  POST {gateway_url}/posts")
        print(f"  Try it in the browser:   {gateway_url}/docs")
        print(f"  Logs: {LOG_DIR}/<service>.log   Stop: Ctrl+C")
        print("─" * 60 + "\n")
        while any(proc.poll() is None for _, proc, _ in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping ...")
    finally:
        stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
