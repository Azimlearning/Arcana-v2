# Arcana v2

Graph-grounded generative UI for learning. **GraphRAG is the core**; agentic AI and generative UI
are the two pillars built on it; trained models are tools that serve those pillars.

Final Year Project, Universiti Teknologi PETRONAS: *Arcana: A GraphRAG-Powered Multi-Agent Research
and Learning Intelligence Platform*.

## Relationship to v1

v2 is a ground-up rebuild, not a continuation. Arcana v1
([Azimlearning/Arcana](https://github.com/Azimlearning/Arcana), frozen at tag `v1.0`, the system the
MCAIT 2026 paper describes) is the **reference**: its design, its lessons and its evaluation harness
inform v2. Individual pieces, for example GenUI components, are copied across only when they suit the
v2 design, and each copied file notes where it came from.

## Direction

- **GraphRAG core:** knowledge graph plus dense and sparse retrieval, fused by rank.
- **GenUI pillar:** typed components by default, a validated layout spec for the adaptive dashboard,
  and verified generated artifacts (sandboxed, contract-checked) only when no component can express
  the answer. The techniques for the last two come from Synapse
  ([Azimlearning/GenUI-Education](https://github.com/Azimlearning/GenUI-Education)).
- **Governed component lifecycle:** generated, verified, cached, audited, promoted. A component joins
  the vocabulary on evidence, and only when retrieval can satisfy what it asserts.
- **Evaluation first:** a gold-annotated retrieval benchmark with RAGAS, a knowledge-graph extraction
  audit, verifier mutation testing, and a user study.

## Status

Empty. The project plan and docs are the next step.
