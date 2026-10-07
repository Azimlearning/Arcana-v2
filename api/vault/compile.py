"""compile_vault: turn a graph and its passages into a vault, deterministically and without a model (M2, D-35 `vault-1`).

    pages      nodes grouped by union-find over `alias_of` edges and over equal compact ids (`graph_rag`, `graphrag`)
    mentions   a passage mentions a page if a member's own chunk list holds it, or a member label (3+ characters) occurs
               in it as a whole word, blind to hyphenation, found corpus-wide with an inverted token index
    asserted   node edges lifted to pages (self-loops dropped), with their relation, evidence and passages
    co-mention two pages whose labels occur in one sentence of a passage; a sentence naming more than 6 pages makes none
               (lists, author lines), neither does a sentence that reads like a bibliography entry, and neither do pages of
               kind person or organisation
    claims     sentences a builder marked claim-worthy, mapped from concept ids to pages

Nothing is merged by judgement and no stored node, edge or passage is changed: the vault is a layer built on top.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import combinations

from api.stores.doc_store import Chunk, DocStore
from api.stores.graph_store import Edge, GraphStore, Node
from api.vault.text import fold, looks_bibliographic, occurs, split_sentences, tokens
from api.vault.types import (
    MAX_DEFINITIONS,
    MAX_SENTENCE_PAGES,
    MIN_SCAN_LABEL_CHARS,
    NO_CO_MENTION_KINDS,
    VAULT_VERSION,
    ClaimDraft,
    ClaimNote,
    ConceptPage,
    Definition,
    PageLink,
    Vault,
)

_ABBREVIATION = re.compile(r"^[A-Z][A-Z0-9]{1,7}s?$")
MIN_COMPACT_CHARS = 4
"""Two node ids that differ only by underscores are one page only when the compact form is at least this long."""


def compile_vault(graph: GraphStore, docs: DocStore, claims: Iterable[ClaimDraft] = ()) -> Vault:
    nodes = sorted(graph.nodes(), key=lambda n: n.id)
    chunks = sorted(docs.all_chunks(), key=lambda c: (c.doc_id, c.ordinal))
    stored = {c.id for c in chunks}
    folded = [fold(c.text) for c in chunks]
    index = {c.id: i for i, c in enumerate(chunks)}

    groups = _group(nodes, graph.edges())
    by_id = {n.id: n for n in nodes}
    postings = _postings(folded)

    pages: dict[str, ConceptPage] = {}
    label_keys: dict[str, list[str]] = {}
    for root, member_ids in sorted(groups.items()):
        members = [by_id[m] for m in member_ids]
        keys = sorted(
            {
                fold(m.label)
                for m in members
                if len(m.label.strip()) >= MIN_SCAN_LABEL_CHARS and fold(m.label)
            }
        )
        label_keys[root] = keys
        mentioned = {c for m in members for c in m.chunk_ids if c in stored}
        for key in keys:
            mentioned.update(
                chunks[i].id for i in _candidates(key, postings) if occurs(folded[i], key)
            )
        label, aliases = _display(members)
        pages[root] = ConceptPage(
            id=root,
            label=label,
            aliases=aliases,
            node_ids=tuple(member_ids),
            kind=_kind(members),
            doc_ids=tuple(sorted({d for m in members for d in m.doc_ids})),
            mention_chunk_ids=tuple(sorted(mentioned, key=lambda cid: index[cid])),
            definitions=_definitions(members, chunks, folded, index),
        )

    page_of = {n: root for root, members in groups.items() for n in members}
    links, alias_internal = _asserted(graph.edges(), page_of)
    co_links = _co_mentions(pages, label_keys, chunks, folded, index)
    claim_notes, claims_dropped = _claims(claims, page_of, stored)
    stats = {
        "version": VAULT_VERSION,
        "nodes": len(nodes),
        "pages": len(pages),
        "pages_with_aliases": sum(1 for p in pages.values() if p.aliases),
        "asserted_links": len(links),
        "co_mention_links": len(co_links),
        "alias_edges_inside_a_page": alias_internal,
        "claims": len(claim_notes),
        "claims_dropped": claims_dropped,
    }
    return Vault(VAULT_VERSION, len(chunks), pages, links + co_links, claim_notes, stats)


# ── pages ─────────────────────────────────────────────────────────────────────


def _group(nodes: Sequence[Node], edges: Iterable[Edge]) -> dict[str, list[str]]:
    """Root id (the smallest member id) to the sorted member ids."""
    parent = {n.id: n.id for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for edge in sorted(edges, key=lambda e: (e.src, e.dst, e.relation, e.chunk_id)):
        if edge.relation == "alias_of" and edge.src in parent and edge.dst in parent:
            union(edge.src, edge.dst)
    compact: dict[str, str] = {}
    for node in nodes:
        key = node.id.replace("_", "")
        if len(key) < MIN_COMPACT_CHARS:
            continue
        if key in compact:
            union(compact[key], node.id)
        else:
            compact[key] = node.id
    groups: dict[str, list[str]] = {}
    for node in nodes:
        groups.setdefault(find(node.id), []).append(node.id)
    return {root: sorted(members) for root, members in groups.items()}


def _is_abbreviation(label: str) -> bool:
    stripped = label.strip()
    return stripped.isupper() or bool(_ABBREVIATION.match(stripped))


def _display(members: Sequence[Node]) -> tuple[str, tuple[str, ...]]:
    """The longest member label that is not an all-capitals abbreviation (ties: the smaller id); if every label is one, the
    member named in the most passages (ties: the smaller id). The other distinct labels are the aliases."""
    plain = [m for m in members if not _is_abbreviation(m.label)]
    if plain:
        chosen = min(plain, key=lambda m: (-len(m.label), m.id))
    else:
        chosen = min(members, key=lambda m: (-len(m.chunk_ids), m.id))
    seen = {chosen.label.lower()}
    aliases: list[str] = []
    for m in sorted(members, key=lambda m: m.id):
        if m.label.lower() not in seen:
            seen.add(m.label.lower())
            aliases.append(m.label)
    return chosen.label, tuple(aliases)


def _kind(members: Sequence[Node]) -> str | None:
    counts = Counter(m.kind for m in members if m.kind and m.kind != "other")
    if not counts:
        return None
    return min(counts, key=lambda k: (-counts[k], k))


def _definitions(
    members: Sequence[Node], chunks: Sequence[Chunk], folded: Sequence[str], index: dict[str, int]
) -> tuple[Definition, ...]:
    out: list[Definition] = []
    seen: set[str] = set()
    for m in members:
        if not m.note:
            continue
        key = fold(m.note)
        if key in seen:
            continue
        for chunk_id in sorted(m.chunk_ids, key=lambda cid: index.get(cid, 1 << 30)):
            i = index.get(chunk_id)
            if i is not None and key in folded[i]:
                seen.add(key)
                out.append(Definition(m.note, chunks[i].id, chunks[i].doc_id))
                break
    return tuple(out[:MAX_DEFINITIONS])


# ── mentions ──────────────────────────────────────────────────────────────────


def _postings(folded: Sequence[str]) -> dict[str, set[int]]:
    postings: dict[str, set[int]] = {}
    for i, text in enumerate(folded):
        for token in set(tokens(text)):
            postings.setdefault(token, set()).add(i)
    return postings


def _candidates(key: str, postings: dict[str, set[int]]) -> list[int]:
    """The passages that hold every alphanumeric token of the folded label. A superset of the passages that contain the label
    (the regex confirms), so the index only prunes."""
    parts = tokens(key)
    if not parts:
        return []
    sets = sorted((postings.get(t, set()) for t in set(parts)), key=len)
    found = set(sets[0])
    for other in sets[1:]:
        found &= other
        if not found:
            break
    return sorted(found)


# ── links ─────────────────────────────────────────────────────────────────────


def _asserted(edges: Iterable[Edge], page_of: dict[str, str]) -> tuple[list[PageLink], int]:
    grouped: dict[tuple[str, str, str], dict[str, object]] = {}
    inside = 0
    for edge in sorted(edges, key=lambda e: (e.src, e.dst, e.relation, e.chunk_id)):
        src, dst = page_of.get(edge.src), page_of.get(edge.dst)
        if src is None or dst is None:
            continue
        if src == dst:
            inside += 1
            continue
        entry = grouped.setdefault((src, dst, edge.relation), {"chunks": [], "evidence": None})
        chunk_list: list[str] = entry["chunks"]  # type: ignore[assignment]
        if edge.chunk_id not in chunk_list:
            chunk_list.append(edge.chunk_id)
        if entry["evidence"] is None and edge.evidence:
            entry["evidence"] = edge.evidence
    links = [
        PageLink(src, dst, "asserted", relation, tuple(e["chunks"]), e["evidence"])  # type: ignore[arg-type]
        for (src, dst, relation), e in sorted(grouped.items())
    ]
    return links, inside


def _co_mentions(
    pages: dict[str, ConceptPage],
    label_keys: dict[str, list[str]],
    chunks: Sequence[Chunk],
    folded: Sequence[str],
    index: dict[str, int],
) -> list[PageLink]:
    eligible = {
        pid for pid, p in pages.items() if p.kind not in NO_CO_MENTION_KINDS and label_keys[pid]
    }
    here: dict[int, list[str]] = {}
    for pid in sorted(eligible):
        for chunk_id in pages[pid].mention_chunk_ids:
            here.setdefault(index[chunk_id], []).append(pid)
    found: dict[tuple[str, str], tuple[list[str], str]] = {}
    for i in sorted(here):
        candidates = here[i]
        if len(candidates) < 2:
            continue
        for sentence in split_sentences(chunks[i].text):
            if looks_bibliographic(sentence):
                continue
            sentence_folded = fold(sentence)
            named = [
                pid
                for pid in candidates
                if any(occurs(sentence_folded, k) for k in label_keys[pid])
            ]
            if not 2 <= len(named) <= MAX_SENTENCE_PAGES:
                continue
            for a, b in combinations(sorted(named), 2):
                entry = found.setdefault((a, b), ([], sentence))
                if chunks[i].id not in entry[0]:
                    entry[0].append(chunks[i].id)
    return [
        PageLink(a, b, "co_mention", None, tuple(ids), example)
        for (a, b), (ids, example) in sorted(found.items())
    ]


# ── claims ────────────────────────────────────────────────────────────────────


def _claims(
    drafts: Iterable[ClaimDraft], page_of: dict[str, str], stored: set[str]
) -> tuple[list[ClaimNote], int]:
    notes: list[ClaimNote] = []
    dropped = 0
    seen: set[tuple[str, str]] = set()
    for draft in drafts:
        pages = tuple(sorted({page_of[n] for n in draft.concept_ids if n in page_of}))
        key = (draft.chunk_id, fold(draft.sentence))
        if not pages or draft.chunk_id not in stored or key in seen:
            dropped += 1
            continue
        seen.add(key)
        notes.append(
            ClaimNote(
                f"claim-{len(notes) + 1}", draft.chunk_id, draft.doc_id, draft.sentence, pages
            )
        )
    return notes, dropped
