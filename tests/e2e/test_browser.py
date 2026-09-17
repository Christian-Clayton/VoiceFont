"""Critical UI flows. Audio is generated test signal, never person/quality evidence."""

import hashlib
import io
import json
import os
import wave
import zipfile

import pytest

if os.environ.get("VOICEFONT_E2E") == "1":
    from playwright.sync_api import expect


def choose(page, prompt):
    button = page.locator(".prompt-choice").filter(has_text=prompt + " ·")
    button.evaluate("el => el.closest('details').open = true")
    button.click()
    expect(button).to_have_attribute("aria-current", "step")


def start(ui, name):
    page = ui.page
    page.locator("#session-name").fill(name)
    page.locator("#consent").check()
    with page.expect_response(
        lambda r: r.url.endswith("/calibration/sessions") and r.request.method == "POST"
    ) as response:
        page.locator("#start-session").click()
    assert response.value.status == 201
    expect(page.locator("#studio")).to_be_visible()
    return response.value.json()


def record_save(ui):
    page = ui.page
    before = page.evaluate("window.__captureEvidence.callbacks")
    page.locator("#record").click()
    expect(page.locator("#recorder-status")).to_contain_text("Recording.")
    expect(page.locator("#skip")).to_be_disabled()
    # Wait for actual WebAudio callbacks and at least a second of PCM, not just a timer.
    page.wait_for_function("n => window.__captureEvidence.callbacks > n + 14", arg=before)
    page.locator("#stop").click()
    expect(page.locator("#save")).to_be_enabled()
    expect(page.locator("#record")).to_be_disabled()
    expect(page.locator("#next")).to_be_disabled()
    page.wait_for_function(
        """() => window.__captureEvidence.streams.every(s =>
          s.getTracks().every(t => t.readyState === 'ended')) &&
          window.__captureEvidence.contexts.every(c => c.state === 'closed')"""
    )
    page.locator("#replay").click()
    page.wait_for_function("() => document.querySelector('#take-audio').currentTime > 0")
    with page.expect_response(
        lambda r: "/takes?" in r.url and r.request.method == "POST"
    ) as response:
        page.locator("#save").click()
    assert response.value.status == 200, response.value.text()
    expect(page.locator("#message")).to_contain_text("Take saved locally")
    session = response.value.json()
    ui.check(
        "native fake getUserMedia -> WebAudio callbacks -> PCM -> stop/replay/save",
        {
            "take_id": session["takes"][-1]["id"],
            "duration_seconds": session["takes"][-1]["duration_seconds"],
        },
    )
    return session


