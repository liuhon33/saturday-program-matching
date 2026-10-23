"""Generate full-size fictional examples in the original questionnaire layouts.

Only question headings, sheet names and row counts mirror historical forms.
Every response is invented independently: no historical response is reused and
this program never reads historical workbooks. Existing files are not replaced.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FIXED_TIME = datetime(2000, 1, 1)
Cell = str | int | None
Rows = list[list[Cell]]

# Form structure only: duplicate guardian email headings and blank columns are
# deliberate. No participant response values contributed to these declarations.
FORM_HEADERS = {'2023tutee.xlsx': {'Sheet1': ['Email Address',
                               'Tutee 1 First Name',
                               'Tutee 1 Last Name',
                               'Gender',
                               'Age by December 31st, 2023',
                               'Home Address (Address, City, Country, Postal Code) ',
                               'Cell Phone Number',
                               'Email (Most frequently used)',
                               'Confirm Email Address',
                               'Reason for referral (if applicable).',
                               'Were you part of the Saturday Program in the past?',
                               'If you answered "yes" to the previous question, how many years have you been '
                               'a part of the Saturday Program?',
                               'First Name',
                               'Last Name',
                               'Relationship to Student',
                               'Primary Contact Phone Number',
                               'Secondary Contact Phone Number',
                               'Email Address',
                               'Confirm Email Address',
                               'Name of School Student is Attending',
                               'Current Grade of Student',
                               'What system does your school use to teach?',
                               'What is your preferred language?',
                               'What other languages do you speak?',
                               'Tutee 1 Primary Subject',
                               None,
                               'Tutee 1 Secondary Subject',
                               None,
                               'Tutee 1 Tertiary Subject',
                               None,
                               'Gender Preference',
                               'Is there anything else you would like us to know? (such as dates that you '
                               "know you won't be available or special considerations)",
                               'What is your reason for participating in the Saturday Program 2024 session?',
                               'What are your short term academic/career goals?',
                               'What field of study are you interested in (or interested in finding out more '
                               'about)? ',
                               'Is there any additional information you would like your tutor to know? ',
                               'Is there any additional information you would like the program co-directors '
                               'to know?',
                               'Submitted Form',
                               'Timestamp',
                               None]},
 '2023tutor.xlsx': {'Sheet1': ['Timestamp_Tutor',
                               'Email Address',
                               'Tutor First Name',
                               'Tutor Last Name',
                               'UofT Student Number',
                               'UTORid',
                               'Year of Study',
                               'What program are you/were you in?',
                               'Primary Phone Number',
                               'Primary Email Address',
                               'Confirm Email',
                               'I agree to receiving Saturday Program newsletter communications.',
                               'Tutor Gender',
                               'Please list all the languages (outside of English) that you feel comfortable '
                               'communicating in:',
                               'Have you volunteered with us before? ',
                               'If yes, how many years and in what position(s)',
                               'Do you have a currently valid (obtained after January 2023) Police Reference '
                               'Check (PRC)?',
                               'Where do you currently reside? ',
                               'Core Volunteer',
                               'Do you have any prior tutoring experience?',
                               'If yes, please describe your previous tutoring experience.',
                               'Are you willing to tutor two tutees?',
                               'Tutor Subjects',
                               'Are you willing to tutor if the need arises?',
                               'If the need arises, what subjects are you comfortable tutoring? (Select all '
                               'that apply)',
                               'How did you hear about us?',
                               'Is there anything else you would like us to know?']},
 '2024tutee.xlsx': {'Sheet1': ['Timestamp',
                               'Email Address',
                               'Tutee 1 First Name',
                               'Tutee 1 Last Name',
                               'Gender',
                               'Age by December 31st, 2024',
                               'Home Address (Address, City, Country, Postal Code)',
                               'Cell Phone Number',
                               'Email (Most frequently used)',
                               'Confirm Email Address',
                               'I agree to receive Saturday Program newsletter communications.',
                               'How did you find out about the Saturday Program?',
                               'Reason for referral (if applicable).',
                               'Were you part of the Saturday Program in the past?',
                               'If you answered "yes" to the previous question, how many years have you been '
                               'a part of the Saturday Program?',
                               'First Name',
                               'Last Name',
                               'Relationship to Student',
                               'Primary Contact Phone Number',
                               'Secondary Contact Phone Number',
                               'Email Address',
                               'Confirm Email Address',
                               'Name of School Student is Attending',
                               'Current Grade of Student',
                               'What system does your school use to teach?',
                               'What is your preferred language?',
                               'What other languages do you speak?',
                               'Tutee 1 Primary Subject',
                               'Tutee 1 Secondary Subject',
                               'Tutee 1 Tertiary Subject',
                               'Gender Preference',
                               'Is there anything else you would like us to know? (such as dates that you '
                               "know you won't be available or special considerations)",
                               'What is your reason for participating in the Saturday Program 2025 session?',
                               'What are your short term academic/career goals?',
                               'What field of study are you interested in (or interested in finding out more '
                               'about)?',
                               'Is there any additional information you would like your tutor to know?',
                               'Is there any additional information you would like the program co-directors '
                               'to know?',
                               'Which information session would you like to attend?',
                               'Email found in sheet 2 (1 means yes)']},
 '2024tutor.xlsx': {'Sheet1': ['Email Address',
                               'Tutor First Name',
                               'Tutor Last Name',
                               'UofT Student Number',
                               'UTORid',
                               'Year of Study',
                               'What program are you/were you in?',
                               'Primary Phone Number',
                               'Primary Email Address',
                               'Confirm Email',
                               'I agree to receiving Saturday Program newsletter communications.',
                               'Tutor Gender',
                               'Please list all the languages (outside of English) that you feel comfortable '
                               'communicating in:',
                               'Have you volunteered with us before?',
                               'If yes, how many years and in what position(s)',
                               'Do you have a currently valid (obtained after January 2024) Police Reference '
                               'Check (PRC)?',
                               'Where do you currently reside?',
                               'What position would you like to sign-up for?',
                               'Do you have any prior tutoring experience?',
                               'If yes, please describe your previous tutoring experience (within 100 words)',
                               'Are you willing to tutor two tutees?',
                               'Tutor Subjects',
                               'Are you willing to tutor if the need arises?',
                               'Tutor Subjects2',
                               'Pease upload a video of yourself answering at least one of the following '
                               'prompts below (length: maximum 2 minutes):\n'
                               '\n'
                               'Why are you interested in becoming a tutor and joining the Saturday Program? '
                               'Please describe what qualities you have that will make you a',
                               'How did you hear about us?',
                               'Is there anything else you would like us to know?',
                               'Please carefully read and agree to these terms.']},
 'scratch_tutee.xlsx': {'Sheet1': ['Timestamp',
                                   'Email Address',
                                   'Tutee 1 First Name',
                                   'Tutee 1 Last Name',
                                   'Gender',
                                   'Age by December 31st, 2024',
                                   'Home Address (Address, City, Country, Postal Code)',
                                   'Cell Phone Number',
                                   'Email (Most frequently used)',
                                   'Confirm Email Address',
                                   'I agree to receive Saturday Program newsletter communications.',
                                   'How did you find out about the Saturday Program?',
                                   'Reason for referral (if applicable).',
                                   'Were you part of the Saturday Program in the past?',
                                   'If you answered "yes" to the previous question, how many years have you '
                                   'been a part of the Saturday Program?',
                                   'First Name',
                                   'Last Name',
                                   'Relationship to Student',
                                   'Primary Contact Phone Number',
                                   'Secondary Contact Phone Number',
                                   'Email Address',
                                   'Confirm Email Address',
                                   'Name of School Student is Attending',
                                   'Current Grade of Student',
                                   'What system does your school use to teach?',
                                   'What is your preferred language?',
                                   'What other languages do you speak?',
                                   'Tutee 1 Primary Subject',
                                   'Tutee 1 Secondary Subject',
                                   'Tutee 1 Tertiary Subject',
                                   'Gender Preference',
                                   'Is there anything else you would like us to know? (such as dates that '
                                   "you know you won't be available or special considerations)",
                                   'What is your reason for participating in the Saturday Program 2025 '
                                   'session?',
                                   'What are your short term academic/career goals?',
                                   'What field of study are you interested in (or interested in finding out '
                                   'more about)?',
                                   'Is there any additional information you would like your tutor to know?',
                                   'Is there any additional information you would like the program '
                                   'co-directors to know?',
                                   'Which information session would you like to attend?',
                                   'Attendance'],
                        'Sheet2': ['Email', 'Email found in sheet 1', 'Note']},
 'scratch_tutor.xlsx': {'Sheet1': ['Email Address',
                                   'Tutor First Name',
                                   'Tutor Last Name',
                                   'UofT Student Number',
                                   'UTORid',
                                   'Year of Study',
                                   'What program are you/were you in?',
                                   'Primary Phone Number',
                                   'Primary Email Address',
                                   'Confirm Email',
                                   'I agree to receiving Saturday Program newsletter communications.',
                                   'Tutor Gender',
                                   'Please list all the languages (outside of English) that you feel '
                                   'comfortable communicating in:',
                                   'Have you volunteered with us before?',
                                   'If yes, how many years and in what position(s)',
                                   'Do you have a currently valid (obtained after January 2024) Police '
                                   'Reference Check (PRC)?',
                                   'Where do you currently reside?',
                                   'What position would you like to sign-up for?',
                                   'Do you have any prior tutoring experience?',
                                   'If yes, please describe your previous tutoring experience (within 100 '
                                   'words)',
                                   'Are you willing to tutor two tutees?',
                                   'What subjects are you comfortable tutoring in? (Select all that apply)',
                                   'Are you willing to tutor if the need arises?',
                                   'Tutor Subjects',
                                   'Pease upload a video of yourself answering at least one of the following '
                                   'prompts below (length: maximum 2 minutes):\n'
                                   '\n'
                                   'Why are you interested in becoming a tutor and joining the Saturday '
                                   'Program? Please describe what qualities you have that will make you a',
                                   'How did you hear about us?',
                                   'Is there anything else you would like us to know?',
                                   'Please carefully read and agree to these terms.']}}

CASE_SIZES = {"2023": (93, 99), "2024": (80, 71), "scratch": (91, 142)}
TUTOR_CHOICES = [
    ("English; Social Sciences", "Female"),
    ("Math Grades 7, 8, 9, 10; Functions (Grade 11)", "Male"),
    ("Biology; Chemistry", "Female"),
    ("Physics; Calculus and/or Advanced Functions (Grade 12)", "Male"),
    ("French; English", "Female"),
    ("Computer Science; Data Management (Grade 12)", "Male"),
    ("Science Grades 7, 8, 9, 10; Chemistry", "Female"),
    ("English; History", "Male"),
    ("Math Grades 7, 8, 9, 10; Science Grades 7, 8, 9, 10", "Female"),
    ("Biology; Physics", "Male"),
    ("French; Social Sciences", "Non-binary"),
    ("Chemistry; Math Grades 7, 8, 9, 10", "Male"),
]
TUTEE_CHOICES = [
    ("English", "French", None, "Female"),
    ("Math Grades 7, 8, 9, 10", "Functions (Grade 11)", None, "No preference"),
    ("Biology", "Chemistry", None, "No preference"),
    ("Physics", "Calculus and/or Advanced Functions (Grade 12)", None, "Male"),
    ("French", "English", None, "Female"),
    ("Computer Science", "Data Management (Grade 12)", None, "No preference"),
    ("Science Grades 7, 8, 9, 10", "Chemistry", "Biology", "No preference"),
    ("History", "Social Sciences", "English", "No preference"),
    ("English", "Social Sciences", None, "No preference"),
    ("Math Grades 7, 8, 9, 10", "Physics", None, "No preference"),
    ("Chemistry", "Biology", None, "No preference"),
    ("Calculus and/or Advanced Functions (Grade 12)", "Data Management (Grade 12)", None, "No preference"),
    # These deliberately invented cases have no tutor satisfying both rules.
    ("Functions (Grade 11)", "Math Grades 7, 8, 9, 10", None, "Female"),
    ("Law", "English", None, "No preference"),
    ("English", "History", None, "Female"),
    ("Math Grades 7, 8, 9, 10", "Science Grades 7, 8, 9, 10", None, "No preference"),
]
PROGRAMS = ["English studies", "Mathematics", "Biology", "Physics", "French studies", "Computer science"]
GOALS = [
    "Build a regular study routine and practise explaining my answers.",
    "Feel more confident solving homework questions independently.",
    "Explore science and technology courses for future study.",
    "Improve essay planning and learn how to check my work.",
]


def _email(role: str, case: str, number: int) -> str:
    return f"{role}.{case}.{number:03d}@example.invalid"


def _stamp(case: str, number: int) -> str:
    year = 2023 if case == "2023" else 2024
    return (datetime(year, 10, 1, 9) + timedelta(minutes=number * 13)).isoformat(sep=" ")


def _tutor_row(headers: list[Cell], case: str, number: int, count: int) -> list[Cell]:
    subjects, gender = TUTOR_CHOICES[(number - 1) % len(TUTOR_CHOICES)]
    if case == "2023":
        subjects = subjects.replace("Functions (Grade 11)", "Math Grade 11")
    if case == "scratch" and number % 12 == 1:
        subjects, gender = "  english ; Social Sciences  ", " female "
    email = _email("tutor", case, number)
    # Last and first applicants intentionally share a name, but not an email.
    name_number = 1 if number == count else number
    row = []
    for header in headers:
        key = (header or "").strip()
        value: Cell = None
        if key == "Timestamp_Tutor": value = _stamp(case, number)
        elif key in ("Email Address", "Primary Email Address", "Confirm Email"): value = email
        elif key == "Tutor First Name": value = "tutor"
        elif key == "Tutor Last Name": value = f"{name_number:03d}"
        elif key == "Year of Study": value = 1 + (number - 1) % 4
        elif key == "What program are you/were you in?": value = PROGRAMS[(number - 1) % len(PROGRAMS)]
        elif key == "Tutor Gender": value = gender
        elif key.startswith("Please list all the languages"): value = "French" if number % 4 == 0 else "None"
        elif key in ("Tutor Subjects", "Tutor Subjects2") or key.startswith("What subjects are you comfortable") or key.startswith("If the need arises, what subjects"): value = subjects
        elif key in ("Core Volunteer", "What position would you like to sign-up for?"): value = "Tutor"
        elif key.startswith("If yes, please describe your previous tutoring"):
            value = "Fictional example: helped classmates practise sample questions." if number % 3 == 0 else None
        elif key == "If yes, how many years and in what position(s)": value = "1 year as a tutor" if number % 3 == 0 else None
        elif key in ("Have you volunteered with us before?", "Do you have any prior tutoring experience?"): value = "Yes" if number % 3 == 0 else "No"
        elif key == "Are you willing to tutor two tutees?": value = "No"  # Unmapped: demo capacity stays one.
        elif key == "Are you willing to tutor if the need arises?": value = "Yes"
        elif key.startswith("Do you have a currently valid"): value = "No"
        elif key.startswith("I agree to receiving") or key == "Please carefully read and agree to these terms.": value = "Yes"
        elif key == "How did you hear about us?": value = "Example program notice"
        elif key == "Is there anything else you would like us to know?": value = "Fictional participant for the demonstration."
        # Addresses, phone numbers, institutional IDs and upload links stay blank.
        row.append(value)
    return row


def _tutee_row(headers: list[Cell], case: str, number: int, count: int) -> list[Cell]:
    primary, secondary, tertiary, preference = TUTEE_CHOICES[(number - 1) % len(TUTEE_CHOICES)]
    if case == "2023":
        primary = primary.replace("Functions (Grade 11)", "Grade 11 Math")
        secondary = secondary.replace("Functions (Grade 11)", "Grade 11 Math") if secondary else None
    if case == "scratch":
        if number % 16 == 1: primary = "Englsh"  # Explicitly approved demo typo.
        if number % 16 == 2: preference = " no preference "
    email, guardian = _email("tutee", case, number), _email("guardian", case, number)
    name_number, grade = (1 if number == count else number), 7 + (number - 1) % 6
    seen, row = {}, []
    for header in headers:
        key = (header or "").strip()
        seen[key] = seen.get(key, 0) + 1
        value: Cell = None
        if key == "Timestamp": value = _stamp(case, number)
        elif key in ("Email Address", "Confirm Email Address"): value = email if seen[key] == 1 else guardian
        elif key == "Email (Most frequently used)": value = email
        elif key == "Tutee 1 First Name": value = "tutee"
        elif key == "Tutee 1 Last Name": value = f"{name_number:03d}"
        elif key == "Gender": value = "Female" if number % 2 else "Male"
        elif key.startswith("Age by December"): value = grade + 5
        elif key == "First Name": value = "guardian"
        elif key == "Last Name": value = f"{number:03d}"
        elif key == "Relationship to Student": value = "Parent or guardian"
        elif key == "Name of School Student is Attending": value = f"Example Secondary School {(number - 1) % 4 + 1:02d}"
        elif key == "Current Grade of Student": value = grade
        elif key == "What system does your school use to teach?": value = "Semester"
        elif key == "What is your preferred language?": value = "English"
        elif key == "What other languages do you speak?": value = "French" if number % 4 == 0 else "None"
        elif key == "Tutee 1 Primary Subject": value = primary
        elif key == "Tutee 1 Secondary Subject": value = secondary
        elif key == "Tutee 1 Tertiary Subject": value = tertiary
        elif key == "Gender Preference": value = preference
        elif key == "Were you part of the Saturday Program in the past?": value = "Yes" if number % 5 == 0 else "No"
        elif key.startswith('If you answered "yes"'): value = 1 if number % 5 == 0 else None
        elif key.startswith("What is your reason for participating"): value = "Practise school subjects with a supportive tutor."
        elif key == "What are your short term academic/career goals?": value = GOALS[(number - 1) % len(GOALS)]
        elif key.startswith("What field of study are you interested"): value = PROGRAMS[(number - 1) % len(PROGRAMS)]
        elif key == "Is there any additional information you would like your tutor to know?": value = "I find worked examples and practice questions helpful."
        elif key == "Is there any additional information you would like the program co-directors to know?": value = "Fictional participant for the demonstration."
        elif key.startswith("Is there anything else you would like us to know?"): value = "No additional scheduling information in this fictional example."
        elif key == "Which information session would you like to attend?": value = "Example information session A" if number % 2 else "Example information session B"
        elif key == "How did you find out about the Saturday Program?": value = "Example school notice"
        elif key.startswith("I agree to receive") or key == "Submitted Form": value = "Yes"
        elif key == "Email found in sheet 2 (1 means yes)": value = 1 if number <= 35 else 0
        elif key == "Attendance": value = "Present" if number <= 67 else "Not recorded"
        # Blank headings and direct-contact fields deliberately remain blank.
        row.append(value)
    return row


def workbook_sheets() -> dict[str, dict[str, Rows]]:
    """Return all seven fictional sheets; no historical workbook is accessed."""
    result = {}
    for case, (tutors, tutees) in CASE_SIZES.items():
        prefix = "scratch_" if case == "scratch" else case
        for role, count, factory in (("tutor", tutors, _tutor_row), ("tutee", tutees, _tutee_row)):
            filename = f"{prefix}{role}.xlsx"
            headers = FORM_HEADERS[filename]["Sheet1"]
            result[filename] = {"Sheet1": [headers.copy()] + [factory(headers, case, n, count) for n in range(1, count + 1)]}
        if case == "scratch":
            result["scratch_tutee.xlsx"]["Sheet2"] = [FORM_HEADERS["scratch_tutee.xlsx"]["Sheet2"].copy()] + [
                [_email("tutee", case, n), 1, "Fictional attendance example"] for n in range(1, 68)
            ]
    return result


def datasets() -> dict[str, Rows]:
    """Return Sheet1 per filename for callers importing participant tables."""
    return {filename: sheets["Sheet1"] for filename, sheets in workbook_sheets().items()}

def _format_sheet(sheet, rows: Rows) -> None:
    for row in rows:
        sheet.append(row)
    sheet.freeze_panes = "D2"
    sheet.sheet_view.showGridLines = False
    sheet.auto_filter.ref = sheet.dimensions
    for column in range(1, len(rows[0]) + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 12 if rows[0][column - 1] is None else 30
    for row in sheet.iter_rows(min_row=1, max_row=len(rows), max_col=len(rows[0])):
        for cell in row:
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="20344D")
        cell.font = Font(name="Arial", size=10, color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 110
    for row_number in range(2, len(rows) + 1):
        sheet.row_dimensions[row_number].height = 48


def workbook_bytes(rows: Rows, *, extra_sheets: dict[str, Rows] | None = None) -> bytes:
    """Make a deterministic workbook with neutral authorship and fixed dates."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    workbook.properties.creator = "Saturday matching synthetic examples"
    workbook.properties.lastModifiedBy = "Saturday matching synthetic examples"
    workbook.properties.title = "Synthetic questionnaire example"
    workbook.properties.description = "Wholly invented participants; no historical rows."
    workbook.properties.created = FIXED_TIME
    workbook.properties.modified = FIXED_TIME
    _format_sheet(sheet, rows)
    for name, sheet_rows in (extra_sheets or {}).items():
        if name == "Sheet1":
            raise ValueError("extra_sheets cannot replace Sheet1")
        _format_sheet(workbook.create_sheet(name), sheet_rows)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    # ZIP timestamps and openpyxl's modified-at update otherwise vary on each run.
    output = BytesIO()
    with ZipFile(BytesIO(buffer.getvalue()), "r") as source, ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
        for filename in sorted(source.namelist()):
            payload = source.read(filename)
            if filename == "docProps/core.xml":
                payload = re.sub(
                    rb"(<dcterms:modified\b[^>]*>).*?(</dcterms:modified>)",
                    rb"\g<1>2000-01-01T00:00:00Z\g<2>", payload,
                )
            entry = ZipInfo(filename, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 0
            target.writestr(entry, payload)
    return output.getvalue()


def check_existing(directory: Path = DATA_DIR) -> int:
    failures = []
    for filename, expected_sheets in workbook_sheets().items():
        path = directory / filename
        if not path.is_file():
            failures.append(f"{filename}: missing")
            continue
        workbook = load_workbook(path, read_only=True, data_only=False)
        try:
            if workbook.sheetnames != list(expected_sheets):
                failures.append(f"{filename}: unexpected worksheets")
                continue
            for name, expected in expected_sheets.items():
                actual = [list(row) for row in workbook[name].iter_rows(values_only=True)]
                if actual != expected:
                    failures.append(f"{filename}/{name}: content differs from synthetic declaration")
            if workbook.properties.creator != "Saturday matching synthetic examples":
                failures.append(f"{filename}: nonstandard author metadata")
        finally:
            workbook.close()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Verified six synthetic workbooks: 264 tutor and 312 tutee responses, plus 67 auxiliary attendance rows.")
    for case, (tutors, tutees) in CASE_SIZES.items():
        print(f"  {case}: {tutors} tutors; {tutees} tutees.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Verify examples without writing.")
    action.add_argument("--json", action="store_true", help="Print all sheet declarations as JSON without writing.")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR, help="Folder to generate or check; existing files are never replaced.")
    args = parser.parse_args()
    if args.check:
        return check_existing(args.output_dir)
    if args.json:
        print(json.dumps(workbook_sheets(), ensure_ascii=False))
        return 0
    examples = workbook_sheets()
    if any((args.output_dir / name).exists() for name in examples):
        print("Refusing to overwrite existing examples. Use --check or --output-dir with a new folder.", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Build all bytes before creating a file; exclusive mode guards a racing writer.
    payloads = {name: workbook_bytes(sheets["Sheet1"], extra_sheets={k: v for k, v in sheets.items() if k != "Sheet1"}) for name, sheets in examples.items()}
    for filename, payload in payloads.items():
        with (args.output_dir / filename).open("xb") as target:
            target.write(payload)
    print("Created six synthetic workbooks: 264 tutor and 312 tutee responses, plus 67 auxiliary attendance rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
