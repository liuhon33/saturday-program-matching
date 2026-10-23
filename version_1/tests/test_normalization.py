"""Synthetic tests for versioned form choices; no historical participant rows."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from saturday_match.config import ConfigError, load_config, validate_config
from saturday_match.normalization import (
    NormalizationError, canonical_gender, canonical_preference, canonical_subject,
    normalize_text, normalize_with_events, parse_subjects,
)


CONFIG = Path(__file__).resolve().parents[1] / "config" / "default.yaml"


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)

    def test_multiselect_grade_label_internal_commas(self):
        self.assertEqual(
            parse_subjects("English, Math Grades 7, 8, 9, 10, Science Grades 7, 8, 9, 10, Biology", self.config),
            ("english", "math7_10", "science7_10", "biology"),
        )

    def test_each_supported_separator_and_longest_labels(self):
        for separator in [", ", "; ", "|", "\n", "\r\n"]:
            with self.subTest(separator=repr(separator)):
                self.assertEqual(parse_subjects(f"Math Grades 7, 8, 9, 10{separator}Economics (Grade 11/12)", self.config), ("math7_10", "economics11_12"))

    def test_unknown_tail_rejects_entire_field(self):
        events = []
        with self.assertRaises(NormalizationError) as caught:
            parse_subjects("English, mystery offering", self.config, on_change=events.append)
        self.assertEqual(caught.exception.code, "unknown_subject")
        self.assertNotIn("subject_list_to_canonical_ids", events)
        self.assertNotIn("mystery", str(caught.exception))

    def test_subject_substring_never_counts_as_match(self):
        for value in ["English literature essay support", "Computer", "Data", "Math"]:
            with self.subTest(value=value), self.assertRaises(NormalizationError):
                canonical_subject(value, self.config)

    def test_unreviewed_typo_suggests_but_does_not_accept(self):
        with self.assertRaises(NormalizationError) as caught:
            canonical_subject("Englihs", self.config)
        self.assertEqual(caught.exception.code, "unknown_subject")
        self.assertIn("English", caught.exception.suggestions)

    def test_approved_typo_records_rule(self):
        result, events = normalize_with_events("primary", "Englsh", self.config)
        self.assertEqual(result, "english")
        self.assertIn("approved_typo_alias", events)

    def test_known_year_labels_share_canonical_ids(self):
        self.assertEqual(canonical_subject("Math Grade 11", self.config), "functions11")
        self.assertEqual(canonical_subject("Grade 11 Math", self.config), "functions11")
        self.assertEqual(canonical_subject("Calculus and/or Functions (Grade 12)", self.config), "calculus12")
        self.assertEqual(canonical_subject("Social Science", self.config), "social_sciences")

    def test_whitespace_case_and_unicode_normalized(self):
        self.assertEqual(canonical_subject("  eNGlIsH\u00a0 ", self.config), "english")
        self.assertEqual(normalize_text("  tutor\u00a0 001  "), "tutor 001")
        self.assertEqual(canonical_subject("Ｅｎｇｌｉｓｈ", self.config), "english")

    def test_optional_empty_and_no_subject_markers(self):
        for value in [None, float("nan"), "", "  ", "N/A", "No", "none", "No third subject"]:
            with self.subTest(value=str(value)):
                self.assertIsNone(canonical_subject(value, self.config, allow_none=True))
                self.assertEqual(parse_subjects(value, self.config), ())

    def test_primary_never_accepts_no_subject_marker(self):
        for value in [None, "", "None", "N/A"]:
            with self.subTest(value=value), self.assertRaisesRegex(NormalizationError, "missing_required_subject"):
                canonical_subject(value, self.config)

    def test_text_nan_is_not_assumed_missing(self):
        with self.assertRaises(NormalizationError):
            canonical_subject("nan", self.config, allow_none=True)

    def test_numeric_and_boolean_subjects_rejected(self):
        for value in [123, False, True, 7.0, float("inf")]:
            with self.subTest(value=value), self.assertRaisesRegex(NormalizationError, "non_text_value"):
                parse_subjects(value, self.config)

    def test_duplicates_removed_with_audit_code(self):
        result, events = normalize_with_events("subjects", "English, english, Math Grade 11, Functions (Grade 11)", self.config)
        self.assertEqual(result, ("english", "functions11"))
        self.assertIn("duplicate_subject_removed", events)

    def test_empty_token_rejected(self):
        for value in ["English,", "English,,Biology", "English; ;Biology", ",English"]:
            with self.subTest(value=value), self.assertRaises(NormalizationError):
                parse_subjects(value, self.config)

    def test_null_marker_cannot_hide_other_choices(self):
        with self.assertRaises(NormalizationError):
            parse_subjects("None, English", self.config)

    def test_internal_ids_are_supported_for_cleaned_data(self):
        self.assertEqual(parse_subjects(["english", "functions11"], self.config), ("english", "functions11"))

    def test_gender_values_and_unknown_do_not_become_binary(self):
        self.assertEqual(canonical_gender(" Non-binary ", self.config), "nonbinary")
        self.assertEqual(canonical_gender("Genderfluid", self.config), "genderfluid")
        self.assertEqual(canonical_gender("Any", self.config), "unspecified")
        self.assertIsNone(canonical_gender(None, self.config))
        with self.assertRaises(NormalizationError):
            canonical_gender("New form answer", self.config)

    def test_no_preference_is_distinct_from_unspecified_gender(self):
        self.assertIsNone(canonical_preference("No preference", self.config))
        self.assertEqual(canonical_preference("Female", self.config), "female")
        self.assertEqual(canonical_gender("Prefer not to specify", self.config), "unspecified")
        for value in ["Any", "Prefer not to specify"]:
            with self.subTest(value=value), self.assertRaisesRegex(NormalizationError, "unknown_gender_preference"):
                canonical_preference(value, self.config)

    def test_missing_preference_policy_is_explicit_and_audited(self):
        result, events = normalize_with_events("gender_preference", None, self.config)
        self.assertIsNone(result)
        self.assertIn("missing_preference_no_requirement", events)
        self.config["normalization"]["missing_preference"] = "error"
        with self.assertRaisesRegex(NormalizationError, "missing_gender_preference"):
            canonical_preference(None, self.config)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)

    def test_synthetic_profile_is_self_contained(self):
        cfg = load_config(CONFIG.with_name("synthetic.yaml"))
        self.assertEqual(cfg["schema_version"], "synthetic-demo-v1")
        self.assertEqual(set(cfg["subjects"]), set(self.config["subjects"]))

    def test_reject_duplicate_yaml_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("schema_version: first\nschema_version: second\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "Duplicate YAML"):
                load_config(path)

    def test_reject_ambiguous_subject_alias(self):
        self.config["subjects"]["physics"]["aliases"].append("English")
        with self.assertRaisesRegex(ConfigError, "Ambiguous subject"):
            validate_config(self.config)

    def test_reject_ambiguous_column_alias(self):
        self.config["columns"]["tutor"]["id"]["aliases"].append("Tutor First Name")
        with self.assertRaisesRegex(ConfigError, "Ambiguous column"):
            validate_config(self.config)

    def test_reject_overlapping_null_marker(self):
        self.config["no_subject"].append("English")
        with self.assertRaisesRegex(ConfigError, "overlaps"):
            validate_config(self.config)

    def test_weights_must_be_finite_nonnegative_not_boolean(self):
        for weight in [-1, float("nan"), float("inf"), "100", True]:
            cfg = deepcopy(self.config)
            cfg["matching"]["weights"]["primary"] = weight
            with self.subTest(weight=weight), self.assertRaises(ConfigError):
                validate_config(cfg)

    def test_policy_misspelling_rejected(self):
        self.config["matching"]["subject_policy"] = "primry"
        with self.assertRaisesRegex(ConfigError, "subject_policy"):
            validate_config(self.config)

    def test_unknown_setting_rejected(self):
        self.config["matching"]["enforce_availabilty"] = True
        with self.assertRaisesRegex(ConfigError, "unsupported"):
            validate_config(self.config)

    def test_capacity_must_be_positive_integer(self):
        for capacity in [0, -1, 1.5, True]:
            cfg = deepcopy(self.config)
            cfg["matching"]["default_capacity"] = capacity
            with self.subTest(capacity=capacity), self.assertRaises(ConfigError):
                validate_config(cfg)

    def test_grade_values_require_nonempty_unique_digit_strings(self):
        for grades in [[], [7], ["7", "7"], ["Grade 7"], ["7.0"], [" 7 "], ["-1"]]:
            cfg = deepcopy(self.config)
            cfg["grade_values"] = grades
            with self.subTest(grades=grades), self.assertRaises(ConfigError):
                validate_config(cfg)

    def test_approved_grade_extension_is_configurable(self):
        self.config["grade_values"].append("6")
        self.assertIn("6", validate_config(self.config)["grade_values"])

    def test_config_validation_does_not_mutate_input(self):
        original = deepcopy(self.config)
        validated = validate_config(self.config)
        validated["subjects"]["english"]["label"] = "changed"
        self.assertEqual(self.config, original)


if __name__ == "__main__":
    unittest.main()
