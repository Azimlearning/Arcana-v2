# P5 S5: the adaptive dashboard and the Studio blocks in a real browser (2026-10-15)

Method: the API (fake LLM and embeddings, so nothing is paid) and the Next.js dev server run locally; a headless Chromium driven by Playwright runs `browser_check`-style scripts (kept in the scratchpad, not the repo) that ask real questions and assert what the page shows. Screenshots are `p5-*.png` in this folder; the pass list is `p5-browser-check.json` and `p5-browser-study-check.json`. Two data sets: a throwaway store with the 3-page fixture paper (writing, dashboard) and a copy of the full-corpus `atomic2` vault (study sets over real definitions and claims, ratings, the schedule).

## What passed

| Check | Result |
|---|---|
| Opens in Basic; Adaptive is disabled and says why until an answer exists | pass |
| A question is answered with citations; Adaptive becomes available; choosing it and then Basic again toggles the pressed state | pass |
| `Write an outline on hybrid retrieval`: a cited draft with sections, sources and a bibliography; the bibliography switches to BibTeX | pass |
| `Make flashcards for dense retrieval`: a study set from the real vault; revealing shows a cited sentence; a self-rating is saved | pass |
| `Guide me with socratic questions`: items with a hint behind a button | pass |
| `What should I review today?` after a rating: the schedule lists the rated page with its due word, mastery in words and days | pass |
| The Studio shelf's starters put the request in the question box (focused) or ask it at once | pass |
| No uncaught page errors in any run | pass |

## What the browser found that the tests did not

1. **Every study turn ended in an error.** The last gate before the wire (`api/agents/graph.py::_checked`) re-validated each block with no vault, so a notes-family block (a study set or a review schedule), which can only be checked against the vault, was refused and the turn ended in an error block. The unit tests called the graph directly and never went through that gate. Fixed: the gate is given the vault and the very mastery reading the block was derived from (`TurnContext.mastery_snapshot`, so a rating that lands in between cannot make the block differ), and two tests now stream a study turn through `run_turn`.
2. **The Studio shelf told the learner the tools were "Coming with the Studio agent"** after they existed. The shelf is now the launcher (Flashcards, Cornell notes, Socratic questions, Review schedule, Write an outline, and a link to the notes quiz); Slides, which nothing builds, is gone rather than promised.

## Phone width (checked at 390 and 768 px)

At 390 px the three panels were squeezed side by side into columns a few characters wide (the sources and the studio read vertically): unusable. Fixed in `Shell.tsx` and `Panel.tsx`: below the `md` breakpoint the panels stack (the answer first, then the Studio, then the sources), each as tall as its content, a collapsed panel is not drawn, and the page scrolls. After the fix, no horizontal overflow at 390 or 768 px for the empty workspace, a study set and a writing draft (`p5-phone-check.json`, `p5-phone-*.png`).

## Limits

Fake LLM text is a stand-in: the answers read "The document states: ...", so this shows structure, gating and interaction, not the quality of a real model's writing (that is S6). The behavioural checks ran at 1440 by 900; the phone-width pass is separate (above), layout only. The Next.js dev overlay badge in two screenshots is the dev server's, not the app's.
