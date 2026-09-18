"""Quick Weaviate search smoke test using real ECAPA embedding."""
import sys

sys.path.insert(0, 'src')

from pathlib import Path

from voicefont.embeddings import CudaSpeakerEncoder
from voicefont.voice_store import WeaviateVoiceStore

data = Path('data/embeddings')
with CudaSpeakerEncoder(data, consent=True) as enc:
    r = enc.encode(data / 'fixtures' / 'kathleen' / '0.wav', consent=True)

print(f'version={r.version} dim={r.dimension} device={r.device}')

store = WeaviateVoiceStore('http://127.0.0.1:18080')
store.ensure_collection()

# Insert two objects
obj1 = store.insert(
    vector=r.vector, version=r.version, consent=True,
    profile_id='kathleen', audio_sha256=r.audio_sha256,
    device=r.device, inference_ms=r.inference_ms,
)
print(f'Inserted 1: {obj1}')

with CudaSpeakerEncoder(data, consent=True) as enc2:
    r2 = enc2.encode(data / 'fixtures' / 'flemishguy' / '0.wav', consent=True)

obj2 = store.insert(
    vector=r2.vector, version=r2.version, consent=True,
    profile_id='flemishguy', audio_sha256=r2.audio_sha256,
    device=r2.device, inference_ms=r2.inference_ms,
)
print(f'Inserted 2: {obj2}')

# Search without exclusion
results = store.search(vector=r.vector, version=r.version, consent=True, limit=5)
print(f'Search (all): {len(results)}')
for res in results:
    print(f'  - {res["profileId"]}: distance={res["distance"]:.4f}')

# Search excluding kathleen
results2 = store.search(
    vector=r.vector, version=r.version, consent=True,
    profile_id='kathleen', limit=5,
)
print(f'Search (exclude kathleen): {len(results2)}')
for res in results2:
    print(f'  - {res["profileId"]}: distance={res["distance"]:.4f}')

# Cleanup
store.delete(obj1)
store.delete(obj2)
store.close()
print('OK')
