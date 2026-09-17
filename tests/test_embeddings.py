"""Small validation tests; generated vectors are not speaker-quality evidence."""
import pytest

from voicefont.embeddings import EMBEDDING_DIM, EMBEDDING_VERSION, validate_embedding, require_consent


def test_valid_embedding_is_normalized():
    result = validate_embedding([2.0] + [0.0] * (EMBEDDING_DIM - 1), EMBEDDING_VERSION)
    assert result == [1.0] + [0.0] * (EMBEDDING_DIM - 1)


@pytest.mark.parametrize('vector', [[0.0]*192, [1.0]*191, [float('nan')]*192, [float('inf')]*192, [True]*192])
def test_invalid_vectors_rejected(vector):
    with pytest.raises(ValueError):
        validate_embedding(vector, EMBEDDING_VERSION)


def test_version_required():
    with pytest.raises(ValueError):
        validate_embedding([1.0]*192, 'acoustic-v1')


@pytest.mark.parametrize('consent', [None, False, 'true', 1, {}])
def test_explicit_boolean_consent_required(consent):
    with pytest.raises(ValueError):
        require_consent(consent)


def test_true_consent_accepted():
    require_consent(True)
