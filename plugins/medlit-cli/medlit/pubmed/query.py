"""Lightweight validation for Agent-authored PubMed queries."""

from __future__ import annotations

import re
from typing import Any


_ATTEMPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_BOOLEAN_RE = re.compile(r"\b(AND|OR|NOT)\b")
_LOWER_BOOLEAN_RE = re.compile(r"\b(and|or|not)\b")
_FIELD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /_.-]*(?::(?:noexp|~\d+))?$", re.IGNORECASE)
_KNOWN_FIELDS = {
    "abstract",
    "all",
    "all fields",
    "author",
    "date - publication",
    "filter",
    "journal",
    "language",
    "mesh major topic",
    "mesh terms",
    "pmcid",
    "pmid",
    "publication date",
    "publication type",
    "subset",
    "supplementary concept",
    "text word",
    "title",
    "title/abstract",
}


def lint_pubmed_query(query: str) -> dict[str, Any]:
    """Reject only query structures that are certainly malformed.

    PubMed remains the authority for its full syntax. Unknown but well-formed
    field tags produce warnings instead of errors so new or advanced syntax is
    not blocked by this local checker.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(query, str) or not query.strip():
        return {"valid": False, "errors": ["exact_query must be a non-empty string"], "warnings": []}

    if any(ord(char) < 32 and char not in "\t\n\r" for char in query):
        errors.append("query contains control characters")

    paren_depth = 0
    bracket_start: int | None = None
    in_quote = False
    field_tags: list[str] = []
    for index, char in enumerate(query):
        if char == '"' and bracket_start is None:
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == "[":
            if bracket_start is not None:
                errors.append("nested square brackets are not valid field tags")
                break
            bracket_start = index
        elif char == "]":
            if bracket_start is None:
                errors.append("closing square bracket has no opener")
                break
            field_tags.append(query[bracket_start + 1:index].strip())
            bracket_start = None
        elif bracket_start is None:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    errors.append("closing parenthesis has no opener")
                    break

    if in_quote:
        errors.append("double quote is not closed")
    if bracket_start is not None:
        errors.append("square bracket is not closed")
    if paren_depth > 0:
        errors.append("parenthesis is not closed")

    for tag in field_tags:
        if not tag or not _FIELD_RE.fullmatch(tag):
            errors.append(f"malformed field tag: [{tag}]")
            continue
        base = tag.split(":", 1)[0].strip().casefold()
        if base not in _KNOWN_FIELDS:
            warnings.append(f"unrecognized field tag; PubMed will decide validity: [{tag}]")

    syntax_text = re.sub(r'"[^"]*"', " TERM ", query)
    syntax_text = re.sub(r"\[[^\]]*\]", "", syntax_text)
    syntax_text = syntax_text.strip()
    stripped_start = syntax_text.lstrip("( ")
    stripped_end = syntax_text.rstrip(") ")
    if _BOOLEAN_RE.match(stripped_start):
        errors.append("query starts with a Boolean operator")
    if re.search(r"\b(?:AND|OR|NOT)$", stripped_end):
        errors.append("query ends with a Boolean operator")
    if re.search(r"\b(?:AND|OR|NOT)\s+(?:AND|OR|NOT)\b", syntax_text):
        errors.append("adjacent Boolean operators are not valid")
    if _LOWER_BOOLEAN_RE.search(syntax_text):
        warnings.append("lowercase boolean-like words are treated as search terms by PubMed")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def validate_query_submission(data: Any) -> dict[str, Any]:
    """Validate the JSON envelope without rewriting the Agent's query."""
    if not isinstance(data, dict):
        raise ValueError("query file must contain a JSON object")

    exact_query = data.get("exact_query")
    lint = lint_pubmed_query(exact_query)
    if not lint["valid"]:
        raise ValueError("; ".join(lint["errors"]))

    attempt_id = str(data.get("attempt_id", "")).strip()
    if attempt_id and not _ATTEMPT_ID_RE.fullmatch(attempt_id):
        raise ValueError("attempt_id must use 1-64 letters, digits, dots, underscores, or hyphens")

    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str):
        raise ValueError("reasoning must be a string")

    added_terms = data.get("added_terms", [])
    if not isinstance(added_terms, list):
        raise ValueError("added_terms must be a list")
    for index, item in enumerate(added_terms):
        if not isinstance(item, dict):
            raise ValueError(f"added_terms[{index}] must be an object")
        for field in ("term", "source_term", "reason"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"added_terms[{index}].{field} must be a non-empty string")

    return {
        "attempt_id": attempt_id,
        "exact_query": exact_query,
        "reasoning": reasoning.strip(),
        "added_terms": added_terms,
        "lint": lint,
    }
