"""Bounded loopback-only Weaviate REST adapter; bring your own consented vectors.

Caller owns consent truth and profile ownership. Local boolean gates are not an
identity/authorization system. Never expose the anonymous DB outside loopback.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from urllib.parse import urlsplit

import httpx

from voicefont.embeddings import EMBEDDING_VERSION, require_consent, validate_embedding

COLLECTION = "VoiceFontSpeakerEcapaV1"
DEFAULT_ENDPOINT = "http://127.0.0.1:18080"
MAX_RESPONSE_BYTES = 1024 * 1024


class VectorStoreUnavailable(RuntimeError):
    """Local vector service failed; response bodies/credentials are never logged."""


class WeaviateStore:
    def __init__(self, endpoint=DEFAULT_ENDPOINT, *, timeout=5.0, transport=None):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.port is None):
            raise ValueError("explicit loopback HTTP endpoint and port required")
        if not isinstance(timeout, (float, int)) or not 0 < timeout <= 30:
            raise ValueError("timeout must be 0-30 seconds")
        self.client = httpx.Client(base_url=endpoint.rstrip('/'), timeout=timeout,
                                   trust_env=False, follow_redirects=False, transport=transport)

    def _request(self, method, path, body=None, *, missing_ok=False):
        try:
            with self.client.stream(method, path, json=body) as response:
                if response.status_code == 404 and missing_ok:
                    return None
                if not 200 <= response.status_code < 300:
                    raise VectorStoreUnavailable(f"local Weaviate HTTP {response.status_code}")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise VectorStoreUnavailable("local Weaviate response exceeds limit")
                return json.loads(data) if data else {}
        except (httpx.HTTPError, ValueError) as exc:
            raise VectorStoreUnavailable("local Weaviate unavailable or invalid response") from exc

    def ensure_collection(self):
        """Explicit provisioning operation; refuses incompatible existing schemas."""
        schema = self._request('GET', f'/v1/schema/{COLLECTION}', missing_ok=True)
        properties = [
            {'name': 'profileId', 'dataType': ['text'], 'tokenization': 'field'},
            {'name': 'audioSha256', 'dataType': ['text'], 'tokenization': 'field'},
            {'name': 'embeddingVersion', 'dataType': ['text'], 'tokenization': 'field'},
            {'name': 'consent', 'dataType': ['boolean']},
        ]
        if schema is not None:
            existing = {x['name']: (x['dataType'], x.get('tokenization'))
                        for x in schema.get('properties', [])}
            wanted = {x['name']: (x['dataType'], x.get('tokenization')) for x in properties}
            if (schema.get('vectorizer') != 'none' or schema.get('vectorConfig')
                    or schema.get('vectorIndexConfig', {}).get('distance') != 'cosine'
                    or any(existing.get(key) != value for key, value in wanted.items())):
                raise VectorStoreUnavailable("incompatible collection schema; no automatic migration")
            return
        self._request('POST', '/v1/schema', {
            'class': COLLECTION, 'description': EMBEDDING_VERSION,
            'vectorizer': 'none', 'vectorIndexType': 'hnsw',
            'vectorIndexConfig': {'distance': 'cosine'}, 'properties': properties,
        })

    def insert(self, vector, *, version, consent, profile_id, audio_sha256):
        require_consent(consent)
        vector = validate_embedding(vector, version)
        if not isinstance(profile_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', profile_id):
            raise ValueError("profile_id must be a bounded opaque identifier")
        if not isinstance(audio_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', audio_sha256):
            raise ValueError("audio_sha256 must be a SHA256 digest")
        identity = str(uuid.uuid5(uuid.NAMESPACE_URL, f'voicefont:{version}:{profile_id}:{audio_sha256}'))
        self._request('POST', '/v1/objects', {
            'class': COLLECTION, 'id': identity, 'vector': vector,
            'properties': {'profileId': profile_id, 'audioSha256': audio_sha256,
                           'embeddingVersion': version, 'consent': True},
        })
        return identity

    def search(self, vector, *, version, consent, limit=5, exclude_audio_sha256=None):
        require_consent(consent)
        vector = validate_embedding(vector, version)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("search limit must be an integer from 1 to 100")
        operands = [
            '{path:["consent"],operator:Equal,valueBoolean:true}',
            '{path:["embeddingVersion"],operator:Equal,valueText:' + json.dumps(version) + '}',
        ]
        if exclude_audio_sha256 is not None:
            if not re.fullmatch(r'[0-9a-f]{64}', exclude_audio_sha256):
                raise ValueError("exclude_audio_sha256 must be a SHA256 digest")
            operands.append('{path:["audioSha256"],operator:NotEqual,valueText:'
                            + json.dumps(exclude_audio_sha256) + '}')
        query = ('{Get{' + COLLECTION + '(nearVector:{vector:' + json.dumps(vector)
                 + '},limit:' + str(limit) + ',where:{operator:And,operands:['
                 + ','.join(operands) + ']}){profileId audioSha256 embeddingVersion consent '
                 + '_additional{id distance}}}}')
        result = self._request('POST', '/v1/graphql', {'query': query})
        if result.get('errors'):
            raise VectorStoreUnavailable("local Weaviate query rejected")
        try:
            rows = result['data']['Get'][COLLECTION]
            if not isinstance(rows, list) or len(rows) > limit:
                raise ValueError
            for row in rows:
                if (row['consent'] is not True or row['embeddingVersion'] != version
                        or not math.isfinite(row['_additional']['distance'])):
                    raise ValueError
            return rows
        except (KeyError, TypeError, ValueError) as exc:
            raise VectorStoreUnavailable("invalid local Weaviate search results") from exc

    def delete(self, object_id: str):
        """Deletion remains available after consent withdrawal. Idempotent."""
        identity = str(uuid.UUID(object_id))
        self._request('DELETE', f'/v1/objects/{COLLECTION}/{identity}', missing_ok=True)

    def exists(self, object_id: str) -> bool:
        identity = str(uuid.UUID(object_id))
        return self._request('GET', f'/v1/objects/{COLLECTION}/{identity}', missing_ok=True) is not None

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
