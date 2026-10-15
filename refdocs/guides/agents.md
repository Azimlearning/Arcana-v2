# Agents and tools: the v2 roster (D-05, D-22, D-30)

> The map from v1's many agents to v2's few. Read it before adding an agent: in v2 a new capability is a **tool** on an existing agent unless it meets the rule below. Updated when a phase adds or moves a tool.
> Status key: **built** (exists and tested), **P2** to **P5** (planned in that phase), **dropped** (not carried, with reason). Plans are not commitments: a phase's plan doc has the final list.

## The rule: when something is an agent

Something is an **agent** only if it owns at least one of:

1. a **distinct trust boundary** (it must not be merged into the thing it checks or the thing that generates code);
2. a **distinct state or budget** (it keeps its own state across turns, or its own spend or hop limit);
3. a **terminal responsibility** (it is the one place a duty is discharged: choosing the interface, ending the turn).

Otherwise it is a **tool group** on the agent whose evidence or output it serves. Agents compose only through
`route_to_agent`, within hop and token budgets, and never import each other. Engines (trained models) are not
agents: they sit behind `Engine`, additive to a heuristic (D-12).

## The roster

| Agent | Why it is an agent | Built in | Distinct from |
|---|---|---|---|
| **Orchestrator** | Entry node; owns routing, plan and the per-turn budgets | P1 | The specialists it routes to |
| **Research** | Evidence synthesis over documents: owns grounded, cited answers | P1 | Graph (structure) and the Fact Checker (verification) |
| **Graph** | Owns graph structure: paths, neighbourhoods, cross-document alignment | P1 | Research (passages) |
| **Fact Checker** | **Trust boundary**: nothing is shown that it has not passed; fails closed | P1 | Every generator (a checker merged into a generator grades its own work) |
| **Composer** | **Terminal responsibility**: the only thing that chooses components and layout (constraint 4) | P1 stub, P2 | Everyone else (agents return payloads, never blocks) |
| **Studio** (learning and writing) | Owns learner state (review schedule, mastery) and draft state | P5 (S1 writing built 2026-10-15, D-42) | Research (it consumes Research evidence) |
| **Lab Builder** | **Trust boundary**: generated code, only through the verifier | P4 | Everything else |

