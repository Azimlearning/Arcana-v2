"""The generated models are the server side of the wire contract: they must fail closed."""

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from api.genui.generated import BlockMeta, CitedSummary, PanelSpec, StreamEvent


def block(**meta_overrides: object) -> dict:
    meta = {"status": "ready", "error": None, **meta_overrides}
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
        PanelSpec.model_validate({"id": "chat", "width": bad})


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError) as exc:
        CitedSummary.model_validate({**block(), "surprise": 1})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_nan_is_rejected():
    with pytest.raises(ValidationError):
        PanelSpec.model_validate_json(json.dumps({"id": "chat", "width": float("nan")}))


def test_error_field_is_required_not_defaulted():
    meta = {"status": "ready"}
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


# ── TurnTrace (P1 task A2) ────────────────────────────────────────────────────

from api.genui.generated import AgentStep, TurnTrace  # noqa: E402


def step(**overrides: object) -> dict:
    return {"hop": 0, "agent": "orchestrator", "status": "ok", "tokens": 12, "latencyMs": 3, "note": None, **overrides}


def trace(**overrides: object) -> dict:
    return {"turnId": "t1", "steps": [step(), step(hop=1, agent="research")], "hopsUsed": 2, "tokensUsed": 24, "outcome": "answered", "composition": [], **overrides}


def test_a_valid_trace_validates_from_dict_and_json():
    assert len(TurnTrace.model_validate(trace()).steps) == 2
    assert TurnTrace.model_validate_json(json.dumps(trace())).outcome == "answered"


@pytest.mark.parametrize("field", ["hop", "tokens", "latencyMs"])
@pytest.mark.parametrize("bad", ["1", True, 1.0])
def test_step_numbers_do_not_coerce(field: str, bad: object):
    with pytest.raises(ValidationError):
        AgentStep.model_validate(step(**{field: bad}))


@pytest.mark.parametrize("field", ["hopsUsed", "tokensUsed"])
def test_trace_totals_do_not_coerce(field: str):
    with pytest.raises(ValidationError):
        TurnTrace.model_validate(trace(**{field: "3"}))


@pytest.mark.parametrize(
    ("overrides", "where"),
    [({"agent": "wizard"}, "agent"), ({"status": "great"}, "status")],
)
def test_step_enums_are_closed(overrides: dict, where: str):
    with pytest.raises(ValidationError) as exc:
        AgentStep.model_validate(step(**overrides))
    assert exc.value.errors()[0]["loc"] == (where,)


def test_every_roster_role_is_a_valid_agent_name():
    for name in ("orchestrator", "research", "graph", "fact_checker", "composer", "studio", "lab_builder"):
        AgentStep.model_validate(step(agent=name))


def test_trace_outcome_is_closed_and_extras_are_rejected():
    with pytest.raises(ValidationError):
        TurnTrace.model_validate(trace(outcome="maybe"))
    with pytest.raises(ValidationError) as exc:
        TurnTrace.model_validate({**trace(), "surprise": 1})
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


def test_a_step_note_may_be_null_or_text_but_not_missing():
    assert AgentStep.model_validate(step(note="hop budget reached")).note == "hop budget reached"
    missing = step()
    del missing["note"]
    with pytest.raises(ValidationError):
        AgentStep.model_validate(missing)


def test_a_composition_decision_has_a_closed_list_of_reason_codes():
    from api.genui.generated import ComponentDecision

    decision = {"component": "GraphView", "offered": False, "reasons": ["no_grounded_edge"]}
    assert ComponentDecision.model_validate(decision).reasons == ["no_grounded_edge"]
    for bad in ({**decision, "reasons": ["the quote said something private"]}, {**decision, "offered": "no"}, {**decision, "extra": 1}):
        with pytest.raises(ValidationError):
            ComponentDecision.model_validate(bad)
    assert TurnTrace.model_validate(trace(composition=[decision])).composition[0].component == "GraphView"
    with pytest.raises(ValidationError):  # the record is required: an old-shaped body is not a trace (the route adapts it)
        TurnTrace.model_validate({k: v for k, v in trace().items() if k != "composition"})
