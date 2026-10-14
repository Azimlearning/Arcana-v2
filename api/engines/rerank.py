"""The cross-encoder re-rank engine (P3-lite, D-37): a pretrained MiniLM cross-encoder run locally through ONNX.

Not trained by this project (D-37: there is no data worth training on; a model trained on LLM-judged labels would measure the judge). The model
is `Xenova/ms-marco-MiniLM-L-6-v2` (Apache-2.0, about 80 MB), trained by others on MS MARCO passage ranking, served by `fastembed`'s
`TextCrossEncoder` (read the current docs of the library before changing this: `rerank(query, documents)` yields one score per document, higher is
more relevant). The runtime is the optional `engines` extra; without it, or without the weights, `is_available()` is False and the heuristic stands.
"""

from __future__ import annotations

from typing import Any

from api.engines.base import RerankEngine

DEFAULT_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class CrossEncoderRerankEngine(RerankEngine):
    name = "cross-encoder-minilm-l6"

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: str | None = None):
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._encoder: Any = None
        self._failed: str | None = None

    def _load(self) -> Any:
        if self._encoder is not None:
            return self._encoder
        if self._failed is not None:
            raise RuntimeError(self._failed)
        try:
            from fastembed.rerank.cross_encoder import (
                TextCrossEncoder,
            )  # the optional `engines` extra

            self._encoder = TextCrossEncoder(model_name=self._model_name, cache_dir=self._cache_dir)
        except Exception as exc:
            self._failed = f"{type(exc).__name__}: {exc}"[:200]
            raise RuntimeError(self._failed) from exc
        return self._encoder

    def is_available(self) -> bool:
        try:
            self._load()
        except Exception:
            return False
        return True

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoder = self._load()
        query = str(payload["query"])
        texts = [str(t) for t in payload["texts"]]
        return {"scores": [float(s) for s in encoder.rerank(query, texts)]}
