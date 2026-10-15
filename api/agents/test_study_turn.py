"""The Studio's learning tools in a turn (P5 S2, D-42): the `study` intent, what the request names, and a turn through the real graph
that ends at the Composer with a validated StudySet beside the grounded answer. The vault is the handmade one of
`api/vault/test_study.py`; no model call is paid (the fake responder)."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine

from api.agents.orchestrator import classify
from api.agents.roster import default_roster
from api.agents.state import TurnContext
from api.agents.studio import make_study, study_focus, study_kind
from api.agents.test_agents import GRAPH
from api.core.budget import TokenBudget
from api.fakes import fake_llm_responder
from api.learner.mastery import MasteryScore
from api.learner.store import LearnerStore
from api.llm.ledger import SpendLedger
from api.llm.providers.fake import FakeProvider
from api.llm.service import LLMService
from api.retrieval.types import RetrievalResult, RetrievedChunk
from api.stores.local.sqlite_doc import SqliteDocStore, make_engine
from api.vault.test_quiz import DOC_OF, PAGE_OF, TEXT, fill
from api.vault.types import Definition


@pytest.mark.parametrize(
    "question",
    [
        "Quiz me on dense retrieval",
        "Make flashcards for BM25",
        "Test me on reciprocal rank fusion",
        "Can you give me cornell notes on reranking?",
        "Guide me through how dense retrieval relates to BM25",
        "Flashcards on query expansion",
    ],
)
def test_a_request_to_study_is_recognised(question: str):
    assert classify(question) == ("study", True)


@pytest.mark.parametrize(
    "question",
    [
        "What is the quiz format used in the benchmark?",
        "Which papers use flashcards as a baseline?",
        "How does the Socratic method compare with direct instruction in these papers?",
        "Does the dataset test me, the reader, on anything?",
    ],
)
def test_a_question_that_only_mentions_studying_is_not_a_study_request(question: str):
    assert classify(question)[0] != "study"


def test_no_frozen_benchmark_question_is_rerouted_to_study():
    path = Path(__file__).resolve().parents[2] / "eval" / "questions.yaml"
    questions = yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]
    assert all(classify(q["question"])[0] not in ("study", "write") for q in questions)


@pytest.mark.parametrize(
    ("request_text", "kind"),
    [
        ("Make flashcards for BM25", "flashcard"),
        ("Quiz me on dense retrieval", "quiz"),
        ("Test me on BM25 with practice questions", "quiz"),
        ("Give me cornell notes on reranking", "cornell"),
        ("Help me recall what BM25 is", "blurt"),
        ("Guide me through RRF with socratic questions", "socratic"),
    ],
)
def test_the_activity_is_chosen_by_keyword_and_defaults_to_flashcards(request_text: str, kind: str):
    assert study_kind(request_text) == kind


async def test_the_request_names_the_longest_page_it_contains(tmp_path: Path):
    docs = SqliteDocStore(make_engine(tmp_path / "d.db"))
    vault = fill(docs)
    assert study_focus("Make flashcards for BM25", vault) == "bm25"
    assert study_focus("quiz me on reciprocal rank fusion and BM25", vault) == "rrf"  # the longest name wins
    assert study_focus("make flashcards about everything", vault) is None
    assert study_focus("anything", None) is None


def _world(tmp_path: Path, *, vault_present: bool = True):
    docs = SqliteDocStore(make_engine(tmp_path / "turn-docs.db"))
    vault = fill(docs)
    vault.pages["dense_retrieval"] = replace(
        vault.pages["dense_retrieval"],
        definitions=(Definition(TEXT["c1"].split(". ")[0] + ".", "c1", "d1"),),
    )
    vault.__post_init__()

    async def retrieve(q: str) -> RetrievalResult:
        chunks = [RetrievedChunk(c, DOC_OF[c], TEXT[c], PAGE_OF[c], 1.0, ("dense",)) for c in ("c1", "c2")]
        return RetrievalResult(chunks=chunks, per_signal={})

    ledger = SpendLedger(create_engine(f"sqlite:///{tmp_path / 'turn.db'}"), None)
    ctx = TurnContext(
        docs,
        retrieve,
        LLMService(FakeProvider(fake_llm_responder), None, ledger),
        TokenBudget(),
        "blk",
        roster=default_roster(),
        vault=vault if vault_present else None,
    )
    return ctx, vault


async def test_a_study_turn_ends_at_the_composer_with_a_validated_set_beside_the_answer(tmp_path: Path):
    ctx, _ = _world(tmp_path)
    state = await GRAPH.ainvoke({"question": "Make flashcards for dense retrieval"}, context=ctx)
    composition = state["composition"]
    assert ctx.intent == "study"
    assert composition.blocks[0].type == "CitedSummary"  # the turn's terminal block is still the grounded answer
    study = next(b for b in composition.blocks if b.type == "StudySet")
    assert study.meta.status == "ready" and study.data.kind == "flashcard" and study.data.focusId == "dense_retrieval"  # type: ignore[union-attr]
    assert [i.pageLabel for i in study.data.items] == ["dense retrieval"]  # type: ignore[union-attr]
    assert any(r.component == "StudySet" and r.outcome == "admitted" for r in composition.records)
    assert make_study("Make flashcards for dense retrieval", ctx) == {"kind": "flashcard", "focus_id": "dense_retrieval"}


async def test_a_study_turn_streams_through_the_last_gate_without_an_error(tmp_path: Path):
    """The path a browser takes: `run_turn` re-validates every block before it is sent. A notes-family block must pass that gate too
    (found in a real browser: the gate had no vault and refused every study set, ending the turn in an error)."""
    from api.agents.graph import run_turn
    from api.genui.generated import BlockEvent, StreamErrorEvent

    ctx, _ = _world(tmp_path)
    events = [e async for e in run_turn(GRAPH, "Make flashcards for dense retrieval", ctx)]
    assert not any(isinstance(e, StreamErrorEvent) for e in events)
    types = [e.block.type for e in events if isinstance(e, BlockEvent)]
    assert "StudySet" in types and "CitedSummary" in types


async def test_a_rating_between_the_block_and_the_gate_cannot_make_the_block_differ(tmp_path: Path):
    from api.agents.graph import run_turn
    from api.genui.generated import BlockEvent, StreamErrorEvent

    class DriftingLearner(LearnerStore):
        """Answers a different mastery each time it is asked: the turn must use the reading the block was made from."""

        def __init__(self) -> None:
            self.reads = 0

        def record(self, event):  # pragma: no cover
            raise AssertionError("a turn never writes")

        def events(self, page_id):
            return []

        def mastery(self, page_ids, now=None):
            self.reads += 1
            return {"bm25": MasteryScore(0.1 if self.reads == 1 else 0.99, 4)}

        def delete_all(self):
            return 0

    ctx, _ = _world(tmp_path)
    ctx.learner = DriftingLearner()
    events = [e async for e in run_turn(GRAPH, "Make flashcards", ctx)]
    assert not any(isinstance(e, StreamErrorEvent) for e in events)
    assert any(isinstance(e, BlockEvent) and e.block.type == "StudySet" for e in events)


async def test_without_a_vault_the_turn_still_answers_and_says_why_there_is_no_set(tmp_path: Path):
    ctx, _ = _world(tmp_path, vault_present=False)
    state = await GRAPH.ainvoke({"question": "Quiz me on dense retrieval"}, context=ctx)
    composition = state["composition"]
    assert composition.blocks[0].type == "CitedSummary"
    assert "QuizCard" not in [b.type for b in composition.blocks]
    assert any(r.component == "QuizCard" and r.reasons == ("no_study_material",) for r in composition.records)


async def test_the_set_follows_the_learners_mastery_and_the_learner_store_is_only_read(tmp_path: Path):
    class FixedLearner(LearnerStore):
        def __init__(self) -> None:
            self.recorded = 0

        def record(self, event):  # pragma: no cover - must never be called by a turn
            self.recorded += 1

        def events(self, page_id):
            return []

        def mastery(self, page_ids, now=None):
            return {"bm25": MasteryScore(0.05, 5), "dense_retrieval": MasteryScore(0.95, 5)}

        def delete_all(self):
            return 0

    ctx, _ = _world(tmp_path)
    learner = FixedLearner()
    ctx.learner = learner
    state = await GRAPH.ainvoke({"question": "Make flashcards"}, context=ctx)
    study = next(b for b in state["composition"].blocks if b.type == "StudySet")
    labels = [i.pageLabel for i in study.data.items]  # type: ignore[union-attr]
    assert labels[0] == "BM25" and learner.recorded == 0  # the page known least comes first; nothing was written


async def test_a_quiz_turn_ends_at_the_composer_with_a_validated_quiz_that_carries_no_answer(tmp_path: Path):
    """V1 (D-43): "quiz me" is the cloze quiz the notes screen has, in the turn, derived from the vault and validated against it."""
    ctx, vault = _world(tmp_path)
    state = await GRAPH.ainvoke({"question": "Quiz me"}, context=ctx)
    composition = state["composition"]
    assert ctx.intent == "study" and composition.blocks[0].type == "CitedSummary"
    quiz = next(b for b in composition.blocks if b.type == "QuizCard")
    assert quiz.meta.status == "ready" and quiz.data.items  # type: ignore[union-attr]
    assert not hasattr(quiz.data.items[0], "answer") and not hasattr(quiz.data.items[0], "correct")  # type: ignore[union-attr]
    assert any(r.component == "QuizCard" and r.outcome == "admitted" for r in composition.records)


async def test_a_quiz_turn_streams_through_the_last_gate_without_an_error(tmp_path: Path):
    from api.agents.graph import run_turn
    from api.genui.generated import BlockEvent, StreamErrorEvent

    ctx, _ = _world(tmp_path)
    events = [e async for e in run_turn(GRAPH, "Quiz me", ctx)]
    assert not any(isinstance(e, StreamErrorEvent) for e in events)
    assert "QuizCard" in [e.block.type for e in events if isinstance(e, BlockEvent)]
