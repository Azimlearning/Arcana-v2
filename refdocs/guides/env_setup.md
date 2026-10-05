# Environment Setup: Arcana v2

> **Security:** never commit a real value from this file. `.env*` is gitignored; `.env.example` carries the *names* with blank values and is committed.
> Never paste a real token into a plan, an execution doc, a changelog entry, or a chat transcript. If one leaks, rotate it; don't just delete the message.
> This repo is **public**. A committed key is a leaked key.

Last updated: 2026-10-05

---

## Required variables

Required once the matching mode is `live`. With `ARCANA_LLM_MODE=fake` and `ARCANA_EMBED_MODE=fake` (the P0 default), no key is needed.

| Variable | Required | Where to get it | Read by | Notes |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` | When `ARCANA_LLM_MODE=live` | https://console.anthropic.com/settings/keys | `api/core/settings.py` → `api/llm` | Primary LLM (D-08) |
| `OPENROUTER_API_KEY` | When `ARCANA_LLM_MODE=live` | https://openrouter.ai/keys | `api/core/settings.py` → `api/llm` | Fallback LLM (D-08) |
| `OPENAI_API_KEY` | When `ARCANA_EMBED_MODE=live` | https://platform.openai.com/api-keys | `api/core/settings.py` → `api/ingestion/embed.py` | `text-embedding-3-large` (D-14) |
| `LLM_MONTHLY_CAP_USD` | When `ARCANA_LLM_MODE=live` | Azim decides (Q-01) | `api/llm/ledger.py` | Calls that would exceed it are refused before sending |

## Optional variables

| Variable | Default if unset | What it changes |
|---|---|---|
| `ARCANA_LLM_MODE` | `fake` | `live` calls real providers |
| `ARCANA_EMBED_MODE` | `fake` | `live` calls the embeddings API |
| `ARCANA_DATA_DIR` | `./data` | Where the graph, vectors, SQLite file, uploads and artifacts live |
| `LOG_LEVEL` | `INFO` | Backend log verbosity |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | The API the web app streams from. Public by design: it is inlined into the browser bundle, so it must never hold a secret |

---

## Setup

```bash
cp .env.example .env      # then fill in values; never commit .env
uv sync                   # backend dependencies (after P0 task 1)
pnpm install              # frontend and schema dependencies (after P0 task 1)
```

Backend reads `.env` at startup. The web app reads only `NEXT_PUBLIC_*` variables, at build time.

---

## Rules

- **Client-side bundles are public.** Anything inlined into a browser build is readable by anyone who opens devtools. A key that must stay secret goes through a server-side route, never into client code, no exceptions.
- **`.env.example` is the documentation.** Add the variable name there the moment you add the variable, or the next setup silently half-works.
- **A missing required variable fails loudly at startup**, with a message naming the variable and pointing here.
- **Rotate on exposure, not on suspicion of exposure.** If you can't prove a key never left the machine, treat it as leaked.

## When a variable changes

Adding, renaming, or removing one means updating, in the same session: this file, `.env.example`, the deploy target's dashboard (if one ever exists), and a changelog entry.
