# Arcana v2: Changelog

> Mandatory session log. Add an entry after **every** session where code changed, a decision was made, or a plan was modified. Newest first. Even a one-line fix gets a one-line entry.

Entry format:
```
### YYYY-MM-DD: [short summary of session goal]
- **Changed:** what files/components were touched and why
- **Decided:** any architectural or design decisions and the reasoning
- **Deviations:** anything that differed from the plan, and why
- **Verified:** what was actually run, and the result (not "should work")
- **Known issues / next steps:** what was left open
```

Those five lines are the floor, not the ceiling. Add these when the session earns them; a debugging session in particular is unreadable without the first two:
- **Reported:** the symptom in the user's own words, before you knew the cause
- **Diagnosed:** what you found, and how you proved it (the reproduction, not the hypothesis)
- **Trade-off:** what this change costs, and who it costs it to
- **Noted, not changed:** something you found and deliberately left alone, so the next session doesn't re-investigate it

Rules that make this file worth keeping:
- **"Verified" means a command was run.** Name it and give the result. If nothing was run, write "nothing verified this session"; that is useful information.
- **Deviations are the most valuable line.** A plan that changed silently is a plan nobody will trust next time.
- **Write what you learned, not what you touched.** "Fixed the retriever" ages into nothing. "Graph traversal returned nothing because query entities matched node ids exactly" is still worth reading in six months.
- Don't rewrite history. Corrections go in a new entry that references the old one.

---

## [Unreleased]

### 2026-10-05: Project scaffolded
- **Changed:** Created the project doc system: `refdocs/` (PRD, STATUS, sources, founding context, guides/, changelog/DECISIONS, plans/, execution/), `CLAUDE.md`, `README.md` (merged with the earlier one-file README), `.gitignore`, `.env.example`, `.claude/` (settings, secret-guard hook, five agents, three commands, memory/preflight). No application code yet.
- **Decided:** D-01 to D-16 (PRD §7): ground-up rebuild with v1 as reference; GraphRAG core with agentic AI and GenUI pillars, trained models as tools; same stack shape at current versions; single user, no auth; fewer, deeper agents with super tools; automated evaluation only; build order P0 to P5; Anthropic primary with OpenRouter fallback and a spend cap; local storage behind abstractions; three GenUI levels with a data-only wire; governed component lifecycle; additive engines; embeddings unchanged from v1; eval metrics; port by copying with provenance.
- **Verified:** Nothing to verify; no code exists yet. Doc checks run at scaffold time: no unfilled template tokens, docs not gitignored, secret hook fired against a planted key and a clean file.
- **Known issues / next steps:** Q-01 (spend cap) needs Azim's number before any paid call. Q-02 (vector store) and Q-03 (Python version) resolve in P0. Q-05 (reuse v1 question set and corpus) needs confirmation before gold annotation. Next session starts from `refdocs/plans/2026-10-05-p0-walking-skeleton.md`.
