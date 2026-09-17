"""REST boundary tests use an explicit fake transport, not retrieval evidence."""
import json

import httpx
import pytest

from voicefont.embeddings import EMBEDDING_VERSION
from voicefont.vector_store import WeaviateStore


@pytest.mark.parametrize('endpoint', ['https://example.com', 'http://localhost:8080', 'http://127.0.0.1:8080/path', 'http://user:pass@127.0.0.1:8080', 'http://0.0.0.0:8080'])
def test_only_explicit_loopback_endpoints(endpoint):
    with pytest.raises(ValueError):
        WeaviateStore(endpoint)


def test_store_consent_and_version_rejected_before_io():
    store = WeaviateStore()
    with pytest.raises(ValueError):
        store.insert([1.0]*192, version=EMBEDDING_VERSION, consent=False, profile_id='x', audio_sha256='a'*64)
    with pytest.raises(ValueError):
        store.search([1.0]*192, version='acoustic-v1', consent=True)
    store.close()


def test_schema_and_filtered_query_contract():
    captured = []
    def handle(request):
        captured.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.method == 'GET':
            return httpx.Response(404)
        if request.url.path == '/v1/graphql':
            return httpx.Response(200, json={'data': {'Get': {'VoiceFontSpeakerEcapaV1': []}}})
        return httpx.Response(200, json={})
    with WeaviateStore(transport=httpx.MockTransport(handle)) as store:
        store.ensure_collection()
        store.search([1.0]*192, version=EMBEDDING_VERSION, consent=True, limit=3)
    schema = captured[1][2]
    assert schema['vectorizer'] == 'none'
    assert schema['vectorIndexConfig']['distance'] == 'cosine'
    query = captured[2][2]['query']
    assert 'consent' in query and 'embeddingVersion' in query
    assert EMBEDDING_VERSION in query


@pytest.mark.parametrize('limit', [0, 101, True, 1.2])
def test_query_limit_bounded(limit):
    with WeaviateStore() as store, pytest.raises(ValueError):
        store.search([1.0]*192, version=EMBEDDING_VERSION, consent=True, limit=limit)


def test_redirects_not_followed():
    with WeaviateStore(transport=httpx.MockTransport(lambda _: httpx.Response(302, headers={'location': 'https://example.com'}))) as store:
        with pytest.raises(RuntimeError):
            store.ensure_collection()
