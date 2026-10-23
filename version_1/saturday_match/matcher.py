"""Deterministic urgency-first greedy matching; no spreadsheet or PII I/O.

Urgency is calculated once from initial tutor supply, just as in Version 0.
There is no global optimization or automatic reallocation of an earlier match.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from .models import RANKS, MatchingSettings, Tutee, Tutor, settings_from_config, validate_ids


def _ranked_preferences(tutee: Tutee) -> tuple[str | None, ...]:
    return tutee.preferences + (None,) * (3 - len(tutee.preferences))


def compatibility(tutee: Tutee, tutor: Tutor) -> dict[str, bool | None]:
    subjects = set(tutor.subjects)
    checks: dict[str, bool | None] = {
        rank: subject is not None and subject in subjects
        for rank, subject in zip(RANKS, _ranked_preferences(tutee))
    }
    checks["gender"] = None if tutee.gender_preference is None else tutor.gender == tutee.gender_preference
    checks["availability"] = bool(set(tutee.slots) & set(tutor.slots)) if tutee.slots and tutor.slots else None
    checks["grade"] = tutee.grade in tutor.grades if tutee.grade is not None and tutor.grades else None
    return checks


def rejection_reasons(checks: Mapping[str, bool | None], settings: MatchingSettings) -> list[str]:
    reasons = []
    if settings.subject_policy == "primary" and not checks["primary"]:
        reasons.append("primary_subject_unavailable")
    elif settings.subject_policy == "any" and not any(checks[rank] for rank in RANKS):
        reasons.append("requested_subject_unavailable")
    if settings.gender_policy == "required" and checks["gender"] is False:
        reasons.append("requested_gender_unavailable")
    for field, enforced in (("availability", settings.enforce_availability), ("grade", settings.enforce_grade)):
        if enforced and checks[field] is not True:
            reasons.append(f"{field}_unknown" if checks[field] is None else f"{field}_incompatible")
    return reasons


def urgency_scores(tutees: Iterable[Tutee], tutors: Iterable[Tutor], config: Mapping[str, Any] | MatchingSettings | None = None) -> dict[str, int]:
    """Supply counts people, not capacity units, preserving the original objective."""
    settings = settings_from_config(config)
    supply = Counter(subject for tutor in tutors for subject in tutor.subjects)
    urgency = {}
    for tutee in tutees:
        score = sum(
            settings.urgency_weights[rank] * settings.urgency_scale / supply[subject]
            for rank, subject in zip(RANKS, _ranked_preferences(tutee))
            if subject is not None and supply[subject] > 0
        )
        if tutee.gender_preference is not None:
            score += settings.gender_urgency_bonus
        urgency[tutee.id] = round(score)
    return urgency


def _pair_score(checks: Mapping[str, bool | None], settings: MatchingSettings) -> tuple[float, dict[str, float]]:
    breakdown = {rank: settings.weights[rank] if checks[rank] else 0 for rank in RANKS}
    subtotal = sum(breakdown.values())
    # Compatibility mode retains the old zero-score gender mismatch fallback.
    adjustment = -subtotal if settings.gender_policy == "legacy_flag" and checks["gender"] is False else 0
    breakdown.update(subject_score=subtotal, gender_adjustment=adjustment)
    return subtotal + adjustment, breakdown


def match_greedy(tutees: Iterable[Tutee], tutors: Iterable[Tutor], config: Mapping[str, Any] | MatchingSettings | None = None) -> dict[str, Any]:
    """Match every input tutee or account for them explicitly as unmatched.

    Tutees are ordered by descending static urgency then ID. Tutors are chosen
    by descending weighted subject score then ID. Names never identify people.
    ``legacy_flag`` explicitly allows a flagged incompatible fallback; it is
    available for comparison, not the default production eligibility policy.
    """
    settings = settings_from_config(config)
    students, teachers = list(tutees), list(tutors)
    validate_ids(students, teachers)
    teachers.sort(key=lambda person: person.id)
    urgency = urgency_scores(students, teachers, settings)
    students.sort(key=lambda person: (-urgency[person.id], person.id))
    remaining = {tutor.id: tutor.capacity for tutor in teachers}
    pairs, unmatched = [], []
    for student in students:
        choices = []
        rejections: Counter[str] = Counter()
        eligible_exists = False
        for teacher in teachers:
            checks = compatibility(student, teacher)
            reasons = rejection_reasons(checks, settings)
            if reasons:
                rejections.update(reasons)
                continue
            eligible_exists = True
            if remaining[teacher.id] == 0:
                rejections["capacity_exhausted"] += 1
                continue
            score, breakdown = _pair_score(checks, settings)
            choices.append((teacher, score, breakdown, checks))
        if not choices:
            unmatched.append({
                "tutee_id": student.id,
                "urgency_score": urgency[student.id],
                "reason": "capacity_exhausted" if eligible_exists or not teachers else "no_eligible_tutor",
                "rejection_counts": dict(sorted(rejections.items())),
            })
            continue
        teacher, score, breakdown, checks = min(choices, key=lambda item: (-item[1], item[0].id))
        flags = []
        if not any(checks[rank] for rank in RANKS):
            flags.append("no_requested_subject_match")
        if checks["gender"] is False:
            flags.append("gender_preference_not_satisfied")
        for field in ("availability", "grade"):
            if checks[field] is False:
                flags.append(f"{field}_incompatible")
        pairs.append({
            "tutee_id": student.id, "tutor_id": teacher.id,
            "urgency_score": urgency[student.id], "score": score,
            "breakdown": breakdown, "compatibility": checks,
            "violations": flags, "hard_constraint_violations": [],
        })
        remaining[teacher.id] -= 1
    capacity_rows = [{
        "tutor_id": tutor.id, "capacity": tutor.capacity,
        "used_capacity": tutor.capacity - remaining[tutor.id],
        "remaining_capacity": remaining[tutor.id],
    } for tutor in teachers]
    result = {
        "algorithm": "urgency_first_greedy", "pairs": pairs,
        "unmatched_tutees": unmatched, "remaining_capacity": capacity_rows,
        "unused_tutors": [row.copy() for row in capacity_rows if row["used_capacity"] == 0],
        "processing_order": [student.id for student in students],
        "policies": {
            "subject_policy": settings.subject_policy, "gender_policy": settings.gender_policy,
            "enforce_availability": settings.enforce_availability, "enforce_grade": settings.enforce_grade,
        },
    }
    from .quality import validate_result

    result["summary"] = validate_result(students, teachers, result, settings)
    return result
