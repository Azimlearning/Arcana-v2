# Plan: M2.11 the vault review screen (a screen for the lint report that already exists)

> Follows M2.8 (`api/vault/lint.py`, `GET /vault/lint`) and Q1. Execution doc: `refdocs/execution/2026-10-07-m2-lint-screen.md`. ADR: none needed (D-35 A5 already says lint is reported and never fixed; this only shows it).
> Status: **Done 2026-10-07.** Started on Azim's "proceed" after Q1; it is the one item left on the Mark 2 list that needs no model, no money and no decision. **Free.**

## Why this exists

The vault can say what a person should look at: pages with no link, near-duplicate pages, concepts several papers define, and pages mentioned almost everywhere. Today that is JSON at `GET /vault/lint`. Nobody reads JSON, and the near-duplicate list is exactly what the vault cannot decide for itself (it never merges by judgement, D-35). A screen turns the report into the review step the design assumed.

## What's already covered (no work needed)

The report and its endpoint (`api/vault/lint.py`, `routes/vault.py`), its wire types (`VaultLintResponse` and the types it uses, generated into `api/genui/generated.py`), the notes screen's frame and header, the client's error handling (`envelopeFromResponse`, `clientError`).

## Scope

**In:** a screen at `/notes/review` that fetches `/vault/lint` and shows the four lists in words, each with its exact total and the note that only the first 50 are shown; a link to it from the notes header and back; a typed client function `fetchLint`; loading, empty (no vault yet), error and ready states; tests; a real-browser look.

**Out, with reasons:** fixing anything (the vault never merges or edits by judgement; the screen has no merge button); judging whether two definitions contradict (needs a model; the report only puts them side by side); opening a page from the report (the notes screen keeps its page in state, not in the address; a person can search the name; adding a page address is a separate change); a new GenUI block (the report is a typed endpoint response, not a block an agent composes; the registry rule is about blocks).

## Approach

A plain client screen over the typed response, in the notes screen's visual language. Document text (definitions) renders as text. Each list says what it is for and what to do with it ("these two names may be one concept; the notes do not merge them") so the screen invites review rather than action.

## Risks & unknowns

| Risk | Impact | Mitigation |
|---|---|---|
| The screen reads as a to-do list the system will fix | Medium: false expectation | Every list says "reported, never fixed" and who decides |
| A large vault makes long lists | Low | The server caps each list at 50 and gives exact totals; the screen says how many are not shown |
| Definitions are long | Low | Shown as quotes with the paper's title, wrapped; no clipping rule needed (the server stores sentences) |

## Definition of done

- `/notes/review` shows orphans, near-duplicates (with the reason in words), concepts defined by several papers (definitions side by side with titles) and hub pages, each with its exact total.
- The four states render; an empty vault says so in words.
- Tests pass, lint and types are clean, and it has been seen in a real browser.
