"""The two RAGAS non-LLM context metrics, behind one module (D-15: RAGAS is used as a library).

    NonLLMContextRecall                    |relevant retrieved contexts| / |reference contexts|
    NonLLMContextPrecisionWithReference    precision of the retrieved contexts, by string similarity

Both compare strings (Levenshtein distance via `rapidfuzz`); neither calls an LLM. The API used here
is from the current stable RAGAS docs (ragas.metrics, ragas.dataset_schema.SingleTurnSample,
`await metric.single_turn_ascore(sample)`).

RAGAS is imported lazily and may not be installed: it pulls in about 94 packages. When it is absent
the runner records these metrics as None with a reason. It never substitutes a different number.
"""

from __future__ import annotations

from dataclasses import dataclass


class RagasUnavailable(RuntimeError):
    """RAGAS (or rapidfuzz, which one metric needs) is not installed."""


@dataclass(frozen=True)
class ContextMetrics:
    context_recall: float
    context_precision: float


def ragas_status() -> dict[str, object]:
    try:
        import importlib.metadata as md

        import ragas  # noqa: F401  # pyright: ignore[reportMissingImports]
        import rapidfuzz  # noqa: F401  # pyright: ignore[reportMissingImports]

        return {"available": True, "version": md.version("ragas")}
    except ImportError as exc:
        return {"available": False, "reason": f"not installed: {exc.name}"}


async def non_llm_context_metrics(retrieved: list[str], reference: list[str]) -> ContextMetrics:
    try:
        from ragas.dataset_schema import SingleTurnSample  # pyright: ignore[reportMissingImports]
        from ragas.metrics import (  # pyright: ignore[reportMissingImports]
            NonLLMContextPrecisionWithReference,
            NonLLMContextRecall,
        )
    except ImportError as exc:
        raise RagasUnavailable(f"ragas is not installed ({exc.name})") from exc

    sample = SingleTurnSample(retrieved_contexts=retrieved, reference_contexts=reference)
    recall = await NonLLMContextRecall().single_turn_ascore(sample)
    precision = await NonLLMContextPrecisionWithReference().single_turn_ascore(sample)
    return ContextMetrics(float(recall), float(precision))
