"""The live lab generator (P4 V9, D-36): one call through the LLM seam per lab, so the spend is booked and the cap applies (constraint 8).

It is untrusted by construction, like the fake: whatever it returns goes through the AST checker and the verifier, and nothing it returns
reaches the client except as a `VerifiedArtifact`. The prompt gives the model the contract's parameters and the stored passage that states
the formula (the evidence the lab is grounded in), and the language the checker accepts. It does **not** give the reference cases or the
properties: those are what the verifier tests the answer against, so a model that merely echoed them would prove nothing about the formula.

`generator_id` names the prompt version; a stored lab made under another id is marked stale (D-41). Bump it with any prompt change.
"""

from __future__ import annotations

import asyncio
import re

from anyio import from_thread

from api.core.errors import ProviderUnavailable
from api.genui.text import normalise
from api.labs.contract import LabContract
from api.labs.generator import LabGenerator
from api.llm.service import LLMService
from api.llm.types import LLMRequest
from api.stores.doc_store import DocStore

MAX_TOKENS = 700
LIVE_PROMPT_VERSION = "live-lab-2"

SYSTEM = """You write exactly one small pure JavaScript function for an interactive lab. Reply with the function source only: no markdown, no code fence, no comments, no explanation, no draft and no correction. Write the function once, as your final answer, and nothing after it.

The function is `function lab(p) { ... }`. `p` holds the parameters as numbers (p.name). It must return one finite number for every combination of parameter values in the stated ranges, so write it to be numerically stable (for example, avoid exp overflow).

The language is deliberately tiny and everything else is rejected:
- numbers and booleans only: no strings, arrays, objects, template literals, closures, classes, `new`, `this`, regex, or computed property access;
- `const` and `let` locals, `if`/`else`, `return`, `for` loops with integer literal bounds up to 1000 (at most two nested), `while` is not allowed;
- operators: + - * / % ** < <= > >= == != === !== && || ! and assignment (= += -= *= /=, ++, --);
- only these Math functions, always written with the `Math.` prefix (Math.max, Math.exp, ...): abs, min, max, pow, sqrt, exp, log, log1p, expm1, sin, cos, tan, tanh, floor, ceil, round, sign, hypot, atan, atan2, and Math.PI, Math.E; a bare `max(...)` or `exp(...)` is rejected;
- do not name a local `p`, `Math`, `lab`, or any global.

Implement exactly the formula the passage states, using the parameter meanings given."""


def lab_prompt(contract: LabContract, passage: str) -> str:
    params = "\n".join(
        f"- p.{q.name}: {q.label}, from {q.min:g} to {q.max:g}" + (f" ({q.unit})" if q.unit else "")
        for q in contract.parameters
    )
    return (
        f"Lab: {contract.title}\n"
        f"The function returns: {contract.output_label}\n"
        f"Parameters:\n{params}\n\n"
        f"The stored passage that states the formula:\n\"\"\"\n{passage}\n\"\"\"\n\n"
        "Write the function."
    )


_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n```\s*$", re.DOTALL)


def strip_fence(text: str) -> str:
    """A reply wrapped in a code fence is unwrapped; anything else is returned as it is (the checker decides)."""
    text = text.strip()
    m = _FENCE.match(text)
    return m.group(1).strip() if m else text


class LiveLabGenerator(LabGenerator):
    generator_id = LIVE_PROMPT_VERSION

    def __init__(self, llm: LLMService, docs: DocStore, tier: str = "standard"):
        self._llm = llm
        self._docs = docs
        self._tier = tier

    def _passage(self, contract: LabContract) -> str:
        phrase = normalise(contract.source_phrase)
        for chunk in sorted(self._docs.all_chunks(), key=lambda c: (c.doc_id, c.ordinal)):
            if phrase in normalise(chunk.text):
                return " ".join(chunk.text.split())
        raise ProviderUnavailable("No stored passage states this formula, so there is nothing to generate from.")

    def generate(self, contract: LabContract) -> str:
        passage = self._passage(contract)
        request = LLMRequest(
            prompt=lab_prompt(contract, passage),
            system=SYSTEM,
            purpose="generate",
            tier=self._tier,  # type: ignore[arg-type]
            max_tokens=MAX_TOKENS,
        )
        # compose_lab is synchronous, so this runs in a worker thread. Under FastAPI that is an AnyIO worker: the call is handed back to the
        # app's own event loop, where the providers' HTTP clients live (a client used from a second loop fails with "Event loop is closed").
        # With no app loop (a script or a test calling it directly) it runs on a loop of its own.
        try:
            result = from_thread.run(self._llm.complete, request)
        except RuntimeError:  # not an AnyIO worker thread
            result = asyncio.run(self._llm.complete(request))
        return strip_fence(result.text)
