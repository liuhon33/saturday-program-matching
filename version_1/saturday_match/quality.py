"""Independent conservation, capacity, and eligibility checks for match output."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from .models import RANKS, MatchingSettings, Tutee, Tutor, settings_from_config, validate_ids


def validate_result(tutees: Iterable[Tutee], tutors: Iterable[Tutor], result: Mapping[str, Any], config: Mapping[str, Any] | MatchingSettings | None = None) -> dict[str, Any]:
    """Return aggregate metrics or fail if any person/capacity is unaccounted for.

    Compatibility is recalculated from records, not trusted from output flags.
    Availability/grade metrics report an unknown count when either side lacks
    the necessary information. Missing information never means verified success.
    """
    from .matcher import compatibility, rejection_reasons

    settings = settings_from_config(config)
    students, teachers = list(tutees), list(tutors)
    validate_ids(students, teachers)
    students_by_id = {person.id: person for person in students}
    teachers_by_id = {person.id: person for person in teachers}
    pairs = result["pairs"]
    unmatched = result["unmatched_tutees"]
    matched_ids = [row["tutee_id"] for row in pairs]
    unmatched_ids = [row["tutee_id"] for row in unmatched]
    accounted = matched_ids + unmatched_ids
    if len(set(accounted)) != len(accounted) or set(accounted) != set(students_by_id):
        raise ValueError("Every tutee must appear exactly once as matched or unmatched")
    usage = Counter(row["tutor_id"] for row in pairs)
    if set(usage) - set(teachers_by_id):
        raise ValueError("Match output refers to an unknown tutor ID")
    if any(usage[tutor.id] > tutor.capacity for tutor in teachers):
        raise ValueError("Tutor capacity exceeded")
    expected_capacity = {tutor.id: (tutor.capacity, usage[tutor.id], tutor.capacity - usage[tutor.id]) for tutor in teachers}
    rows = result["remaining_capacity"]
    actual_capacity = {row["tutor_id"]: (row["capacity"], row["used_capacity"], row["remaining_capacity"]) for row in rows}
    if len(rows) != len(expected_capacity) or actual_capacity != expected_capacity:
        raise ValueError("Tutor remaining capacity does not reconcile with assignments")
    unused_ids = [row["tutor_id"] for row in result["unused_tutors"]]
    if len(unused_ids) != len(set(unused_ids)) or set(unused_ids) != {tutor.id for tutor in teachers if not usage[tutor.id]}:
        raise ValueError("Unused tutor accounting does not reconcile with assignments")
    rank_counts: Counter[str] = Counter()
    known_counts: Counter[str] = Counter()
    compatible_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()
    for pair in pairs:
        student, teacher = students_by_id[pair["tutee_id"]], teachers_by_id[pair["tutor_id"]]
        checks = compatibility(student, teacher)
        if rejection_reasons(checks, settings):
            raise ValueError("Match output violates a configured hard constraint")
        if pair.get("compatibility") != checks:
            raise ValueError("Reported compatibility does not match participant records")
        for rank in RANKS:
            rank_counts[rank] += bool(checks[rank])
        for field in ("gender", "availability", "grade"):
            known_counts[field] += checks[field] is not None
            compatible_counts[field] += checks[field] is True
        if not any(checks[rank] for rank in RANKS):
            flag_counts["no_requested_subject_match"] += 1
        if checks["gender"] is False:
            flag_counts["gender_preference_not_satisfied"] += 1
        for field in ("availability", "grade"):
            if checks[field] is False:
                flag_counts[f"{field}_incompatible"] += 1
    capacity = sum(person.capacity for person in teachers)
    summary: dict[str, Any] = {
        "tutee_count": len(students), "tutor_count": len(teachers),
        "matched_count": len(pairs), "unmatched_count": len(unmatched),
        "matched_percent": round(100 * len(pairs) / len(students), 2) if students else 0.0,
        "unused_tutor_count": len(unused_ids), "total_capacity": capacity,
        "remaining_capacity": capacity - len(pairs),
        "capacity_utilization": round(len(pairs) / capacity, 6) if capacity else 0.0,
        "hard_constraint_violations": 0,
        "compatibility_flags": dict(sorted(flag_counts.items())),
        "subject_match_counts": {rank: rank_counts[rank] for rank in RANKS},
        "assignment_distribution": {str(count): sum(usage[tutor.id] == count for tutor in teachers) for count in sorted({usage[tutor.id] for tutor in teachers})},
        "total_pair_score": sum(pair["score"] for pair in pairs),
        "conservation_passed": True,
    }
    for field in ("gender", "availability", "grade"):
        summary[f"{field}_evaluated_count"] = known_counts[field]
        summary[f"{field}_compatible_count"] = compatible_counts[field]
        summary[f"{field}_not_evaluated_count"] = len(pairs) - known_counts[field]
    return summary
