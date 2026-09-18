"""Tests for voice_store.py: Weaviate-backed voice embedding store."""
import json
from unittest.mock import patch

import httpx
import pytest

from voicefont.embeddings import EMBEDDING_VERSION
from voicefont.voice_store import (
    COLLECTION,
    DEFAULT_ENDPOINT,
    VectorStoreError,
    WeaviateVoiceStore,
)


def valid_vector():
    """A valid 192-dim unit vector."""
    import math
    # Exactly 192 elements: first and last are 1/sqrt(2), rest are 0
    v = [0.0] * 192
    v[0] = 1.0
    v[-1] = 1.0
    norm = math.sqrt(2.0)
    return [x / norm for x in v]


class FakeResponse:
    """Minimal httpx.Response mock."""
    def __init__(self, status_code, json_data=None, text=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else (json.dumps(json_data) if json_data is not None else "")

    def json(self):
        return self._json


class FakeClient:
    """Mock httpx.Client that records calls."""
    def __init__(self, responses):
        self._responses = responses
        self.closed = False
        self.calls = []

    def request(self, method, url, json=None):
        self.calls.append((method, url, json))
        if self._responses:
            return self._responses.pop(0)
        raise httpx.ConnectError("connection refused")

    def close(self):
        self.closed = True


def make_store(responses=None):
    """Create a WeaviateVoiceStore with mocked httpx.Client."""
    store = WeaviateVoiceStore.__new__(WeaviateVoiceStore)
    store.endpoint = DEFAULT_ENDPOINT
    store.client = FakeClient(responses or [])
    return store


class TestWeaviateVoiceStoreInit:
    def test_default_endpoint(self):
        store = WeaviateVoiceStore()
        assert store.endpoint == DEFAULT_ENDPOINT

    def test_loopback_127_0_0_1_allowed(self):
        store = WeaviateVoiceStore("http://127.0.0.1:9999")
        assert store.endpoint == "http://127.0.0.1:9999"

    def test_loopback_ipv6_allowed(self):
        store = WeaviateVoiceStore("http://[::1]:9999")
        assert store.endpoint == "http://[::1]:9999"

    @pytest.mark.parametrize("endpoint", [
        "https://example.com",
        "http://localhost:8080",
        "http://127.0.0.1:8080/path",
        "http://user:pass@127.0.0.1:8080",
        "http://0.0.0.0:8080",
        "http://127.0.0.1",
        "ftp://127.0.0.1:8080",
        "http://127.0.0.1:8080/path?q=1",
    ])
    def test_non_loopback_rejected(self, endpoint):
        with pytest.raises(ValueError, match="loopback"):
            WeaviateVoiceStore(endpoint)


class TestWeaviateVoiceStoreRequest:
    def test_404_with_missing_ok(self):
        """404 with missing_ok=True returns None."""
        store = make_store([FakeResponse(404)])
        result = store._request("GET", "/test", missing_ok=True)
        assert result is None

    def test_404_without_missing_ok(self):
        """404 without missing_ok raises VectorStoreError."""
        store = make_store([FakeResponse(404)])
        with pytest.raises(VectorStoreError, match="HTTP 404"):
            store._request("GET", "/test")

    def test_500_raises(self):
        """Server errors raise VectorStoreError."""
        store = make_store([FakeResponse(500)])
        with pytest.raises(VectorStoreError, match="HTTP 500"):
            store._request("GET", "/test")

    def test_200_json_response(self):
        """200 responses return parsed JSON."""
        store = make_store([FakeResponse(200, json_data={"status": "ok"})])
        result = store._request("GET", "/test")
        assert result == {"status": "ok"}

    def test_empty_200_response(self):
        """Empty 200 response returns empty dict."""
        store = make_store([FakeResponse(200, text="")])
        result = store._request("GET", "/test")
        assert result == {}

    def test_http_error_raises(self):
        """Network errors raise VectorStoreError."""
        store = make_store([])
        store.client._responses = []
        with patch.object(store.client, "request", side_effect=httpx.ConnectError("connection refused")):
            with pytest.raises(VectorStoreError, match="Weaviate unavailable"):
                store._request("GET", "/test")


class TestEnsureCollection:
    def test_creates_collection_when_missing(self):
        """Creates collection when schema doesn't exist."""
        store = make_store([
            FakeResponse(404),  # GET schema not found
            FakeResponse(200, json_data={"class": COLLECTION}),  # POST create
        ])
        result = store.ensure_collection()
        assert result["class"] == COLLECTION
        assert store.client.calls[1][0] == "POST"
        assert store.client.calls[1][1] == "/v1/schema"

    def test_reuses_valid_collection(self):
        """Returns schema if it matches expectations."""
        schema = {
            "class": COLLECTION,
            "vectorizer": "none",
            "properties": [
                {"name": "profileId", "dataType": ["text"], "tokenization": "field"},
                {"name": "consent", "dataType": ["boolean"]},
                {"name": "embeddingVersion", "dataType": ["text"]},
                {"name": "audioSha256", "dataType": ["text"]},
                {"name": "device", "dataType": ["text"]},
                {"name": "durationSeconds", "dataType": ["number"]},
                {"name": "inferenceMs", "dataType": ["number"]},
            ],
            "vectorIndexConfig": {"distance": "cosine"},
        }
        store = make_store([FakeResponse(200, json_data=schema)])
        result = store.ensure_collection()
        assert result == schema

    def test_rejects_wrong_vectorizer(self):
        """Raises if existing collection has wrong vectorizer."""
        store = make_store([FakeResponse(200, json_data={"vectorizer": "text2vec-transformers"})])
        with pytest.raises(VectorStoreError, match="wrong vectorizer"):
            store.ensure_collection()


class TestInsert:
    def test_insert_success(self):
        """Insert returns a valid UUID string."""
        store = make_store([
            FakeResponse(200, json_data={"vectorizer": "none"}),  # ensure_collection
            FakeResponse(200, json_data={"id": "test-uuid"}),  # insert
        ])
        result = store.insert(
            vector=valid_vector(),
            version=EMBEDDING_VERSION,
            consent=True,
            profile_id="user-1",
            audio_sha256="a" * 64,
        )
        assert isinstance(result, str)
        assert len(result) == 36  # UUID format

    def test_insert_rejects_no_consent(self):
        """Insert requires explicit consent=True."""
        store = make_store([])
        with pytest.raises(ValueError, match="consent"):
            store.insert(
                vector=valid_vector(),
                version=EMBEDDING_VERSION,
                consent=False,
                profile_id="user-1",
                audio_sha256="a" * 64,
            )

    def test_insert_rejects_bad_version(self):
        """Insert rejects unsupported embedding version."""
        store = make_store([])
        with pytest.raises(ValueError, match="unsupported"):
            store.insert(
                vector=valid_vector(),
                version="bad-version",
                consent=True,
                profile_id="user-1",
                audio_sha256="a" * 64,
            )

    def test_insert_rejects_bad_vector(self):
        """Insert rejects invalid vector dimensions."""
        store = make_store([])
        with pytest.raises(ValueError, match="192"):
            store.insert(
                vector=[1.0] * 100,  # wrong dimension
                version=EMBEDDING_VERSION,
                consent=True,
                profile_id="user-1",
                audio_sha256="a" * 64,
            )


class TestSearch:
    def test_search_with_results(self):
        """Search returns parsed results."""
        results = FakeResponse(200, json_data={
            "data": {
                "Get": {
                    COLLECTION: [
                        {
                            "profileId": "other-user",
                            "audioSha256": "b" * 64,
                            "device": "cuda:0",
                            "_additional": {"distance": 0.5},
                        }
                    ]
                }
            }
        })
        store = make_store([
            FakeResponse(200, json_data={"vectorizer": "none"}),  # ensure_collection
            results,  # search
        ])
        hits = store.search(
            vector=valid_vector(),
            version=EMBEDDING_VERSION,
            consent=True,
            limit=5,
        )
        assert len(hits) == 1
        assert hits[0]["profileId"] == "other-user"
        assert hits[0]["distance"] == 0.5

    def test_search_rejects_no_consent(self):
        """Search requires explicit consent=True."""
        store = make_store([])
        with pytest.raises(ValueError, match="consent"):
            store.search(
                vector=valid_vector(),
                version=EMBEDDING_VERSION,
                consent=False,
                limit=5,
            )

    @pytest.mark.parametrize("bad_limit", [0, 101, -1, "five", 1.5])
    def test_search_invalid_limit(self, bad_limit):
        """Search rejects invalid limit values."""
        store = make_store([])
        with pytest.raises(ValueError, match="limit"):
            store.search(
                vector=valid_vector(),
                version=EMBEDDING_VERSION,
                consent=True,
                limit=bad_limit,
            )

    def test_search_excludes_profile(self):
        """Search with profile_id adds NotEqual filter."""
        results = FakeResponse(200, json_data={"data": {"Get": {COLLECTION: []}}})
        store = make_store([
            FakeResponse(200, json_data={"vectorizer": "none"}),
            results,
        ])
        store.search(
            vector=valid_vector(),
            version=EMBEDDING_VERSION,
            consent=True,
            profile_id="my-user",
            limit=5,
        )
        # Check the GraphQL query contains the profile filter
        graphql_call = store.client.calls[1]
        assert "NotEqual" in str(graphql_call[2])
        assert "my-user" in str(graphql_call[2])


class TestDeleteAndExists:
    def test_delete_calls_api(self):
        """Delete sends DELETE request."""
        store = make_store([FakeResponse(200, json_data={})])
        store.delete("some-uuid")
        assert store.client.calls[0][0] == "DELETE"
        assert "objects" in store.client.calls[0][1]


class TestContextManager:
    def test_context_manager(self):
        store = make_store([])
        with store as s:
            assert s is store
        assert store.client.closed


class TestClose:
    def test_close(self):
        """Close doesn't raise."""
        store = make_store([])
        store.close()
        assert store.client.closed
