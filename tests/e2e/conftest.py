"""Opt-in local browser fixtures: synthetic signal, never a real microphone."""

from __future__ import annotations

import array
import hashlib
import json
import math
import os
import urllib.parse
import wave
from pathlib import Path

import pytest

# Normal unit-suite collection does not require Playwright or start a browser.
if os.environ.get("VOICEFONT_E2E") == "1":
    from playwright.sync_api import sync_playwright


def pytest_collection_modifyitems(items):
    if os.environ.get("VOICEFONT_E2E") != "1":
        for item in items:
            if "/e2e/" in str(item.path).replace("\\", "/"):
                item.add_marker(
                    pytest.mark.skip(reason="Run scripts/browser_e2e.py (local opt-in)")
                )


@pytest.fixture(scope="session")
def browser():
    output = Path(os.environ["VOICEFONT_E2E_OUTPUT"])
    signal = output / "GENERATED-NOT-A-VOICE.wav"
    rate = 48000
    # Chromium fake capture loops this generated fixture; no personal audio input.
    samples = array.array(
        "h",
        (
            int(
                32767
                * (
                    0.18 * math.sin(2 * math.pi * 440 * n / rate)
                    + 0.08 * math.sin(2 * math.pi * 660 * n / rate)
                )
            )
            for n in range(rate * 10)
        ),
    )
    with wave.open(str(signal), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ["VOICEFONT_E2E_BROWSER"],
            headless=os.environ.get("VOICEFONT_E2E_HEADED") != "1",
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-audio-capture={signal}",
                "--mute-audio",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--no-first-run",
            ],
        )
        (output / "browser.json").write_text(
            json.dumps(
                {
                    "version": browser.version,
                    "fixture": str(signal),
                    "sha256": hashlib.sha256(signal.read_bytes()).hexdigest(),
                    "purpose": "Generated two-tone; microphone mechanics only, not voice quality",
                },
                indent=2,
            ),
            encoding="utf8",
        )
        yield browser
        browser.close()


@pytest.fixture
def ui(browser, request):
    output = Path(os.environ["VOICEFONT_E2E_OUTPUT"]) / request.node.name
    output.mkdir()
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        permissions=["microphone"],
        accept_downloads=True,
        service_workers="block",
    )
    evidence = {
        "requests": [],
        "responses": [],
        "console": [],
        "page_errors": [],
        "external_blocked": [],
        "websockets_blocked": [],
        "checks": [],
    }
    base = os.environ["VOICEFONT_E2E_BASE"]

    def guard(route):
        url = route.request.url
        host = urllib.parse.urlsplit(url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            evidence["external_blocked"].append(url)
            route.abort("blockedbyclient")
        else:
            route.continue_()

    context.route("**/*", guard)

    def websocket_guard(route):
        # Product has no websocket requirement; deny instead of connecting externally.
        evidence["websockets_blocked"].append(route.url)
        route.close()

    context.route_web_socket("**/*", websocket_guard)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.set_default_timeout(10000)
    page.on(
        "console",
        lambda msg: evidence["console"].append(
            {"type": msg.type, "text": msg.text, "location": msg.location}
        ),
    )
    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
    page.on(
        "request",
        lambda req: evidence["requests"].append(
            {"url": req.url, "method": req.method, "type": req.resource_type}
        ),
    )
    page.on(
        "response", lambda res: evidence["responses"].append({"url": res.url, "status": res.status})
    )
    page.on("dialog", lambda dialog: dialog.accept())
    # Observe native capture without substituting getUserMedia or PCM processing.
    page.add_init_script("""(() => {
      window.__captureEvidence = {streams: [], contexts: [], callbacks: 0};
      const native = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = async (...args) => {
        const stream = await native(...args);
        window.__captureEvidence.streams.push(stream);
        return stream;
      };
      const original = AudioContext.prototype.createScriptProcessor;
      AudioContext.prototype.createScriptProcessor = function(...args) {
        window.__captureEvidence.contexts.push(this);
        const node = original.apply(this, args);
        node.addEventListener('audioprocess', () => window.__captureEvidence.callbacks++);
        return node;
      };
    })();""")

    class UI:
        pass

    state = UI()
    state.page, state.context, state.output = page, context, output
    state.base, state.evidence = base, evidence
    state.expected_http_errors = set()
    state.check = lambda label, detail=None: evidence["checks"].append(
        {"check": label, "detail": detail}
    )

    def fetch(path, body=None):
        return page.evaluate(
            """async ({path,body}) => {
          const r = await fetch(path, body === null ? {} : {method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
          return {status:r.status, body:await r.json()};
        }""",
            {"path": path, "body": body},
        )

    state.fetch = fetch
    page.goto(base + "/calibrate")
    page.locator("#start-session:not([disabled])").wait_for()
    yield state
    try:
        page.screenshot(path=str(output / "final.png"), full_page=True)
        (output / "final.html").write_text(page.content(), encoding="utf8")
        context.tracing.stop(path=str(output / "trace.zip"))
    finally:
        context.close()
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf8")
    assert not evidence["external_blocked"], evidence["external_blocked"]
    assert not evidence["websockets_blocked"], evidence["websockets_blocked"]
    assert not evidence["page_errors"], evidence["page_errors"]
    unexpected_http = [
        r
        for r in evidence["responses"]
        if r["status"] >= 400
        and (urllib.parse.urlsplit(r["url"]).path, r["status"]) not in state.expected_http_errors
    ]
    assert not unexpected_http, unexpected_http
    unexpected_console = [
        c
        for c in evidence["console"]
        if c["type"] == "error"
        and not (
            "Failed to load resource" in c["text"]
            and any(
                urllib.parse.urlsplit(c["location"].get("url", "")).path == p
                for p, _ in state.expected_http_errors
            )
        )
    ]
    assert not unexpected_console, unexpected_console
