"""Synthetic integration tests: private import, review, matching, and export.

Every fixture is generated in an OS temporary directory. No historical workbook
or participant information is read, copied, or written by this module.
"""

import contextlib
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook, load_workbook

from saturday_match.cli import main
from saturday_match.config import load_config, validate_config
from saturday_match.loader import InputError, fingerprint, load_input, read_corrections
from saturday_match.matcher import match_greedy
from saturday_match.output import export_cleaning, export_matches, workbook


BASE = Path(__file__).resolve().parents[1]
CONFIG = BASE / "config" / "synthetic.yaml"
TUTOR_HEADERS = ["Tutor ID", "Tutor First Name", "Tutor Last Name", "Tutor Subjects", "Tutor Gender", "Tutor Email"]
TUTEE_HEADERS = ["Tutee ID", "Tutee 1 First Name", "Tutee 1 Last Name", "Tutee 1 Primary Subject", "Gender Preference", "Tutee Email"]


def create_input(path, headers, rows, *, literal_strings=False):
    book = Workbook()
    sheet = book.active
    sheet.title = "Sheet1"
    for row in [headers, *rows]:
        sheet.append(row)
    if literal_strings:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    book.save(path)
    book.close()
    return path


class ImportExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="saturday-synthetic-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = load_config(CONFIG)

    def tutors(self, rows=None, headers=None, *, filename="tutors.xlsx", literal_strings=False):
        if rows is None:
            rows = [["tutor-001", "tutor", "001", "English", "Female", "tutor001@example.invalid"]]
        return create_input(self.directory / filename, headers or TUTOR_HEADERS, rows, literal_strings=literal_strings)

    def tutees(self, rows=None, headers=None, *, filename="tutees.xlsx", literal_strings=False):
        if rows is None:
            rows = [["tutee-001", "tutee", "001", "English", "No preference", "tutee001@example.invalid"]]
        return create_input(self.directory / filename, headers or TUTEE_HEADERS, rows, literal_strings=literal_strings)

    def corrections(self, source, changes, *, digest=None):
        path = self.directory / "corrections.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["role", "source_sha256", "row", "field", "value"])
            writer.writeheader()
            for field, row, value in changes:
                writer.writerow({"role": "tutee", "source_sha256": digest or fingerprint(source), "row": row, "field": field, "value": value})
        return read_corrections(path)

    def invoke(self, tutors, tutees, output, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["run", "--config", str(CONFIG), "--tutors", str(tutors), "--tutees", str(tutees), "--output-dir", str(output), *extra])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_run_does_not_modify_raw_workbooks(self):
        tutors, tutees = self.tutors(), self.tutees()
        before = {path: fingerprint(path) for path in (tutors, tutees)}
        destination = self.directory / "read-only-test"
        code, _, _ = self.invoke(tutors, tutees, destination)
        self.assertEqual(code, 0)
        self.assertEqual(before, {path: fingerprint(path) for path in before})
        self.assertTrue((destination / "matches.xlsx").exists())
        self.assertEqual(json.loads((destination / "summary.json").read_text())["matched_count"], 1)

    def test_same_names_with_distinct_ids_are_retained(self):
        path = self.tutees([
            ["student-001", "tutee", "same", "English", "No preference", "same@example.invalid"],
            ["student-002", "tutee", "same", "English", "No preference", "same@example.invalid"],
        ])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(len(loaded.records), 2)
        self.assertEqual(len({person.id for person in loaded.records}), 2)
        self.assertEqual(sum(event["rule"] == "same_name_distinct_ids_retained" for event in loaded.events), 2)

    def test_same_names_different_emails_have_distinct_fallback_ids(self):
        path = self.tutees([
            [None, "tutee", "same", "English", "No preference", "first@example.invalid"],
            [None, "tutee", "same", "English", "No preference", "second@example.invalid"],
        ])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(len(loaded.records), 2)
        self.assertEqual(len({person.id for person in loaded.records}), 2)

    def test_possible_duplicate_submissions_are_quarantined_not_dropped(self):
        row = [None, "tutee", "same", "English", "No preference", "same@example.invalid"]
        path = self.tutees([row, row.copy()])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.records, [])
        self.assertEqual(loaded.metadata["invalid_rows"], 2)
        self.assertEqual(len(loaded.ledger), 2)
        self.assertEqual(sum(event["rule"] == "duplicate_identity_requires_review" for event in loaded.errors), 2)

    def test_duplicate_explicit_ids_quarantine_different_names(self):
        path = self.tutees([
            ["shared-id", "tutee", "001", "English", "No preference", "first@example.invalid"],
            ["shared-id", "tutee", "002", "English", "No preference", "second@example.invalid"],
        ])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.records, [])
        self.assertEqual(loaded.metadata["invalid_rows"], 2)

    def test_unknown_column_ignored_without_response_leak(self):
        path = self.tutees([["s1", "tutee", "001", "English", "No preference", None, "PRIVATE-UNMAPPED-SENTINEL"]], headers=TUTEE_HEADERS + ["Home address"])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.metadata["ignored_column_count"], 1)
        self.assertEqual(len(loaded.records), 1)
        self.assertNotIn("PRIVATE-UNMAPPED-SENTINEL", json.dumps(loaded.events))

    def test_unknown_column_error_policy_is_enforced(self):
        path = self.tutees([["s1", "tutee", "001", "English", "No preference", None, "PRIVATE-UNMAPPED-SENTINEL"]], headers=TUTEE_HEADERS + ["Unmapped new question"])
        config = copy.deepcopy(self.config)
        config["input_policy"]["unknown_columns"] = "error"
        config = validate_config(config)
        with self.assertRaises(InputError):
            load_input(path, "tutee", config)

    def test_unknown_subject_quarantined_without_guess_or_value_leak(self):
        sentinel = "PRIVATE-UNKNOWN-SUBJECT-SENTINEL"
        path = self.tutees([["s1", "tutee", "001", sentinel, "No preference", "private@example.invalid"]])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.records, [])
        self.assertEqual(loaded.metadata["invalid_rows"], 1)
        self.assertIn("unknown_subject", [event["rule"] for event in loaded.errors])
        self.assertNotIn(sentinel, json.dumps(loaded.events))
        self.assertNotIn("private@example.invalid", json.dumps(loaded.events))

    def test_formula_in_consumed_xlsx_field_requires_review(self):
        path = self.tutees([["s1", "=1+1", "001", "English", "No preference", None]])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.records, [])
        self.assertIn("formula_in_consumed_field", [event["rule"] for event in loaded.errors])

    def test_formula_like_literal_name_stays_literal_in_excel_output(self):
        tutors = load_input(self.tutors(), "tutor", self.config)
        tutees = load_input(self.tutees([["s1", "=1+1", "001", "English", "No preference", "=2+2"]], literal_strings=True), "tutee", self.config)
        self.assertEqual(len(tutees.records), 1)
        output = self.directory / "literal-output"
        output.mkdir()
        result = match_greedy(tutees.records, tutors.records, self.config)
        export_cleaning(output, [tutors, tutees])
        export_matches(output, result, tutees, tutors, include_contacts=True)
        for filename in ("cleaned_tutees.xlsx", "matches.xlsx"):
            book = load_workbook(output / filename, data_only=False, read_only=True)
            try:
                cells = [cell for sheet in book for row in sheet for cell in row if isinstance(cell.value, str) and cell.value.startswith("=")]
                self.assertTrue(cells)
                self.assertTrue(all(cell.data_type == "s" for cell in cells))
            finally:
                book.close()

    def test_row_ledger_accounts_for_valid_invalid_blank_and_duplicates(self):
        duplicate = ["same-id", "tutee", "same", "English", "No preference", None]
        rows = [duplicate, [None] * len(TUTEE_HEADERS), ["s-bad", "tutee", "bad", "unapproved-subject", "No preference", None], duplicate.copy(), ["s-good", "tutee", "good", "English", "No preference", None]]
        loaded = load_input(self.tutees(rows), "tutee", self.config)
        self.assertEqual(len(loaded.ledger), 5)
        self.assertEqual((loaded.metadata["valid_records"], loaded.metadata["invalid_rows"], loaded.metadata["blank_rows"]), (1, 3, 1))
        self.assertEqual([row["source_row"] for row in loaded.ledger], [2, 3, 4, 5, 6])

    def test_audit_files_exclude_private_values(self):
        sentinels = ("PRIVATE-FIRST-SENTINEL", "PRIVATE-LAST-SENTINEL", "private-contact-sentinel@example.invalid")
        path = self.tutees([[None, sentinels[0], sentinels[1], "  English ", "No preference", sentinels[2]]])
        loaded = load_input(path, "tutee", self.config)
        output = self.directory / "audit-output"
        output.mkdir()
        export_cleaning(output, [loaded])
        for filename in ("cleaning_audit.json", "input_summary.json", "row_status.csv"):
            contents = (output / filename).read_text(encoding="utf-8-sig")
            for sentinel in sentinels:
                self.assertNotIn(sentinel, contents)
        self.assertIn(sentinels[0], (output / "normalized_tutees.json").read_text())

    def test_hash_bound_correction_applies_without_touching_source(self):
        path = self.tutees([["s1", "tutee", "001", "unapproved-subject", "No preference", None]])
        before = fingerprint(path)
        corrections = self.corrections(path, [("primary", 2, "English")])
        loaded = load_input(path, "tutee", self.config, corrections)
        self.assertEqual(len(loaded.records), 1)
        self.assertEqual(loaded.records[0].preferences[0], "english")
        self.assertEqual(fingerprint(path), before)
        self.assertIn("explicit_hash_bound_correction", [event["rule"] for event in loaded.events])

    def test_stale_correction_hash_is_rejected(self):
        path = self.tutees()
        corrections = self.corrections(path, [("primary", 2, "English")], digest="0" * 64)
        with self.assertRaisesRegex(InputError, "source_hash_mismatch"):
            load_input(path, "tutee", self.config, corrections)

    def test_corrections_reject_ambiguous_headers_and_row_widths(self):
        digest = fingerprint(self.tutees())
        header = "role,source_sha256,row,field,value\n"
        cases = {
            "duplicate-header": "role,source_sha256,row,field,value,field\n" + f"tutee,{digest},2,primary,English,primary\n",
            "overflow": header + f"tutee,{digest},2,primary,English,Physics\n",
            "missing-value": header + f"tutee,{digest},2,primary\n",
        }
        for case, contents in cases.items():
            with self.subTest(case=case):
                path = self.directory / f"corrections-{case}.csv"
                path.write_text(contents, encoding="utf-8")
                with self.assertRaises(InputError):
                    read_corrections(path)

    def test_csv_blank_line_is_accounted_as_blank(self):
        path = self.directory / "tutees.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(TUTEE_HEADERS)
            writer.writerow([])
            writer.writerow(["s1", "tutee", "001", "English", "No preference", None])
        loaded = load_input(path, "tutee", self.config)
        self.assertEqual(loaded.metadata["blank_rows"], 1)
        self.assertEqual(loaded.metadata["invalid_rows"], 0)
        self.assertEqual(loaded.metadata["valid_records"], 1)

    def test_correction_unknown_field_is_rejected(self):
        path = self.tutees()
        corrections = self.corrections(path, [("misspelled-internal-field", 2, "English")])
        with self.assertRaisesRegex(InputError, "location_not_found"):
            load_input(path, "tutee", self.config, corrections)

    def test_correction_to_blank_row_is_not_silently_ignored(self):
        path = self.tutees([[None] * len(TUTEE_HEADERS), ["s1", "tutee", "001", "English", "No preference", None]])
        corrections = self.corrections(path, [("primary", 2, "English")])
        with self.assertRaises(InputError):
            load_input(path, "tutee", self.config, corrections)

    def test_cli_blocks_invalid_rows_unless_partial_is_explicit(self):
        tutors = self.tutors()
        tutees = self.tutees([
            ["s1", "PRIVATE-FIRST-SENTINEL", "001", "English", "No preference", "private-contact@example.invalid"],
            ["s2", "tutee", "002", "PRIVATE-UNKNOWN-SENTINEL", "No preference", None],
        ])
        blocked = self.directory / "blocked-run"
        code, stdout, stderr = self.invoke(tutors, tutees, blocked)
        self.assertEqual(code, 2)
        self.assertFalse((blocked / "matches.xlsx").exists())
        self.assertEqual(json.loads((blocked / "run_manifest.json").read_text())["status"], "needs_review")
        partial = self.directory / "partial-run"
        code, partial_stdout, partial_stderr = self.invoke(tutors, tutees, partial, "--allow-partial")
        self.assertEqual(code, 0)
        self.assertTrue((partial / "matches.xlsx").exists())
        summary = json.loads((partial / "summary.json").read_text())
        self.assertEqual(summary["invalid_rows"], 1)
        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(json.loads((partial / "run_manifest.json").read_text())["status"], "completed_with_invalid_rows")
        for sentinel in ("PRIVATE-FIRST-SENTINEL", "PRIVATE-UNKNOWN-SENTINEL", "private-contact@example.invalid"):
            self.assertNotIn(sentinel, stdout + stderr + partial_stdout + partial_stderr)

    def test_contacts_are_opt_in_and_local(self):
        tutors, tutees = self.tutors(), self.tutees()
        for include in (False, True):
            destination = self.directory / ("contacts" if include else "no-contacts")
            code, _, _ = self.invoke(tutors, tutees, destination, *(["--include-contacts"] if include else []))
            self.assertEqual(code, 0)
            book = load_workbook(destination / "matches.xlsx", read_only=True)
            try:
                self.assertEqual("Private Contacts" in book.sheetnames, include)
            finally:
                book.close()

    def test_existing_output_is_never_replaced(self):
        path = self.directory / "existing.xlsx"
        path.write_bytes(b"synthetic original sentinel")
        before = fingerprint(path)
        with self.assertRaises(FileExistsError):
            workbook(path, {"Test": (["value"], [["new"]])})
        self.assertEqual(fingerprint(path), before)
        destination = self.directory / "existing-directory"
        destination.mkdir()
        code, _, _ = self.invoke(self.tutors(), self.tutees(), destination)
        self.assertEqual(code, 2)
        self.assertEqual(list(destination.iterdir()), [])

    def test_corrupt_workbook_returns_safe_cli_failure(self):
        path = self.directory / "PRIVATE-PATH-SENTINEL.xlsx"
        path.write_bytes(b"not an xlsx ZIP container")
        code, stdout, stderr = self.invoke(path, self.tutees(), self.directory / "corrupt-run")
        self.assertEqual(code, 2)
        self.assertNotIn("PRIVATE-PATH-SENTINEL", stdout + stderr)
        self.assertNotIn("Traceback", stdout + stderr)

    def test_all_synthetic_demo_pairs_run_without_invalid_rows(self):
        for prefix in ("2023", "2024", "scratch_"):
            with self.subTest(prefix=prefix):
                tutors = load_input(BASE / "data" / f"{prefix}tutor.xlsx", "tutor", self.config)
                tutees = load_input(BASE / "data" / f"{prefix}tutee.xlsx", "tutee", self.config)
                self.assertFalse(tutors.errors)
                self.assertFalse(tutees.errors)
                result = match_greedy(tutees.records, tutors.records, self.config)
                self.assertEqual(result["summary"]["matched_count"] + result["summary"]["unmatched_count"], len(tutees.records))
                self.assertEqual(result["summary"]["hard_constraint_violations"], 0)


if __name__ == "__main__":
    unittest.main()