def test_generated_pcm_wizard_retakes_resume_export_finalize_library(ui):
    page = ui.page
    sessions_before = ui.fetch("/calibration/sessions")["body"]
    page.locator("#start-session").click()
    assert not page.locator("#consent").evaluate("el => el.checkValidity()")
    assert ui.fetch("/calibration/sessions")["body"] == sessions_before
    ui.check(
        "profile ID client validation",
        page.locator("#voice-id").evaluate("""el => {
      el.value='invalid id!'; const valid=el.checkValidity(); el.value='';
      return {selector:'#voice-id',pattern:el.pattern,invalidIdAccepted:valid};
    }"""),
    )
    ui.expected_http_errors.add(("/calibration/sessions", 422))
    denied = ui.fetch(
        "/calibration/sessions",
        {"name": "GENERATED test: consent absent", "consent": False, "mode": "full"},
    )
    assert denied["status"] == 422
    ui.check("unchecked consent blocks UI and false consent rejected by server")
    session = start(ui, "GENERATED two-tone signal — NOT a human voice")
    root = "/calibration/sessions/" + session["id"]
    session = record_save(ui)
    first = session["takes"][0]
    choose(page, "phonetic-01")
    page.locator("#rerecord").click()
    session = record_save(ui)
    assert len(session["takes"]) == 2 and session["coverage"]["completed"] == 1
    choose(page, "phonetic-01")
    page.locator(".take-row").first.get_by_role("button", name="Use this take").click()
    expect(page.locator(".take-row").first).to_contain_text("selected")
    session = ui.fetch(root)["body"]
    assert session["accepted"]["phonetic-01"] == first["id"]
    assert len(session["takes"]) == 2
    page.locator(".take-row").first.get_by_role("button", name="Replay saved").click()
    page.wait_for_function("() => document.querySelector('#take-audio').currentTime > 0")
    choose(page, "range-01")
    with page.expect_response(lambda r: r.url.endswith("/skip")):
        page.locator("#skip").click()
    assert "range-01" in ui.fetch(root)["body"]["skipped"]
    page.reload()
    page.get_by_role("button", name="Resume", exact=True).click()
    expect(page.locator("#coverage-count")).to_contain_text("1 /")
    session = ui.fetch(root)["body"]
    assert len(session["takes"]) == 2 and session["accepted"]["phonetic-01"] == first["id"]
    assert "range-01" in session["skipped"]
    ui.check("retake/select preserve earlier takes; skip and reload/resume persisted")
    # Incomplete finalization must fail without discarding the active session.
    page.locator("#show-finalize").click()
    page.locator("#voice-id").fill("generated-mechanics-only")
    ui.expected_http_errors.add((root + "/finalize", 422))
    page.locator("#finalize-form button[type=submit]").click()
    expect(page.locator("#message.error")).to_contain_text("3")
    assert ui.fetch(root)["body"]["status"] == "active"
    page.locator("#cancel-finalize").click()
    choose(page, "phonetic-02")
    record_save(ui)
    choose(page, "connected-01")
    session = record_save(ui)
    assert session["coverage"]["completed"] == 3
    assert sum(c["completed"] > 0 for c in session["coverage"]["by_category"].values()) == 2
    with page.expect_download() as download:
        page.locator("#export-session").click()
    archive_path = ui.output / "generated-session-backup.zip"
    download.value.save_as(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert not any(name.startswith(("/", "\\")) or ".." in name.split("/") for name in names)
        assert "session.json" in names and "corpus.json" in names
        exported = json.loads(archive.read("session.json"))
        assert len(exported["takes"]) == 4
        wav_names = [name for name in names if name.endswith(".wav")]
        assert len(wav_names) == 4
        hashes = set()
        for name in wav_names:
            raw = archive.read(name)
            hashes.add(hashlib.sha256(raw).hexdigest())
            with wave.open(io.BytesIO(raw)) as wav:
                assert wav.getsampwidth() == 2 and wav.getnchannels() == 1
                assert wav.getframerate() == 48000 and wav.getnframes() >= 48000
                assert any(wav.readframes(wav.getnframes()))
        assert hashes == {take["sha256"] for take in session["takes"]}
    ui.check("ZIP contains 4 byte-preserved native 48kHz mono PCM16 takes", names)
    page.locator("#show-finalize").click()
    expect(page.locator("#finalize-summary")).to_contain_text(
        "3 accepted prompts across 2 categories"
    )
    page.locator("#voice-id").fill("generated-mechanics-only")
    page.locator("#finalize-form button[type=submit]").click()
    expect(page.locator("#view-library")).to_be_visible()
    expect(page.locator("#profiles-list")).to_contain_text("GENERATED two-tone signal")
    assert ui.fetch(root)["body"]["status"] == "finalized"
    profile = ui.fetch("/profiles/generated-mechanics-only")
    assert profile["status"] == 200
    (ui.output / "finalized-profile.json").write_text(
        json.dumps(profile["body"], indent=2), encoding="utf8"
    )
    page.reload()
    page.locator("#nav-library").click()
    expect(page.locator("#profiles-list")).to_contain_text("generated-mechanics-only")
    page.locator("#profiles-list").get_by_role("button", name="Create speech").click()
    expect(page.locator("#capability")).to_contain_text("Engine unavailable")
    expect(page.locator("#generate")).to_be_disabled()
    expect(page.locator("#cancel-job")).to_be_disabled()
    ui.check(
        "3 prompts/2 categories finalized; library reload; real unavailable backend disabled"
    )


def test_synthesis_error_cancel_ui_boundaries_explicit_network_stubs(ui):
    """Fault injection only; NOT an engine run or proof of worker cancellation."""
    page = ui.page
    ui.context.route(
        "**/profiles",
        lambda route: route.fulfill(
            json=[
                {
                    "voice_id": "generated-boundary-fixture",
                    "name": "GENERATED network boundary fixture",
                }
            ]
        ),
    )
    ui.context.route(
        "**/synthesis/capabilities",
        lambda route: route.fulfill(
            json={
                "available": True,
                "backend": "E2E NETWORK STUB (not synthesis)",
                "device": "none",
                "message": "UI boundary injection only",
            }
        ),
    )
    page.locator("#nav-speech").click()
    expect(page.locator("#generate")).to_be_enabled()
    page.locator("#speech-voice").select_option("generated-boundary-fixture")
    page.locator("#speech-text").fill(
        "Generated fixture: this request must never invoke a real engine."
    )
    ui.expected_http_errors.add(("/synthesis/jobs", 503))
    ui.context.route(
        "**/synthesis/jobs",
        lambda route: route.fulfill(status=503, json={"detail": "E2E injected unavailable worker"}),
    )
    page.locator("#generate").click()
    expect(page.locator("#job-status")).to_contain_text("E2E injected unavailable worker")
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("#cancel-job")).to_be_disabled()
    expect(page.locator("#speech-audio")).to_be_hidden()
    expect(page.locator("#download-speech")).to_be_hidden()
    ui.check("injected POST 503 visible, controls recover, no fabricated speech/audio")
    job = {"id": "e2e-network-stub", "status": "running"}
    ui.context.route("**/synthesis/jobs", lambda route: route.fulfill(status=202, json=job))
    ui.expected_http_errors.add(("/synthesis/jobs/e2e-network-stub", 503))
    ui.context.route(
        "**/synthesis/jobs/e2e-network-stub",
        lambda route: route.fulfill(status=503, json={"detail": "E2E injected polling failure"}),
    )
    ui.context.route(
        "**/synthesis/jobs/e2e-network-stub/cancel",
        lambda route: route.fulfill(json={"id": job["id"], "status": "cancelled"}),
    )
    page.locator("#generate").click()
    expect(page.locator("#message")).to_contain_text("Status check failed")
    expect(page.locator("#check-job")).to_be_visible()
    expect(page.locator("#generate")).to_be_disabled()
    expect(page.locator("#cancel-job")).to_be_enabled()
    page.locator("#cancel-job").click()
    expect(page.locator("#job-status")).to_have_text("Status: cancelled")
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("#cancel-job")).to_be_disabled()
    expect(page.locator("#speech-audio")).to_be_hidden()
    expect(page.locator("#download-speech")).to_be_hidden()
    ui.check("injected polling failure retains cancel; cancelled UI is terminal without audio")


