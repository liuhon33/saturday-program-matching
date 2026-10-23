# Questionnaire preparation and cleaning

The loader reads two local questionnaire exports: tutors and tutees. It writes
new prepared outputs and a cleaning audit without modifying either source file.
Google Drive credentials are not required and the application makes no network
calls. Download the files yourself and keep live data and run outputs private.

## Public examples and private deployment

The six Excel files in `data/` contain wholly invented people, not renamed
historical rows. The names follow `tutor 001` and `tutee 001`. No home address,
phone number, email, school, timestamp or questionnaire free text is included.
Renaming people alone would not reliably anonymize historical records, so the
public examples use independent invented assignments and preferences as well.
They do not represent historical program participation or matching quality.

Each pair has eight tutors and twelve tutees. Every workbook contains `Sheet1`:

| Pair | Purpose |
| --- | --- |
| `2024tutor.xlsx`, `2024tutee.xlsx` | Default demonstration, duplicate names with distinct IDs, and excess tutees |
| `2023tutor.xlsx`, `2023tutee.xlsx` | The same invented scenario with approved Grade 11 math label variants |
| `scratch_tutor.xlsx`, `scratch_tutee.xlsx` | The same invented scenario with whitespace, case differences and the explicitly approved `Englsh` typo |

The years preserve familiar filenames; they do not identify actual cohorts.
All six files are valid under the included profiles. The generator in
`tools/generate_demo_data.py` reads no historical inputs and refuses to overwrite
existing examples. `python tools/generate_demo_data.py --check` verifies their
contents. Metadata uses a neutral author and fixed timestamps.

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
demonstrate two people with the same name and different IDs. They are both kept.

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

Run these commands from `version_1` after installing its dependencies:

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
