"""The generated models are the server side of the wire contract: they must fail closed."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from api.genui.generated import BlockMeta, CitedSummary, StreamEvent


def block(**meta_overrides: object) -> dict:
    meta = {"panel": "chat", "order": 0, "status": "ready", "error": None, **meta_overrides}
    return {
        "type": "CitedSummary",
        "id": "b1",
        "meta": meta,
        "data": {"segments": [], "citations": []},
    }


def test_valid_block_validates_from_dict_and_json():
    assert CitedSummary.model_validate(block()).id == "b1"
    assert CitedSummary.model_validate_json(json.dumps(block())).id == "b1"


@pytest.mark.parametrize("bad", ["1", True, 1.0])
def test_int_fields_do_not_coerce(bad: object):
    with pytest.raises(ValidationError):
        BlockMeta.model_validate({"panel": "chat", "status": "ready", "error": None, "order": bad})


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError) as exc:
        CitedSummary.model_validate({**block(), "surprise": 1})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_nan_is_rejected():
    with pytest.raises(ValidationError):
        CitedSummary.model_validate_json(json.dumps(block(order=float("nan"))))


def test_error_field_is_required_not_defaulted():
    meta = {"panel": "chat", "order": 0, "status": "ready"}
    with pytest.raises(ValidationError):
        BlockMeta.model_validate(meta)


def test_stream_event_discriminates_on_type():
    adapter = TypeAdapter(StreamEvent)
    assert adapter.validate_python({"type": "done"}).type == "done"
    assert adapter.validate_python({"type": "block", "block": block()}).type == "block"
    err = {"code": "internal", "message": "m", "issues": [], "retryable": False}
    assert adapter.validate_python({"type": "error", "error": err}).type == "error"


def test_stream_event_rejects_an_unknown_tag():
    with pytest.raises(ValidationError) as exc:
        TypeAdapter(StreamEvent).validate_python({"type": "nope"})
    assert exc.value.errors()[0]["type"] == "union_tag_invalid"
