"""Synthetic regressions for participant accounting and greedy semantics."""

import copy
import itertools
import unittest

from saturday_match.matcher import match_greedy, urgency_scores
from saturday_match.models import Tutee, Tutor, settings_from_config
from saturday_match.quality import validate_result


def student(identifier, primary="math", secondary=None, tertiary=None, **kwargs):
    return Tutee(identifier, "tutee example", (primary, secondary, tertiary), **kwargs)


def teacher(identifier, subjects=("math",), **kwargs):
    return Tutor(identifier, "tutor example", subjects, **kwargs)


class GreedyMatchingTests(unittest.TestCase):
    def test_same_names_remain_distinct(self):
        result = match_greedy([student("s1"), student("s2")], [teacher("t1"), teacher("t2")])
        self.assertEqual(result["summary"]["matched_count"], 2)
        self.assertEqual({pair["tutor_id"] for pair in result["pairs"]}, {"t1", "t2"})

    def test_shortage_retains_every_student(self):
        result = match_greedy([student(f"s{i}") for i in range(5)], [teacher("t1")])
        self.assertEqual(result["summary"]["matched_count"], 1)
        self.assertEqual(result["summary"]["unmatched_count"], 4)
        self.assertTrue(all(row["reason"] == "capacity_exhausted" for row in result["unmatched_tutees"]))

    def test_no_tutors_and_no_students_are_valid(self):
        self.assertEqual(len(match_greedy([student("s1")], [])["unmatched_tutees"]), 1)
        self.assertEqual(len(match_greedy([], [teacher("t1")])["unused_tutors"]), 1)
        self.assertEqual(match_greedy([], [])["summary"]["matched_count"], 0)

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate tutee IDs"):
            match_greedy([student("s1"), student("s1")], [teacher("t1")])
        with self.assertRaisesRegex(ValueError, "Duplicate tutor IDs"):
            match_greedy([student("s1")], [teacher("t1"), teacher("t1")])

    def test_input_permutations_have_identical_results(self):
        students = [student("s1"), student("s2", "english"), student("s3")]
        teachers = [teacher("t2", ("math", "english")), teacher("t1", ("math", "english"))]
        expected = match_greedy(students, teachers)
        for student_order in itertools.permutations(students):
            for teacher_order in itertools.permutations(teachers):
                self.assertEqual(match_greedy(student_order, teacher_order), expected)

    def test_subject_matching_is_exact(self):
        result = match_greedy([student("s1", "math")], [teacher("t1", ("math_advanced",))])
        self.assertEqual(result["summary"]["matched_count"], 0)

    def test_any_policy_allows_secondary_but_primary_does_not(self):
        students, teachers = [student("s1", "math", "english")], [teacher("t1", ("english",))]
        self.assertFalse(match_greedy(students, teachers)["pairs"])
        result = match_greedy(students, teachers, {"subject_policy": "any"})
        self.assertEqual(result["pairs"][0]["score"], 100)
        self.assertEqual(result["summary"]["hard_constraint_violations"], 0)

    def test_legacy_fallback_is_explicitly_flagged(self):
        result = match_greedy([student("s1", "math", gender_preference="female")], [teacher("t1", ("english",), gender="male")], {"subject_policy": "legacy_flag", "gender_policy": "legacy_flag"})
        self.assertEqual(result["pairs"][0]["score"], 0)
        self.assertEqual(set(result["pairs"][0]["violations"]), {"no_requested_subject_match", "gender_preference_not_satisfied"})

    def test_required_gender_cannot_fall_back_to_zero_score(self):
        result = match_greedy([student("s1", gender_preference="female")], [teacher("t1", gender="male")])
        self.assertFalse(result["pairs"])
        self.assertEqual(result["unmatched_tutees"][0]["rejection_counts"], {"requested_gender_unavailable": 1})

    def test_optional_missing_rank_preserves_tertiary_weight(self):
        result = match_greedy([student("s1", "math", None, "english")], [teacher("t1", ("math", "english"))])
        self.assertEqual(result["pairs"][0]["score"], 1_000_001)

    def test_original_urgency_formula_and_rounding(self):
        students = [student("s1", "math", "english", "science", gender_preference="female")]
        teachers = [teacher("t1", ("math", "english")), teacher("t2", ("math", "science"))]
        self.assertEqual(urgency_scores(students, teachers), {"s1": 1900})

    def test_capacity_is_individual_and_supply_counts_people(self):
        students, teachers = [student(f"s{i}") for i in range(3)], [teacher("t1", capacity=2)]
        result = match_greedy(students, teachers)
        self.assertEqual(result["summary"]["matched_count"], 2)
        self.assertEqual(result["remaining_capacity"][0]["remaining_capacity"], 0)
        self.assertEqual(urgency_scores(students, teachers)["s0"], 1000)

    def test_missing_optional_constraints_not_claimed_verified(self):
        result = match_greedy([student("s1")], [teacher("t1")])
        self.assertIsNone(result["pairs"][0]["compatibility"]["availability"])
        self.assertEqual(result["summary"]["availability_evaluated_count"], 0)
        self.assertEqual(result["summary"]["grade_not_evaluated_count"], 1)
        self.assertFalse(match_greedy([student("s1")], [teacher("t1")], {"enforce_availability": True})["pairs"])

    def test_enforced_availability_and_grade(self):
        students = [student("s1", grade="9", slots=("am",))]
        teachers = [teacher("t1", grades=("9",), slots=("pm",)), teacher("t2", grades=("10",), slots=("am",)), teacher("t3", grades=("9",), slots=("am",))]
        result = match_greedy(students, teachers, {"enforce_availability": True, "enforce_grade": True})
        self.assertEqual(result["pairs"][0]["tutor_id"], "t3")

    def test_conservation_check_detects_silently_dropped_student(self):
        students, teachers = [student("s1"), student("s2")], [teacher("t1")]
        result = match_greedy(students, teachers)
        result["unmatched_tutees"] = []
        with self.assertRaisesRegex(ValueError, "Every tutee"):
            validate_result(students, teachers, result)

    def test_quality_recalculates_constraints(self):
        students = [student("s1", gender_preference="female")]
        teachers = [teacher("t1", gender="male")]
        result = match_greedy(students, teachers, {"gender_policy": "legacy_flag"})
        result["pairs"][0]["hard_constraint_violations"] = []
        with self.assertRaisesRegex(ValueError, "hard constraint"):
            validate_result(students, teachers, result)

    def test_quality_rejects_tampered_remaining_capacity(self):
        students, teachers = [student("s1")], [teacher("t1")]
        result = copy.deepcopy(match_greedy(students, teachers))
        result["remaining_capacity"][0]["remaining_capacity"] = 1
        with self.assertRaisesRegex(ValueError, "remaining capacity"):
            validate_result(students, teachers, result)

    def test_bad_configuration_is_rejected(self):
        for config in ({"subject_policy": "typo"}, {"gender_policy": "typo"}, {"enforce_grade": "false"}, {"urgency_scale": float("nan")}, {"weights": {"primary": 1}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                settings_from_config(config)

    def test_invalid_domain_types_rejected(self):
        for bad_capacity in (0, -1, 1.5, True):
            with self.subTest(capacity=bad_capacity), self.assertRaises(ValueError):
                teacher("t1", capacity=bad_capacity)
        with self.assertRaises(ValueError):
            teacher("t1", subjects=("math", "math"))

    def test_greedy_can_sacrifice_total_matches(self):
        # The gender urgency bonus and stable ID tie give s1 the flexible tutor first.
        # A global assignment could instead give s1 t2 and s2 t1.
        students = [student("s1", "math", gender_preference="female"), student("s2", "english")]
        teachers = [teacher("t1", ("math", "english"), gender="female"), teacher("t2", ("math",), gender="female")]
        result = match_greedy(students, teachers)
        self.assertEqual(result["processing_order"], ["s1", "s2"])
        self.assertEqual(result["summary"]["matched_count"], 1)


if __name__ == "__main__":
    unittest.main()
