"""Real local training acceptance, using generated signals rather than voices."""

import io
import math
import os
import struct
import wave

if os.environ.get("VOICEFONT_E2E") == "1":
    from playwright.sync_api import expect


def test_react_experiment_consent_training_results_and_resume(ui):
    page = ui.page
    created = ui.fetch(
        "/calibration/sessions",
        {
            "name": "GENERATED experiment signals - not a voice",
            "consent": True,
        },
    )
    assert created["status"] == 201
    sid = created["body"]["id"]
    prompts = ui.fetch("/calibration/corpus")["body"]["prompts"]
    for index, prompt in enumerate(prompts[:8]):
        stream = io.BytesIO()
        samples = [
            int(8000 * math.sin(2 * math.pi * (220 + index * 47) * n / 16000)) for n in range(8000)
        ]
        with wave.open(stream, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(struct.pack("<8000h", *samples))
        response = page.request.post(
            ui.base
            + f"/calibration/sessions/{sid}/takes"
            + f"?prompt_id={prompt['id']}&take_id=generated-{index}",
            data=stream.getvalue(),
            headers={"Content-Type": "audio/wav"},
        )
        assert response.status == 200, response.text()
    page.locator("#nav-experiments").click()
    expect(page.locator("#experiment-capability")).to_contain_text("installed")
    page.locator("#experiment-session").select_option(sid)
    expect(page.locator("#experiment-train")).to_be_disabled()
    page.locator("#experiment-consent").check()
    expect(page.locator("#experiment-train")).to_be_enabled()
    with page.expect_response(
        lambda r: r.url.endswith("/experiments") and r.request.method == "POST"
    ) as submitted:
        page.locator("#experiment-train").click()
    assert submitted.value.status == 202
    job_id = submitted.value.json()["id"]
    expect(page.locator("#experiment-status")).to_have_text("completed", timeout=120000)
    result = ui.fetch("/experiments/" + job_id)["body"]
    assert result["dataset"]["distinct_recordings"] == 8
    assert not set(result["dataset"]["train_hashes"]) & set(result["dataset"]["heldout_hashes"])
    for selector, metric in [
        ("#experiment-mse", "validation_mse"),
        ("#experiment-baseline", "baseline_mse"),
    ]:
        actual = float(page.locator(selector).inner_text())
        assert math.isfinite(actual)
        assert actual == result["report"]["metrics"][metric]
    expect(page.locator("#experiment-results")).to_contain_text(result["report"]["run_id"])
    expect(page.locator("#experiment-gate")).to_contain_text(
        "PASS" if result["gate_passed"] else "REJECTED"
    )
    page.reload()
    page.locator("#nav-experiments").click()
    expect(page.locator("#experiment-id")).to_contain_text(job_id)
    expect(page.locator("#experiment-status")).to_have_text("completed")
    ui.check("React explicit consent -> real local training -> metrics -> reload resume", result)
