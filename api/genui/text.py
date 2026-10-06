"""Text rules shared by the validator and the quote helpers, in a module neither of them imports the other for.

`validate_block` (which judges a quote) and `evidence` (which chooses one) must agree exactly on how whitespace is
normalised, how long a quote must be, and when a label occurs in a quote; one definition here keeps them in step.
"""

import re

MIN_QUOTE_CHARS = 20  # "a" or "." is not evidence
MIN_LABEL_CHARS = 2  # a one-character label would be "found" inside almost any word
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Collapse every run of whitespace to one space and trim: the form the validator compares quotes in."""
    return _WS.sub(" ", text).strip()


def label_in_quote(quote: str, label: str) -> bool:
    """True if `label` occurs in `quote` as a whole word or phrase, ignoring case and whitespace runs: "AI" is not
    found inside "chain". An empty label never matches."""
    wanted = normalise(label).lower()
    if not wanted:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(wanted)}(?![a-z0-9])"
    return re.search(pattern, normalise(quote).lower()) is not None
