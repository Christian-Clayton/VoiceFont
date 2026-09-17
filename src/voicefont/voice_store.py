"""Weaviate-backed voice embedding store with explicit consent and no auto-vectorizer."""
from __future__ import annotations

import json
import logging
import re
import uuid
from urllib.parse import urlsplit

import httpx

from voicefont.embeddings import EMBEDDING_VERSION, require_consent, validate_embedding

logger = logging.getLogger(__name__)

COLLECTION = "VoiceFontSpeakerEcapaV1"
DEFAULT_ENDPOINT = "http://127.0.0.1:18080"
MAX_RESPONSE_BYTES = 1024 * 1024


class VectorStoreError(RuntimeError):
    pass


class WeaviateVoiceStore:
    """Store speaker embeddings in Weaviate with consent and provenance."""

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, *, timeout: float = 5.0,
                 transport=None):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or not parsed.port):
            raise ValueError("loopback HTTP endpoint required")
        self.client = httpx.Client(base_url=endpoint.rstrip("/"), timeout=timeout,
                                   trust_env=False, follow_redirects=False,
                                   transport=transport)

    def _request(self, method, path, body=None, *, missing_ok=False):
        try:
            with self.client.stream(method, path, json=body) as resp:
                if resp.status_code == 404 and missing_ok:
                    return None
                if not 200 <= resp.status_code < 300:
                    raise VectorStoreError(f"HTTP {resp.status_code}")
                data = bytearray()
                for chunk in resp.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise VectorStoreError("response too large")
                return json.loads(data) if data else {}
        except (httpx.HTTPError, ValueError) as e:
            raise VectorStoreError(f"Weaviate unavailable: {type(e).__name__}") from e

    def ensure_collection(self):
        """Create the collection with vectorizer=none (caller provides vectors)."""
        schema = self._request("GET", f"/v1/schema/{COLLECTION}", missing_ok=True)
        if schema:
            cfg = schema.get("vectorIndexConfig", {})
            if cfg.get("distance") != "cosine":
                raise VectorStoreError("existing collection has wrong distance metric")
            if schema.get("vectorizer") != "none":
                raise VectorStoreError("existing collection has wrong vectorizer")
            return schema

        body = {
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
        self._request("POST", "/v1/schema", body)
        return body

    def insert(self, *, vector: list, version: str, consent: bool,
               profile_id: str, audio_sha256: str, device: str = "cuda:0",
               duration_seconds: float = 0.0, inference_ms: float = 0.0) -> str:
        """Insert an embedding. Returns the object ID."""
        require_consent(consent)
        validate_embedding(vector, version)
        self.ensure_collection()

        obj_id = str(uuid.uuid4())
        body = {
            "class": COLLECTION,
            "id": obj_id,
            "vector": vector,
            "properties": {
                "profileId": profile_id,
                "consent": consent,
                "embeddingVersion": version,
                "audioSha256": audio_sha256,
                "device": device,
                "durationSeconds": duration_seconds,
                "inferenceMs": inference_ms,
            },
        }
        self._request("POST", "/v1/objects", body)
        return obj_id

    def search(self, *, vector: list, version: str, consent: bool,
               profile_id: str | None = None, limit: int = 5) -> list[dict]:
        """Cosine-similarity search with consent/version filters."""
        require_consent(consent)
        validate_embedding(vector, version)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be 1-100")
        self.ensure_collection()

        # Build filter operands
        operands = [
            '{"path": ["consent"], "operator": "Equal", "valueBoolean": true}',
            '{"path": ["embeddingVersion"], "operator": "Equal", "valueText": "%s"}' % version,
        ]
        if profile_id:
            operands.append(
                '{"path": ["profileId"], "operator": "NotEqual", "valueText": "%s"}' % profile_id
            )

        query = {
            "query": """
            {
                Get {
                    %s(
                        nearVector: {vector: [%s]}
                        limit: %d
                        where: {
                            operator: And
                            operands: [%s]
                        }
                    ) {
                        profileId
                        audioSha256
                        device
                        durationSeconds
                        inferenceMs
                        _additional { distance }
                    }
                }
            }
            """ % (COLLECTION, ",".join(str(v) for v in vector), limit, ", ".join(operands))
        }
        result = self._request("POST", "/v1/graphql", query)
        objects = result.get("data", {}).get("Get", {}).get(COLLECTION, [])
        return [
            {
                "profileId": o.get("profileId"),
                "audioSha256": o.get("audioSha256"),
                "device": o.get("device"),
                "distance": o.get("_additional", {}).get("distance"),
            }
            for o in objects
        ]

    def delete(self, obj_id: str) -> None:
        self._request("DELETE", f"/v1/objects/{COLLECTION}/{obj_id}")

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
