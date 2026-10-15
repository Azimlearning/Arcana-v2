"""References for cited documents (P5 S1, D-42): derived by code from the stored document record, never generated.

A reference is built from what the store holds: the document's title (the stored title, with a leading arXiv id and underscores from a file
name tidied), the arXiv id when the source file name starts with one, and nothing else. No author, year or venue is invented: a field the
record lacks is left out, so the reference says less rather than something false. The three styles are plain strings ready to copy.

The Studio agent builds the bibliography with `reference_for`, and the block validator calls the same function again on the stored record and
requires equality, so a draft cannot carry a reference the record does not give.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from api.stores.doc_store import Document

_ARXIV = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?(?:[_\-. ]|$)")
_BIBTEX_SPECIAL = str.maketrans({"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_"})
_DROP = str.maketrans({"{": "", "}": "", "\\": ""})


def arxiv_id(document: Document) -> str | None:
    """The arXiv id the source file name starts with (`2310.11511_Self_RAG....pdf`), or None."""
    name = PurePath(document.source_path.replace("\\", "/")).name
    match = _ARXIV.match(name)
    return match.group(1) + (match.group(2) or "") if match else None


def display_title(document: Document) -> str:
    """The stored title; when it is only the file's stem (an arXiv id then underscores) the id is dropped and underscores become spaces."""
    title = document.title.strip()
    if _ARXIV.match(title):
        title = _ARXIV.sub("", title, count=1)
        title = title.replace("_", " ").strip()
    return " ".join(title.split())


def _bibtex_key(document: Document) -> str:
    return "arcana" + re.sub(r"[^A-Za-z0-9]", "", document.id)[:24]


def reference_for(document: Document) -> dict[str, str]:
    """`{"apa", "ieee", "bibtex"}` for one stored document."""
    title = display_title(document)
    arxiv = arxiv_id(document)
    apa = f"{title}. arXiv:{arxiv}." if arxiv else f"{title}."
    ieee = f'"{title}," arXiv:{arxiv}.' if arxiv else f'"{title}."'
    clean = title.translate(_DROP).translate(_BIBTEX_SPECIAL)
    fields = [f"  title = {{{clean}}}"]
    if arxiv:
        fields += [f"  eprint = {{{arxiv}}}", "  archivePrefix = {arXiv}"]
    bibtex = "@misc{" + _bibtex_key(document) + ",\n" + ",\n".join(fields) + "\n}"
    return {"apa": apa, "ieee": ieee, "bibtex": bibtex}
