"""The calibration checklist must ship with the locally served page."""
from fastapi.testclient import TestClient

from voicefont.api import create_app


def test_calibration_page_and_corpus_are_served_locally(tmp_path):
    client = TestClient(create_app(tmp_path))
    page = client.get('/calibrate')
    assert page.status_code == 200
    assert 'Record' in page.text
    assert 'Replay' in page.text
    corpus = client.get('/calibration/corpus').json()
    assert len(corpus['prompts']) >= 70
    assert len({p['id'] for p in corpus['prompts']}) == len(corpus['prompts'])
    assert all(p['text'] and p['instruction'] and p['category'] for p in corpus['prompts'])
    assert client.get('/calibration-assets/app.js').status_code == 200
