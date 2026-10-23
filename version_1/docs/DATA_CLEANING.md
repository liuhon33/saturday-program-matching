# Questionnaire preparation and cleaning

The loader reads two local questionnaire exports: tutors and tutees. It writes
new prepared outputs and a cleaning audit without modifying either source file.
Google Drive credentials are not required and the application makes no network
calls. Download the files yourself and keep live data and run outputs private.

## Use your own Google Forms exports

Complete the [quick-start setup](../README.md#try-the-example) first. Run the
commands below from `version_1`. Create a private input folder and a copy of the
settings for your questionnaire:

**Windows - PowerShell**

```powershell
New-Item -ItemType Directory -Force private_data
Copy-Item config/default.yaml private_data/current_schema.yaml
```

**Mac - Terminal**

```bash
mkdir -p private_data
cp config/default.yaml private_data/current_schema.yaml
```

Copy the tutor and student downloads into this folder as `tutors.xlsx` and
`tutees.xlsx`, or substitute your actual filenames in the commands. UTF-8 CSV
files are also supported. The `private_data` folder is excluded from Git; do not
replace the invented examples in `data/` with real responses.

Open `private_data/current_schema.yaml` in a text editor. Check the sheet names,
column headings and subject choices against your exports. The supplied settings
describe prepared older questionnaires; a fresh Google Forms export may use
different questions. A field's `aliases` list contains its accepted headings.
Ask someone comfortable with the settings file to help if needed.

Each input row must describe one person, with separate first-name and last-name
fields. If a family response contains several students, prepare one row per
student in a separate working copy and keep the original download.

Check and clean the inputs before matching:

**Windows**

```powershell
.\.venv\Scripts\python.exe run_matching.py clean --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml
```

**Mac**

```bash
./.venv/bin/python run_matching.py clean --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml
```

Open the results folder printed by the program:

| File | What to review |
| --- | --- |
| `row_status.csv` | Which source rows are valid, invalid or blank |
| `cleaning_audit.json` | Changes and problems; open in a text editor and look for `error` or `warning` |
| `cleaned_tutors.xlsx`, `cleaned_tutees.xlsx` | Readable copies of the valid, cleaned records |

If the result says `needs_review`, resolve the flagged entries using the guidance
below. A missing sheet or required column must be fixed in the settings before
row-level review files can be produced. Once the result says `validated`, rerun
the same command with `run` in place of `clean` to create matches. If you used
`--corrections`, include it in both commands.

Add `--include-contacts` to the matching command to include a separate local
name/email sheet. Each run creates a new folder inside `local_runs/`.

## Public examples and private deployment

The six Excel files in `data/` keep the older questionnaires' column order,
worksheet layouts and number of entries. Their participants and answers are
independently invented, not renamed historical rows. Names follow `tutor 001`
and `tutee 001`, email addresses use `example.invalid`, and narrative responses
are invented. Addresses, phone numbers, institutional IDs and upload links are
blank. Renaming people alone would not safely anonymize historical records.

| Pair | Tutors | Students | Matches | Waiting |
| --- | ---: | ---: | ---: | ---: |
| `2024tutor.xlsx`, `2024tutee.xlsx` | 80 | 71 | 60 | 11 |
| `2023tutor.xlsx`, `2023tutee.xlsx` | 93 | 99 | 75 | 24 |
| `scratch_tutor.xlsx`, `scratch_tutee.xlsx` | 91 | 142 | 79 | 63 |

These results use `config/synthetic.yaml`. All response rows pass validation,
and none of the matches violates the enabled requirements. The invented
scenarios include subject or gender-preference requests that no tutor can meet,
as well as demand for more tutoring places than are available. They demonstrate
the outputs and waiting lists; they are not a benchmark of matching quality.

Participant responses are in `Sheet1`. The scratch student workbook also keeps
the old `Sheet2` layout with 67 invented email entries; these are auxiliary
entries, not additional students. The examples include varied subject choices,
preferences and same-name participants. They demonstrate the program at the
size of the older files, but do not represent historical matching quality.

The years preserve familiar filenames. The generator in
`tools/generate_demo_data.py` reads no historical inputs.
`python tools/generate_demo_data.py --check` verifies the examples. Workbook
metadata uses a neutral author and fixed timestamps.

In deployment, put downloaded XLSX or UTF-8 CSV files under `private_data/` or
outside the project, and select the appropriate profile. Real participant names
stay in the local outputs so the coordinator can use the results. Names and
optional email contacts are not altered or replaced in the source exports.
`--include-contacts` adds a separate local name/email sheet; this is opt-in.
The application does not need home addresses or phone numbers for matching.

## What a profile controls

`config/default.yaml` maps the prepared historical-style headers. A fresh Google
Forms export may use longer question text, another sheet name, or a different
header row. Adjust a private copy of the profile rather than renaming source
columns or changing the matching code. `config/synthetic.yaml` identifies the
public demonstration schema explicitly.

Each role defines the worksheet name, header row and aliases for internal fields.
Tutor fields include names, optional ID, subjects, gender and optional capacity.
Tutee fields include names, optional ID, ranked subjects and gender preference.
The profile also lists approved subject choices, category aliases, no-subject
markers, no-preference markers, and matching policy settings.

Headers are normalized for Unicode, whitespace and case. A consumed field that
matches two columns is an error: the program does not guess which one to use.
Missing required columns or the configured sheet stop loading. Unmapped columns
are ignored and counted; they are not copied into the canonical matching model.
This is why the raw exports remain available privately if the coordinator needs
information beyond the fields used for matching.

## Automatic changes and their audit rules

The audit lists the role, source Excel row number, internal field, rule code and
severity. It omits the original response values. The original file remains the
reference for a coordinator investigating a particular row.

| Handling | Representative audit rule | Boundary |
| --- | --- | --- |
| Normalize Unicode and repeated/edge whitespace | `normalized_whitespace_or_unicode` | Does not infer missing meaning |
| Map approved subject names to internal IDs | `subject_to_canonical_id`, `subject_list_to_canonical_ids` | Case-insensitive exact approved choices |
| Map a known questionnaire variant | `approved_subject_alias` | For example, Grade 11 math labels map to `functions11` |
| Apply an explicitly approved spelling correction | `approved_typo_alias` | For example, `Englsh` maps to `english`; no automatic fuzzy correction |
| Remove a repeated subject within one tutor's list | `duplicate_subject_removed` | Does not remove participant rows |
| Convert an allowed blank/no-subject response | `blank_to_null`, `no_subject_marker_to_null` | Primary subject is still required |
| Normalize gender/preference | `gender_to_canonical_id`, `no_preference_to_null` | Only approved choices are accepted |
| Treat a missing preference as no requirement | `missing_preference_no_requirement` | Explicit default policy; set `normalization.missing_preference: error` if missing answers require review |
| Apply a coordinator's row correction | `explicit_hash_bound_correction` | Source hash, role, row and internal field must match |
| Derive a private ID when absent | `generated_private_identity_from_name_and_contact` or `generated_private_identity_from_name` | The digest is an identity convenience, not anonymization |
| Retain distinct people with the same display name | `same_name_distinct_ids_retained` | Distinct IDs remain separate; warning is reviewable |
| Reject colliding identities | `duplicate_identity_requires_review` | All rows in the collision group require review |
| Account for a blank row | `blank_row_recorded` | Recorded separately from valid and invalid rows |

Multi-select subjects accept comma, semicolon, pipe or newline delimiters. The
parser recognizes the longest complete approved label, so internal commas in
`Math Grades 7, 8, 9, 10` do not turn grade numbers into subjects. An unknown
remainder rejects the whole field instead of silently keeping a recognized
prefix. Numeric subject cells and formulas in consumed fields are errors.

Unknown answers can produce suggestions drawn from the approved public catalog.
A suggestion is never applied automatically. The program cannot reliably decide
that two different courses, a changed gender choice, or a free-text answer mean
the same thing.

## Duplicate submissions and duplicate names

Prefer a persistent, non-identifying `Tutor ID` or `Tutee ID`. The public samples
keep the older question columns, without adding an ID column. They demonstrate
people with the same display name and different invented email addresses, which
produce distinct internal identities so both people are kept.

When an ID is absent, a private deterministic identity uses the role, normalized
first/last names and email when available. Matching never removes someone merely
because their name equals another person's name. If the derived identity or
explicit ID appears twice, the entire group is flagged invalid. The coordinator
must decide whether these are duplicate submissions or distinct people. There is
no silent first-row/last-row wins rule and no automatic merge. Assign distinct
IDs to genuinely different people through reviewed corrections. For repeated
submissions, select the intended submission in a separately maintained private
input copy and document that decision; keep the downloaded original unchanged.

## Review, correct, and rerun

Run these commands from `version_1` after installing its dependencies. In the
examples below, replace `python` with `.\.venv\Scripts\python.exe` on Windows
or `./.venv/bin/python` on Mac to use the environment created in the quick start:

```text
python run_matching.py clean --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml
```

The new run directory contains `cleaning_audit.json`, `input_summary.json`,
`row_status.csv`, `corrections.template.csv`, `normalized_tutors.json`,
`normalized_tutees.json`, and the cleaned tutor/tutee workbooks. The cleaned
workbooks are review views with canonical values, not replacements for the raw
questionnaire exports. The run manifest records source/configuration/code hashes
and environment versions. The summary reports counts without participant names.

For a spelling variant that has one reviewed meaning everywhere, add a
`typo_aliases` entry under that subject in a private versioned profile. Do not
map genuinely different subjects together just to make validation pass.

For a correction that applies only to one submission, copy the empty corrections
template into `private_data/` and add a row containing these columns:

| Column | Meaning |
| --- | --- |
| `role` | `tutor` or `tutee` |
| `source_sha256` | Exact hash for that source file from `input_summary.json` |
| `row` | Excel row number including the header row, or equivalent CSV line record |
| `field` | Internal field such as `primary`, `subjects`, or `id` |
| `value` | Coordinator-approved replacement value |

For example, a synthetic tutee's `primary` can be explicitly corrected to
`English`. A profile-wide typo alias is more appropriate only if the spelling
always has that meaning. Values in a live corrections file can identify people;
keep that file private. The hash prevents accidentally applying row corrections
to a different or reordered download.

```text
python run_matching.py run --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml --corrections private_data/reviewed_corrections.csv
```

Use a new output directory for each run or accept the unique `local_runs/`
default. Existing outputs are never overwritten. `validate` and `clean` both
prepare review artifacts without matching. `run` blocks matching when invalid
rows remain. `--allow-partial` is an explicit coordinator choice to match valid
rows while retaining invalid rows in the ledger. Those rows are not part of the
matching denominator; compare input and matching summaries before claiming
everyone was handled.

## Review unmatched students

In `matches.xlsx`, open `Unmatched Tutees`. `no_eligible_tutor` means nobody met
the required conditions; `Candidate Rejections` explains subject or
gender-preference conflicts. `capacity_exhausted` means no suitable place was
left when that student was considered; it also covers a run with no tutors.

Use this list to review possible data mistakes, recruit suitable tutors or
confirm whether existing tutors can take more students. Unused tutor capacity
does not necessarily satisfy an unmatched student's requirements.

Also check `row_status.csv`: invalid records are separate from the unmatched
list. Every valid student appears in either `Matches` or `Unmatched Tutees`.
The default matching requires the first-choice subject and any stated
tutor-gender preference, with one student per tutor. Availability and grade
compatibility are not checked by default. See the [matching details](ALGORITHM.md)
for priorities, ties and optional checks.

## Annual questionnaire checklist

1. Keep the downloaded originals in private storage and copy the profile to a
   new year-specific name with a new `schema_version`.
2. Confirm sheet/header locations and map each consumed question to an internal
   field. Ambiguous mappings must be resolved before matching.
3. Review subject, gender and no-preference choices. Register approved aliases
   and spelling corrections with a short rationale in the private change record.
4. Run `clean`; investigate every error, identity collision and warning. Keep
   row-specific decisions in the hash-bound corrections file.
5. Confirm strict primary-subject and requested-gender requirements, capacity,
   and whether structured availability/grade data are complete enough to enable
   those checks. The default profile does not claim schedule/grade verification.
6. Run matching, reconcile valid/invalid/blank source rows, and review unmatched
   participants and unused capacity. Preserve the run manifest and audit locally.

Names, normalized records, IDs, corrections and match outputs can all be
sensitive even when there are no email addresses. Only the generated synthetic
examples belong in the public repository. Git ignore rules help prevent
accidental staging; they do not anonymize files or remove earlier Git history.
