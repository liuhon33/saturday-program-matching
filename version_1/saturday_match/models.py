"""Questionnaire-independent records and validated matching settings.

No contact details or questionnaire question text belong in these records.
The loader provides canonical subject/category values and persistent opaque IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


RANKS = ("primary", "secondary", "tertiary")


def _text(value: Any, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty, trimmed string")


def _tokens(values: Any, label: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{label} must be a tuple of canonical strings")
    for value in values:
        _text(value, label)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} contains duplicate values")


@dataclass(frozen=True)
class Tutee:
    id: str
    display_name: str
    preferences: tuple[str | None, ...]
    gender_preference: str | None = None
    grade: str | None = None
    slots: tuple[str, ...] = ()
    source_row: int | None = None

    def __post_init__(self) -> None:
        _text(self.id, "Tutee ID")
        _text(self.display_name, "Tutee display name")
        if not isinstance(self.preferences, tuple) or len(self.preferences) > 3:
            raise ValueError("Tutee preferences must be a tuple of at most three ranks")
        for value in self.preferences:
            _text(value, "Tutee subject", optional=True)
        _text(self.gender_preference, "Gender preference", optional=True)
        _text(self.grade, "Grade", optional=True)
        _tokens(self.slots, "Tutee slots")


@dataclass(frozen=True)
class Tutor:
    id: str
    display_name: str
    subjects: tuple[str, ...]
    gender: str | None = None
    capacity: int = 1
    grades: tuple[str, ...] = ()
    slots: tuple[str, ...] = ()
    source_row: int | None = None

    def __post_init__(self) -> None:
        _text(self.id, "Tutor ID")
        _text(self.display_name, "Tutor display name")
        _tokens(self.subjects, "Tutor subjects")
        if not self.subjects:
            raise ValueError("Tutor subjects must contain at least one subject")
        _text(self.gender, "Tutor gender", optional=True)
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int) or self.capacity < 1:
            raise ValueError("Tutor capacity must be a positive integer")
        _tokens(self.grades, "Tutor grades")
        _tokens(self.slots, "Tutor slots")


@dataclass(frozen=True)
class MatchingSettings:
    subject_policy: str = "primary"
    gender_policy: str = "required"
    weights: Mapping[str, float] = field(default_factory=lambda: dict(zip(RANKS, (1_000_000, 100, 1))))
    urgency_weights: Mapping[str, float] = field(default_factory=lambda: dict(zip(RANKS, (10, 3, 1))))
    urgency_scale: float = 100
    gender_urgency_bonus: float = 1000
    enforce_availability: bool = False
    enforce_grade: bool = False


def settings_from_config(config: Mapping[str, Any] | MatchingSettings | None = None) -> MatchingSettings:
    """Accept a full configuration or its ``matching`` section; reject bad values."""
    if isinstance(config, MatchingSettings):
        raw = dict(vars(config))
    elif config is None:
        raw = {}
    elif isinstance(config, Mapping):
        raw = config.get("matching", config)
        if not isinstance(raw, Mapping):
            raise ValueError("matching must be a mapping")
    else:
        raise ValueError("Matching configuration must be a mapping")
    defaults = MatchingSettings()
    values = {name: raw.get(name, value) for name, value in vars(defaults).items()}
    if values["subject_policy"] not in ("primary", "any", "legacy_flag"):
        raise ValueError("subject_policy must be primary, any, or legacy_flag")
    if values["gender_policy"] not in ("required", "legacy_flag"):
        raise ValueError("gender_policy must be required or legacy_flag")
    for name in ("enforce_availability", "enforce_grade"):
        if not isinstance(values[name], bool):
            raise ValueError(f"{name} must be true or false")
    for name in ("weights", "urgency_weights"):
        weights = values[name]
        if not isinstance(weights, Mapping) or set(weights) != set(RANKS):
            raise ValueError(f"{name} must define exactly primary, secondary, and tertiary")
        values[name] = dict(weights)
        for rank, number in weights.items():
            _number(number, f"{name}.{rank}")
    for name in ("urgency_scale", "gender_urgency_bonus"):
        _number(values[name], name)
    return MatchingSettings(**values)


def _number(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")


def validate_ids(tutees: list[Tutee], tutors: list[Tutor]) -> None:
    for label, people in (("Tutee", tutees), ("Tutor", tutors)):
        if len({person.id for person in people}) != len(people):
            raise ValueError(f"Duplicate {label.lower()} IDs: distinct people require distinct IDs")