Seven in the end, six built today (the Studio's writing and learning groups were built in P5 S1 and S2; counting the Composer), against v1's 25. D-22 had separate Tutor and Writer;
D-30 merges them into Studio (ASSUMED, settled in the P5 plan).

## Tools by agent

### Orchestrator
| Tool | Status | Notes |
|---|---|---|
| `classify` (intent rules) | built | single, compare, relate; confident or not |
| routing model call (`purpose="route"`) | built | one light-tier call, only when the rules are unsure, safe default on failure |
| `route_to_agent`, `tool_spec`, budgets, loop guard, trace | built | framework in `api/agents/framework.py` |
| distilled intent router | P3 (Engine) | replaces the model call; falls back to rules |
| context tools (conversation history, learner profile) | P5 | absorbs v1's Memory agent |

### Research
| Tool | Status | Notes |
|---|---|---|
| `retrieve_evidence` | built | hybrid retrieval, graph evidence first for relationships |
| `compare_documents` | built | round-robin across papers, balanced |
| model-chosen quotes verified verbatim | built | server fallback sentence if not verbatim |
| `summarise_document` | P5 | per-document grounded summary (absorbs v1's Document agent) |
| `extract_methods`, `stance_by_document` | P5 | absorbs v1's Methodology and Debate agents; stance needs a measured judge |
| `contradiction_candidates` | P3 or later | structural half only (co-retrieved claims on one entity); the "disagree" judgement waits for a measured judge |
| `annotate` | P5 | absorbs v1's Annotation agent |

### Graph
| Tool | Status | Notes |
|---|---|---|
| `find_path` | built | grounded edges only, deterministic search |
| `neighborhood` | built | one to two hops, capped |
| `align_documents` | built (P2 B3) | entity-by-document alignment with a verbatim quote per cell, supplies `ComparisonGrid` |
| `cross_document_paths` | P2 stretch | supplies `InsightCard` |
| `communities`, `central_entities` | P5 | structure summaries; the store already has communities |
| `entity_timeline` | needs re-extraction, not planned | absorbs v1's Timeline; extraction records no dates (D-29) |

### Fact Checker
| Tool | Status | Notes |
|---|---|---|
| `check_claims` (verbatim quote check, judge, lexical fallback) | built | fail closed, enforced in the Composer |
| `verify_claim` (re-retrieve and judge) | P5 | absorbs v1's claim verification for Studio outputs; covered for drafts by `check_draft`'s judge |
| `check_draft` | built (P5 S1) | the quote screen and judge over a Studio draft, survivors regrouped, references rebuilt, close copies reported |
| `check_citation_accuracy` | built (P5 S1) | each reference matches the stored record (rebuilt from it otherwise) |
| `originality_check` | built inside `check_draft` (P5 S1) | longest verbatim run of words from the cited evidence; reported, not removed |
| mutation suites for each checker | built for `check_claims`; each new checker ships with one | detection rates reported, not asserted |

### Composer
| Tool | Status | Notes |
|---|---|---|
| validated `CitedSummary` and error and empty blocks | built | the only block builder |
| catalog admission and templates | P2 | deterministic, evidence-admitting (D-28) |
| `compose_layout`, prebuilt layout, `compose_workspace` | P2 | `LayoutSpec` (D-27) |
| saved patterns: save, list, apply, re-verify | P2 (spine), P4 (full lifecycle) | the UI generation pipeline (D-31) |
| generated-artifact delivery | P4 | only the verifier-minted type reaches the client |

### Studio (P5)
| Tool group | Absorbs from v1 |
|---|---|
| learning: flashcards, quiz, blurting, Feynman explainer, Cornell notes | Learning agent. **Built (S2):** `make_study` (flashcards, blurting, Cornell, Socratic; the block is `StudySet`, derived by the Composer from the vault, no model call); the quiz is the notes workspace's; the Feynman explainer is the Research answer asked for plainly |
| Socratic turn (withholds the answer, asks) | Socratic Tutor. **Built (S2):** a Socratic `StudySet`: a question per asserted link, a hint that points at the source, the sentence revealed on request |
| review scheduling | Study Planner. **Built (S3):** `StudyPlan`, a fixed interval over mastery and rating dates (no trained engine, D-37) |
| writing: outline, draft section with citations, bibliography export, citation formatting | Writing agent, Citation agent's formatting side, Document agent's export side. **Built (S1):** `draft_section`, `format_bibliography`; the block is `WritingDraft` |

### Lab Builder (P4)
| Tool | Notes |
|---|---|
| `declare_contract` | the artifact's contract (what it asserts, its evidence, its fences) |
| `generate_from_template` | starts from a reviewed template, not a blank page |
| `submit_to_verifier` | the only way an artifact can be minted for delivery |

## Where each of v1's agents went

v1 names 25 agents; the table maps the 24 named in its PRD tiers and in `api/agents/` (I could not name the 25th).

| v1 agent | v2 home | Tools or status |
|---|---|---|
| Orchestrator | Orchestrator | built |
| Memory | Orchestrator context tools | P5 |
| Research | Research | built |
| Comparator, Cross-document | Research | `compare_documents` (built); alignment evidence from Graph `align_documents` (P2) |
| Literature | Research | `ComparisonGrid` supplied by `align_documents` |
| Contradiction | Research (candidates), Fact Checker (judgement) | P3 or later; needs a measured judge |
| Discovery | Graph | `cross_document_paths` (P2 stretch) |
| Methodology, Debate | Research | P5 |
| Annotation | Research | P5 |
| Document | Research (summaries), Composer (source list), Studio (export) | `SourceList` (P2) |
| Graph | Graph | built |
| Visual | Graph (data), Composer (layout and rendering) | `GraphView` (P2) |
| Timeline | Graph | not planned: no extracted dates |
| UI | Composer | P2 |
| Fact Checker | Fact Checker | built |
| Citation | Fact Checker (accuracy), Studio (formatting) | P5 |
| Learning, Study Planner | Studio | P5 (planner needs Mastery, P3) |
| Socratic Tutor | Studio | P5 |
| Writing | Studio | P5 |
| Web Search | dropped | general web search is a PRD non-goal |
| Audio | dropped | audio generation is a PRD non-goal |

## Engines (trained tools, not agents)

| Engine | Phase | Heuristic it falls back to |
|---|---|---|
| Intent router (distilled) | P3 | the intent rules in `orchestrator.py` |
| Re-Rank after RRF | P3 | the RRF order |
| Mastery (review scheduling), optional | P3 | a fixed review interval |

## Why this shape

Fewer agents means fewer hops, smaller prompts, simpler budgets and a trace a person can read. Capability grows
by adding a tool and, if it has a visible form, a catalog entry (see `refdocs/guides/catalog.md` once A1 writes it),
not by adding an agent. The cost is a larger tool surface per agent, kept in check by the typed tool schemas
(`tool_spec`) and intent-scoped tool selection in the framework.
