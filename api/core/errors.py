"""The one error shape. Every failure the client can see leaves as an ErrorEnvelope.

ErrorEnvelope, FieldIssue and ErrorCode are generated from packages/schema (api/genui/generated.py);
this module only builds them. An unexpected exception becomes a generic "internal" envelope: the
detail goes to the log, never to the client.
"""

from __future__ import annotations

from collections.abc import Sequence

from api.genui.generated import ErrorCode, ErrorEnvelope, FieldIssue


class ArcanaError(Exception):
    code: ErrorCode = "internal"
    retryable: bool = False

    def __init__(self, message: str, issues: Sequence[FieldIssue] = ()):
        super().__init__(message)
        self.message = message
        self.issues = list(issues)

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(code=self.code, message=self.message, issues=self.issues, retryable=self.retryable)


class ValidationFailed(ArcanaError):
    code = "validation_failed"


class BadRequest(ArcanaError):
    code = "bad_request"


class NotFound(ArcanaError):
    code = "not_found"


class PatternRefused(ArcanaError):
    """A saved view cannot be applied. `reason` is `precondition_not_met`, `template_changed` or `document_missing`;
    it travels as the path of the one issue, with a plain sentence as its message."""

    code = "pattern_refused"

    def __init__(self, reason: str, message: str):
        super().__init__("This saved view cannot be shown.", [FieldIssue(path=reason, message=message)])
        self.reason = reason


class IngestFailed(BadRequest):
    """A document could not be ingested (unreadable PDF, no extractable text, bad model output)."""


class BudgetExhausted(ArcanaError):
    """The per-turn token budget ran out. The turn still terminates, with this envelope."""

    code = "budget_exhausted"


class SpendCapExceeded(ArcanaError):
    """The monthly LLM cap would be exceeded; refused before the call was sent."""

    code = "spend_cap_exceeded"


class ProviderUnavailable(ArcanaError):
    code = "provider_unavailable"
    retryable = True


class ModelOutputInvalid(ProviderUnavailable):
    """The model answered, but not in a usable or grounded form. A server-side fault the user can
    retry, so it must not be reported as validation_failed ("your input was invalid")."""


def envelope_from_exception(exc: BaseException) -> ErrorEnvelope:
    """Map any exception to the wire envelope without leaking internals."""
    if isinstance(exc, ArcanaError):
        return exc.to_envelope()
    return ErrorEnvelope(code="internal", message="An internal error occurred.", issues=[], retryable=False)


# Transport mapping for non-stream endpoints. In a stream the envelope itself carries the failure.
HTTP_STATUS: dict[str, int] = {
    "validation_failed": 422,
    "bad_request": 400,
    "not_found": 404,
    "budget_exhausted": 429,
    "spend_cap_exceeded": 402,
    "provider_unavailable": 503,
    "pattern_refused": 409,
    "internal": 500,
}
