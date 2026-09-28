import json

import pytest

from sonic_config_version.errors import ValidationError
from sonic_config_version.snapshot.normalizer import digest, normalize


def test_normalization_sorts_objects_preserves_arrays_and_types():
    value = {"z": [3, 1], "a": {"text": "café", "bool": True, "number": 4}}
    rendered = normalize(value)
    assert rendered == '{"a":{"bool":true,"number":4,"text":"café"},"z":[3,1]}\n'.encode()
    assert normalize(json.loads(rendered)) == rendered


def test_normalization_has_one_trailing_newline():
    assert normalize('{"a":1}\n\n') == b'{"a":1}\n'


def test_normalization_rejects_non_object_and_nan():
    with pytest.raises(ValidationError):
        normalize([1, 2])
    with pytest.raises(ValidationError):
        normalize({"value": float("nan")})


def test_digest_is_stable():
    assert digest(normalize({"b": 2, "a": 1})) == digest(normalize({"a": 1, "b": 2}))
