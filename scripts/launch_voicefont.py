"""Start the provisioned local app without installing anything; open after health."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def server_command(uv, port):
    return [
        uv,
        "run",
        "--offline",
        "--no-sync",
        "python",
        "-m",
        "voicefont",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def valid_health(payload):
    return (
        isinstance(payload, dict)
        and payload.get("status") == "ok"
        and payload.get("local_only") is True
        and bool(payload.get("feature_version"))
    )


def stop_server(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                timeout=15,
            )
        else:
            process.kill()
        process.wait(timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Headless local verification")
    parser.add_argument("--check", action="store_true", help="Stop after the real readiness check")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    uv = shutil.which("uv")
    if not uv or not (ROOT / ".venv/Scripts/python.exe").is_file():
        raise SystemExit("Local app is not provisioned. Follow docs/local-setup.md first.")
    # Do not open an unrelated service or silently reuse another registry on this port.
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError:
            raise SystemExit(
                "Port is already in use. Close the other server or use --port."
            ) from None
    env = os.environ.copy()
    env.update(
        UV_OFFLINE="1",
        UV_NO_SYNC="1",
        UV_PYTHON_DOWNLOADS="never",
        UV_PROJECT_ENVIRONMENT=str(ROOT / ".venv"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        DO_NOT_TRACK="1",
    )
    env.setdefault("VOICEFONT_OPENVOICE_CONFIG", str(ROOT / "data/openvoice-runtime/config.json"))
    process = subprocess.Popen(
        server_command(uv, args.port),
        cwd=ROOT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    url = f"http://127.0.0.1:{args.port}"
    # Ignore system HTTP proxies; readiness traffic must never leave loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Local server exited before readiness. See console error above.")
            try:
                with opener.open(url + "/health", timeout=1) as response:
                    payload = json.loads(response.read(16384))
                if valid_health(payload):
                    break
            except (OSError, ValueError, urllib.error.URLError):
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("Local server did not become ready within 45 seconds.")
        print(f"VoiceFont ready: {url}/calibrate", flush=True)
        print(json.dumps(payload), flush=True)
        if not args.no_browser and not webbrowser.open(url + "/calibrate"):
            print("Browser did not open automatically. Open the local address above.", flush=True)
        if not args.check:
            print("Keep this window open. Press Ctrl+C to stop VoiceFont.", flush=True)
            process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_server(process)


if __name__ == "__main__":
    main()
