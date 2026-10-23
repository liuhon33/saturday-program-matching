"""Synthetic import-to-match tests for optional constraints and review locations."""
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from saturday_match.config import load_config
from saturday_match.loader import InputError, load_input
from saturday_match.matcher import match_greedy


BASE = Path(__file__).resolve().parents[1]


class InputPolicyTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(BASE / "config" / "default.yaml")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.counter = 0

    def load(self, role, additions=None, *, config=None):
        if role == "tutor":
            row = {
                "Tutor ID": "tutor-demo-001", "Tutor First Name": "tutor",
                "Tutor Last Name": "001", "Tutor Subjects": "English",
                "Tutor Gender": "Female",
            }
        else:
            row = {
                "Tutee ID": "tutee-demo-001", "Tutee 1 First Name": "tutee",
                "Tutee 1 Last Name": "001", "Tutee 1 Primary Subject": "English",
                "Tutee 1 Secondary Subject": None, "Tutee 1 Tertiary Subject": None,
                "Gender Preference": "Female",
            }
        row.update(additions or {})
        self.counter += 1
        path = Path(self.directory.name) / f"synthetic-{role}-{self.counter}.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append(list(row))
        sheet.append(list(row.values()))
        workbook.save(path)
        workbook.close()
        return load_input(path, role, config or self.config)

    def assert_review(self, loaded, field, code):
        self.assertEqual(len(loaded.records), 0)
        self.assertEqual(loaded.metadata["invalid_rows"], 1)
        self.assertEqual(loaded.ledger[0]["status"], "invalid")
        self.assertEqual(
            [(error["source_row"], error["field"], error["rule"]) for error in loaded.errors],
            [(2, field, code)],
        )

    def test_grade_number_and_spelling_normalize_to_same_band(self):
        self.config["matching"]["enforce_grade"] = True
        tutors = self.load("tutor", {"Teaching Grades": "Grade 9|10|grade 9"})
        for raw in [9, 9.0, "9", "Grade 9", " grade 9 ", "9.0"]:
            with self.subTest(raw=raw):
                students = self.load("tutee", {"Current Grade of Student": raw})
                self.assertFalse(students.errors)
                self.assertEqual(students.records[0].grade, "9")
                self.assertEqual(set(tutors.records[0].grades), {"9", "10"})
                result = match_greedy(students.records, tutors.records, self.config)
                self.assertEqual(result["summary"]["matched_count"], 1)
                self.assertTrue(result["pairs"][0]["compatibility"]["grade"])

    def test_numeric_single_tutor_grade_is_supported(self):
        self.config["matching"]["enforce_grade"] = True
        teachers = self.load("tutor", {"Teaching Grades": 9})
        self.assertFalse(teachers.errors)
        self.assertEqual(teachers.records[0].grades, ("9",))

    def test_enforced_grades_require_both_roles(self):
        self.config["matching"]["enforce_grade"] = True
        self.assert_review(self.load("tutor"), "grades", "tutor_grade_capabilities_required")
        self.assert_review(self.load("tutee"), "grade", "student_grade_required")

    def test_unrecognized_or_out_of_program_grade_requires_review(self):
        self.config["matching"]["enforce_grade"] = True
        for raw in ["6", "13", "Grade9", "nine", "9.5", "9|10"]:
            with self.subTest(raw=raw):
                self.assert_review(self.load("tutee", {"Current Grade of Student": raw}), "grade", "unknown_grade")
        self.assert_review(self.load("tutor", {"Teaching Grades": "9|13"}), "grades", "unknown_grade")

    def test_valid_but_incompatible_grade_is_explicitly_unmatched(self):
        self.config["matching"]["enforce_grade"] = True
        teachers = self.load("tutor", {"Teaching Grades": "Grade 10"})
        students = self.load("tutee", {"Current Grade of Student": 9})
        result = match_greedy(students.records, teachers.records, self.config)
        self.assertEqual(result["summary"]["matched_count"], 0)
        self.assertEqual(result["unmatched_tutees"][0]["rejection_counts"], {"grade_incompatible": 1})

    def test_new_program_grade_can_be_enabled_in_profile(self):
        self.config["matching"]["enforce_grade"] = True
        self.config["grade_values"].append("6")
        teachers = self.load("tutor", {"Teaching Grades": "Grade 6"})
        students = self.load("tutee", {"Current Grade of Student": 6})
        self.assertFalse(teachers.errors + students.errors)
        self.assertEqual(teachers.records[0].grades, ("6",))
        self.assertEqual(students.records[0].grade, "6")
        result = match_greedy(students.records, teachers.records, self.config)
        self.assertEqual(result["summary"]["matched_count"], 1)

    def test_optional_constraints_can_remain_disabled_without_fields(self):
        teachers, students = self.load("tutor"), self.load("tutee")
        self.assertFalse(teachers.errors + students.errors)
        result = match_greedy(students.records, teachers.records, self.config)
        self.assertEqual(result["summary"]["matched_count"], 1)
        self.assertIsNone(result["pairs"][0]["compatibility"]["grade"])
        self.assertIsNone(result["pairs"][0]["compatibility"]["availability"])

    def test_availability_requires_structured_data_for_both_roles(self):
        self.config["matching"]["enforce_availability"] = True
        for role in ("tutor", "tutee"):
            with self.subTest(role=role):
                self.assert_review(self.load(role), "slots", "structured_availability_required")

    def test_availability_case_whitespace_and_duplicate_slots(self):
        self.config["matching"]["enforce_availability"] = True
        teachers = self.load("tutor", {"Available Tutoring Slots": " SAT AM | sat PM | SAT AM "})
        students = self.load("tutee", {"Available Tutoring Slots": "sat am"})
        self.assertEqual(teachers.records[0].slots, ("sat am", "sat pm"))
        result = match_greedy(students.records, teachers.records, self.config)
        self.assertEqual(result["summary"]["matched_count"], 1)
        self.assertTrue(result["pairs"][0]["compatibility"]["availability"])

    def test_nonoverlapping_availability_is_unmatched(self):
        self.config["matching"]["enforce_availability"] = True
        teachers = self.load("tutor", {"Available Tutoring Slots": "sat am"})
        students = self.load("tutee", {"Available Tutoring Slots": "sat pm"})
        result = match_greedy(students.records, teachers.records, self.config)
        self.assertEqual(result["summary"]["matched_count"], 0)
        self.assertEqual(result["unmatched_tutees"][0]["rejection_counts"], {"availability_incompatible": 1})

    def test_subject_errors_identify_the_correct_rank(self):
        for internal, header in [
            ("primary", "Tutee 1 Primary Subject"),
            ("secondary", "Tutee 1 Secondary Subject"),
            ("tertiary", "Tutee 1 Tertiary Subject"),
        ]:
            with self.subTest(field=internal):
                self.assert_review(self.load("tutee", {header: "Unreviewed synthetic subject"}), internal, "unknown_subject")
        self.assert_review(self.load("tutor", {"Tutor Subjects": "English, Unreviewed synthetic subject"}), "subjects", "unknown_subject")

    def test_non_subject_errors_identify_their_fields(self):
        cases = [
            ("tutor", "Tutor First Name", 123, "first_name", "non_text_value"),
            ("tutor", "Tutor Subjects", None, "subjects", "missing_required_subject"),
            ("tutor", "Tutor Gender", "unreviewed choice", "gender", "unknown_gender"),
            ("tutor", "Tutor Capacity", 0, "capacity", "invalid_capacity"),
            ("tutee", "Gender Preference", "Any", "gender_preference", "unknown_gender_preference"),
            ("tutee", "Available Tutoring Slots", 123, "slots", "non_text_value"),
        ]
        for role, header, value, field, rule in cases:
            with self.subTest(role=role, field=field):
                self.assert_review(self.load(role, {header: value}), field, rule)

    def test_unknown_column_policy_is_enforced(self):
        accepted = self.load("tutor", {"Unrelated synthetic note": "invented"})
        self.assertEqual(accepted.metadata["ignored_column_count"], 1)
        self.config["input_policy"]["unknown_columns"] = "error"
        with self.assertRaisesRegex(InputError, "unmapped_columns_present"):
            self.load("tutor", {"Unrelated synthetic note": "invented"})


if __name__ == "__main__":
    unittest.main()