@pytest.mark.parametrize("width,height", [(1440, 1000), (390, 844), (320, 740)])
def test_viewports_have_no_horizontal_overflow(ui, width, height):
    page = ui.page
    page.set_viewport_size({"width": width, "height": height})
    failures = []

    def measure(label):
        page.screenshot(path=str(ui.output / (label + ".png")), full_page=True)
        measurement = page.evaluate("""() => ({width:innerWidth,
          document:document.documentElement.scrollWidth, body:document.body.scrollWidth,
          overflowing:[...document.querySelectorAll('body *')].filter(el => {
            const r=el.getBoundingClientRect();return r.width && r.right>innerWidth+1;
          }).map(el=>({tag:el.tagName,id:el.id,cls:el.className,right:el.getBoundingClientRect().right}))})""")
        ui.check("viewport " + label, measurement)
        if max(measurement["document"], measurement["body"]) > width + 1:
            failures.append({"view": label, **measurement})

    measure("setup")
    start(ui, f"GENERATED viewport mechanics {width}")
    measure("studio")
    page.locator("#show-finalize").click()
    measure("finalize")
    page.locator("#nav-library").click()
    expect(page.locator("#view-library")).to_be_visible()
    measure("library")
    page.locator("#nav-speech").click()
    expect(page.locator("#capability")).to_contain_text("Engine unavailable")
    measure("speech")
    if page.locator("#nav-experiments").count():
        page.locator("#nav-experiments").click()
        expect(page.locator("#experiments-panel")).to_be_visible()
        expect(page.locator("#experiments-details")).to_have_attribute("open", "")
        measure("experiments")
    assert not failures, json.dumps(failures, indent=2)
