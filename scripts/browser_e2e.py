"""Run the real local UI against an isolated server and generated microphone audio.

No human recording, voice-quality claim, runtime weights or cloud browser.
Provision once: uv pip install --python .venv/Scripts/python.exe playwright==1.63.0
Run: .venv/Scripts/python.exe scripts/browser_e2e.py
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, help="Existing Chrome/Chromium executable")
    parser.add_argument("--output", type=Path, help="New evidence directory (must not exist)")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        import uvicorn

        from voicefont.api import create_app

        uvicorn.run(create_app(args.output / "profiles"), host="127.0.0.1", port=args.port)
        return 0

    output = (
        args.output or REPO / "data" / "browser-e2e" / time.strftime("%Y%m%d-%H%M%S")
    ).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidates = (
        [args.browser]
        if args.browser
        else [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
            / "Google/Chrome/Application/chrome.exe",
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ]
    )
    browser = next((p.resolve() for p in candidates if p and p.is_file()), None)
    if not browser:
        parser.error("No installed browser found; pass --browser. No browser is auto-downloaded.")
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(REPO / "src"),
            "VOICEFONT_OPENVOICE_CONFIG": str(output / "intentionally-nonexistent-openvoice.json"),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "LANGSMITH_TRACING": "false",
            "LANGCHAIN_TRACING_V2": "false",
            "VOICEFONT_E2E": "1",
            "VOICEFONT_E2E_OUTPUT": str(output),
            "VOICEFONT_E2E_BROWSER": str(browser),
            "VOICEFONT_E2E_HEADED": str(int(args.headed)),
        }
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env["VOICEFONT_E2E_BASE"] = base
    metadata = {
        "base_url": base,
        "output": str(output),
        "browser_executable": str(browser),
        "audio": "generated dual-tone PCM fixture; NOT a human voice or speech quality test",
        "config": env["VOICEFONT_OPENVOICE_CONFIG"],
        "server_stopped": False,
    }
    result = 1
    server = None
    try:
        with (output / "server.log").open("w", encoding="utf8") as log:
            server = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--serve",
                    "--port",
                    str(port),
                    "--output",
                    str(output),
                ],
                cwd=REPO,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            metadata["server_pid"] = server.pid
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(150):
                if server.poll() is not None:
                    raise RuntimeError("Local server exited; inspect server.log")
                try:
                    with opener.open(base + "/calibration/corpus", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Local server not ready; inspect server.log")
            command = [
                sys.executable,
                "-m",
                "pytest",
                "tests/e2e",
                "-v",
                "--tb=short",
                f"--junitxml={output / 'junit.xml'}",
            ]
            metadata["test_command"] = command
            run = subprocess.run(command, cwd=REPO, env=env, text=True, capture_output=True)
            (output / "pytest.log").write_text(run.stdout + run.stderr, encoding="utf8")
            print(run.stdout, end="")
            print(run.stderr, end="", file=sys.stderr)
            result = run.returncode
    finally:
        if server is not None:
            if server.poll() is None:
                server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
            # Windows may report process exit before the listening socket closes.
            for _ in range(100):
                with socket.socket() as sock:
                    sock.settimeout(0.2)
                    metadata["server_stopped"] = sock.connect_ex(("127.0.0.1", port)) != 0
                if metadata["server_stopped"]:
                    break
                time.sleep(0.1)
            metadata["server_exit_code"] = server.returncode
        metadata["test_exit_code"] = result
        (output / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf8")
        print(f"Evidence: {output}\nServer stopped: {metadata['server_stopped']}")
    return result if metadata["server_stopped"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
