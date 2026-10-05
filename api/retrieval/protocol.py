"""The retrieval protocol stamp: every constant that shapes what the five arms return.

Written into every benchmark results file, so a result can always be tied to the exact settings that
produced it. These values are FROZEN before gold annotation (D-20); changing one needs a declared
amendment and a version bump, and results from different stamps are never pooled.
"""

from __future__ import annotations

import hashlib
from typing import Any

from api.ingestion.chunk import DEFAULT_OVERLAP_CHARS, DEFAULT_TARGET_CHARS
from api.ingestion.extract import EXTRACTION_SYSTEM
from api.retrieval import entities, graph
from api.retrieval.types import RRF_K, TOP_K


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def protocol_stamp() -> dict[str, Any]:
    return {
        "rrf_k": RRF_K,
        "top_k": TOP_K,
        "chunking": {"target_chars": DEFAULT_TARGET_CHARS, "overlap_chars": DEFAULT_OVERLAP_CHARS},
        "sparse": {"library": "rank_bm25.BM25Okapi", "tokenizer": "ascii [a-z0-9]+, lowercase"},
        "graph": {
            "scoring_version": graph.GRAPH_SCORING_VERSION,
            "direct_weight": graph.DIRECT_WEIGHT,
            "neighbor_weight": graph.NEIGHBOR_WEIGHT,
            "hops": 1,
            "tie_break": "score, edge support, document order",
        },
        "entity_resolution": {
            "exact_weight": entities.EXACT_WEIGHT,
            "approx_weight": entities.APPROX_WEIGHT,
            "max_approx": entities.MAX_APPROX,
            "min_containment": entities.MIN_CONTAINMENT,
            "max_ngram": entities.MAX_NGRAM,
            "stopwords_sha": _sha(" ".join(sorted(entities.STOPWORDS))),
        },
        "extraction": {"prompt_sha": _sha(EXTRACTION_SYSTEM)},
    }
