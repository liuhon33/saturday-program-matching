"""Reviewed, exact category normalization. Unknown answers are never guessed."""
from __future__ import annotations

import difflib
import math
from numbers import Real
from typing import Callable
import unicodedata


class NormalizationError(ValueError):
    """Safe error code plus suggestions from the public approved catalog only."""

    def __init__(self, code: str, *, suggestions=()):
        self.code = code
        self.suggestions = tuple(suggestions)
        super().__init__(code)


def normalize_text(value) -> str | None:
    """NFKC-normalize and collapse whitespace; preserve case and genuine nulls."""
    if value is None or (isinstance(value, Real) and not isinstance(value, bool) and math.isnan(value)):
        return None
    if not isinstance(value, str):
        raise NormalizationError("non_text_value")
    return " ".join(unicodedata.normalize("NFKC", value).split()) or None


def _key(value: str) -> str:
    return normalize_text(value).casefold()


def _emit(callback, code):
    if callback is not None:
        callback(code)


def _text(value, callback):
    cleaned = normalize_text(value)
    if isinstance(value, str) and value != cleaned:
        _emit(callback, "normalized_whitespace_or_unicode" if cleaned else "blank_to_null")
    return cleaned


def _subject_lookup(config):
    lookup = {}
    for subject_id, spec in config["subjects"].items():
        for label in (subject_id, spec["label"], *spec.get("aliases", [])):
            lookup[_key(label)] = (subject_id, "approved_subject_alias" if label != spec["label"] and label != subject_id else None)
        for label in spec.get("typo_aliases", []):
            lookup[_key(label)] = (subject_id, "approved_typo_alias")
    return lookup


def _unknown_subject(cleaned, config):
    labels = {spec["label"].casefold(): spec["label"] for spec in config["subjects"].values()}
    suggestions = [labels[k] for k in difflib.get_close_matches(cleaned.casefold(), labels, n=3, cutoff=0.7)]
    raise NormalizationError("unknown_subject", suggestions=suggestions)


def canonical_subject(value, config, *, allow_none=False, on_change: Callable[[str], None] | None = None) -> str | None:
    cleaned = _text(value, on_change)
    if cleaned is None:
        if allow_none:
            return None
        raise NormalizationError("missing_required_subject")
    key = cleaned.casefold()
    if key in {_key(x) for x in config["no_subject"]}:
        if allow_none:
            _emit(on_change, "no_subject_marker_to_null")
            return None
        raise NormalizationError("missing_required_subject")
    entry = _subject_lookup(config).get(key)
    if entry is None:
        _unknown_subject(cleaned, config)
    subject_id, rule = entry
    if rule:
        _emit(on_change, rule)
    if cleaned != subject_id:
        _emit(on_change, "subject_to_canonical_id")
    return subject_id


def parse_subjects(value, config, *, on_change: Callable[[str], None] | None = None) -> tuple[str, ...]:
    """Parse full approved labels, including their internal commas.

    Delimiters may be comma, semicolon, pipe, or newline. At each position the
    longest *whole* approved label wins. Any unmatched remainder rejects the
    entire field: known prefixes are never accepted while unknown text is lost.
    """
    if isinstance(value, (list, tuple)):
        parsed = [canonical_subject(item, config, on_change=on_change) for item in value]
        if len(parsed) != len(set(parsed)):
            _emit(on_change, "duplicate_subject_removed")
        return tuple(dict.fromkeys(parsed))
    # Newlines delimit choices; do this before ordinary whitespace collapse.
    prepared = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "|") if isinstance(value, str) else value
    cleaned = _text(prepared, on_change)
    if cleaned is None:
        return ()
    if cleaned.casefold() in {_key(x) for x in config["no_subject"]}:
        _emit(on_change, "no_subject_marker_to_null")
        return ()
    lookup = _subject_lookup(config)
    labels = sorted(lookup, key=lambda item: (-len(item), item))
    remaining = cleaned.casefold()
    parsed = []
    rules = []
    while remaining:
        match = None
        for label in labels:
            if remaining.startswith(label):
                after = remaining[len(label):].lstrip()
                if not after or after[0] in ",;|":
                    match = label
                    break
        if match is None:
            _unknown_subject(remaining, config)
        subject_id, rule = lookup[match]
        parsed.append(subject_id)
        if rule:
            rules.append(rule)
        remaining = remaining[len(match):].lstrip()
        if remaining:
            remaining = remaining[1:].lstrip()
            if not remaining or remaining[0] in ",;|":
                raise NormalizationError("empty_subject_token")
    # Emit transformations only after the entire field has passed validation.
    for rule in rules:
        _emit(on_change, rule)
    if len(parsed) != len(set(parsed)):
        _emit(on_change, "duplicate_subject_removed")
    _emit(on_change, "subject_list_to_canonical_ids")
    return tuple(dict.fromkeys(parsed))


def canonical_gender(value, config, *, on_change: Callable[[str], None] | None = None) -> str | None:
    cleaned = _text(value, on_change)
    if cleaned is None:
        return None
    key = cleaned.casefold()
    for gender_id, aliases in config["genders"].items():
        if key in {_key(x) for x in [gender_id, *aliases]}:
            if cleaned != gender_id:
                _emit(on_change, "gender_to_canonical_id")
            return gender_id
    raise NormalizationError("unknown_gender")


def canonical_preference(value, config, *, on_change: Callable[[str], None] | None = None) -> str | None:
    cleaned = _text(value, on_change)
    if cleaned is None:
        if config.get("normalization", {}).get("missing_preference", "error") == "no_preference":
            _emit(on_change, "missing_preference_no_requirement")
            return None
        raise NormalizationError("missing_gender_preference")
    if cleaned.casefold() in {_key(x) for x in config["no_preference"]}:
        _emit(on_change, "no_preference_to_null")
        return None
    gender = canonical_gender(cleaned, config)
    if gender not in config["preference_values"]:
        raise NormalizationError("unknown_gender_preference")
    if cleaned != gender:
        _emit(on_change, "gender_preference_to_canonical_id")
    return gender


def normalize_with_events(field, value, config):
    """Convenience wrapper returning (normalized_value, public_rule_codes)."""
    events = []
    if field == "subjects":
        normalized = parse_subjects(value, config, on_change=events.append)
    elif field in {"primary", "secondary", "tertiary"}:
        normalized = canonical_subject(value, config, allow_none=field != "primary", on_change=events.append)
    elif field == "gender":
        normalized = canonical_gender(value, config, on_change=events.append)
    elif field == "gender_preference":
        normalized = canonical_preference(value, config, on_change=events.append)
    else:
        normalized = _text(value, events.append)
    return normalized, events
