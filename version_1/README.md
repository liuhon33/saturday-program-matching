# Version 1: local, auditable greedy matching

Version 1 retains the original urgency-first greedy algorithm and the original urgency and pair-score weights. It fixes name-based deletion and silent student truncation, separates questionnaire configuration from matching, and records normalization/corrections. Maximum-weight matching, other optimizers, and NLP for goals/career interests are deferred.

## Setup and synthetic demo

Use Python 3.10 or newer; the local tested environment is CPython 3.12.4. From this directory:

```powershell
python -m pip install -r requirements.txt
python -B run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
```

The six bundled XLSX files are generated from invented records, with names such as `tutee 001`. No historical row was copied or merely pseudonymized. Addresses, contact details, institutional identifiers, uploads and narrative answers are absent. Both tutors and tutees are synthetic. Each year/scratch pair has 8 tutor rows and 12 tutee rows, including distinct IDs with the same display name and excess demand. Scratch demonstrates an explicitly approved typo alias.

The command creates a new, uniquely named directory inside ignored `local_runs/`. For the 2024 demo, expect 8 matches and 4 explicitly unmatched tutees, with no configured hard-constraint violations. Each run is independently recorded; output-directory reuse is refused.

## Use your real Google Forms exports privately

1. Download the tutor and tutee responses from your own Google Drive/Sheets as XLSX or CSV. Keep them in a local private folder. The application has no network calls or Google credentials.
2. Copy `config/default.yaml` to a new versioned configuration and review its field aliases, worksheet/header location and subject choices against that year's actual questionnaire. This supplied profile maps the **prepared** 2023/2024 column names; a fresh raw form may have different question wording.
3. Validate before matching. Use the real local paths; no input file is modified.

```powershell
python -B run_matching.py validate --tutors "C:\private_exports\tutors.xlsx" --tutees "C:\private_exports\tutees.xlsx" --config config/default.yaml
```

4. Inspect the newly created run's `cleaning_audit.json`, `row_status.csv`, `input_summary.json`, and cleaned workbooks. Audit entries identify role, original Excel/CSV row, canonical field and rule, without recording submitted values. Unknown subjects offer approved-catalog suggestions for review, never guessed corrections.
5. Correct your configuration's explicit aliases or prepare a private corrections CSV. Run again into a new directory. Once validation is clean:

```powershell
python -B run_matching.py run --tutors "C:\private_exports\tutors.xlsx" --tutees "C:\private_exports\tutees.xlsx" --config config/default.yaml --include-contacts
```

Original names remain in private operational results. `--include-contacts` adds a separate local name/email contact sheet. Phone numbers, addresses, uploaded links and unrelated narratives are not propagated by the current output allowlist; they remain in your original private downloads. Public examples contain no phone number, so there is no risk of inventing a number belonging to a real person.

Git ignore rules keep `local_runs/` private, but cannot prevent you from manually publishing another folder. Treat real inputs, cleaned records, corrections, identities and operational outputs as private. Do not replace tracked sample files with real exports.

## Cleaning and correction utility

`clean` performs the same validation/normalization as `validate` and exports cleaned local records without matching. It does not rewrite the source workbook. Both commands return exit code 2 if any record requires review.

```powershell
python -B run_matching.py clean --tutors "C:\private_exports\tutors.xlsx" --tutees "C:\private_exports\tutees.xlsx" --corrections "C:\private_exports\corrections.csv"
```

Each run creates an empty `corrections.template.csv` with these columns:

| Column | Meaning |
| --- | --- |
| `role` | `tutor` or `tutee` |
| `source_sha256` | That role's full input-file hash from `input_summary.json` |
| `row` | Actual source row number, including the header row |
| `field` | Internal field, e.g. `id`, `primary`, `subjects` or `gender_preference` |
| `value` | Reviewed replacement value; CSV-quote values containing commas |

A correction applies only to the exact source hash and existing nonblank row. Stale, duplicate, malformed or unmapped corrections are rejected. Empty values deliberately clear optional fields; they are not placeholders to apply automatically. Corrections and raw input remain separate. Every applied correction produces an audit event and the run manifest records the correction file hash.

Normalizations are explicit: whitespace/Unicode normalization, reviewed header/subject aliases, approved typo aliases, missing optional subjects, canonical gender choices, and duplicate identity checks. Multiselect parsing recognizes complete subject labels, including labels containing commas. Unknown residual text blocks the record instead of partially accepting it. See [the cleaning guide](docs/DATA_CLEANING.md).

## Identity and accounting

- Prefer a persistent `Tutor ID` / `Tutee ID` in operational exports. Names are display labels, not the key for removal.
- When no ID is supplied, a deterministic private digest is derived from role, normalized full name and participant contact email when available. It is not a public anonymization method or a substitute for authoritative registration IDs.
- Same-name rows with distinct IDs are retained and audited. Repeated identities are all held for review; the program never guesses which submission to keep. If two same-name people lack differentiating contact/IDs, assign reviewed IDs via corrections.
- Every source row appears in `row_status.csv` as valid, invalid, or blank. Every valid tutee appears in a match or the unmatched list. Every tutor's used/remaining capacity is reconciled.
- By default, any invalid row blocks matching. `--allow-partial` explicitly opts into matching the valid subset, while invalid rows remain in the ledger and the manifest says `completed_with_invalid_rows`. A zero process exit in that explicit mode does not mean the excluded rows have been resolved.

## Rules and limitations

Default hard conditions are primary-subject compatibility, any stated tutor-gender preference, and tutor capacity (default 1). A zero score never substitutes for eligibility. Tutees are sorted by original rounded scarcity urgency, then stable ID. Tutors are chosen by original subject score, then stable ID. No randomness or global reassignment occurs. Exact approved canonical subject IDs replace substring matching, so corrected questionnaire labels can legitimately change matches.

Missing gender preference is explicitly configured as no preference in the supplied profiles and audited. Change `normalization.missing_preference` to `error` if staff must resolve blanks. New/unrecognized choices are rejected. The config also exposes compatibility modes for deliberate comparison; the production examples use strict rules.

Historical exports lack reliable structured tutor availability and subject-specific grade capabilities. Their checks are **disabled and reported as unevaluated**, not passed. If enabling grade/availability checks, supply the configured structured fields for both roles. The profile's `grade_values` defaults to bands 7–12 and can be extended after review; numeric grades and `Grade 9` spelling normalize to the same approved value. Slots are exact normalized `|`-separated labels. Subject-specific grade competence, recurring timetables and room allocation remain outside this model.

An explicit numeric capacity may exceed one, but that represents total tutoring places, not a scheduling guarantee. The questionnaire's willingness-to-tutor-two answer is not automatically converted into capacity. Staff must approve any capacity above one, particularly whether those places form a simultaneous group or separate sessions. [Algorithm details](docs/ALGORITHM.md) explain the retained heuristic and tradeoffs.

## Outputs

| File | Contents |
| --- | --- |
| `run_manifest.json` | Version, schema/config snapshot and hash, source hashes, correction hash, code hashes, dependency versions, status |
| `input_summary.json` | Source and record counts, schema ID, ignored-field count |
| `cleaning_audit.json` | Value-free change/error/warning events and catalog suggestions |
| `row_status.csv` | Every source row's review/accounting status |
| `normalized_tutors.json`, `normalized_tutees.json` | Typed canonical records, with real display names for private runs |
| `cleaned_tutors.xlsx`, `cleaned_tutees.xlsx` | Minimal human-readable normalized records; unrelated personal fields removed |
| `matches.xlsx` | Matches, unmatched tutees with reasons, tutor capacity, optional separate private contacts |
| `matching_details.json` | IDs, score components, compatibility results, unmatched reasons and aggregate checks |
| `summary.json` | Matching/validation counts, rule totals and quality checks |

Excel output writes user strings as literal text to avoid treating a name or other submitted value as a formula. Output folders are exclusive-create. A failed run is labeled failed/needs-review and is not a completed match publication.

## Verify and share

```powershell
python -B -m unittest discover -s tests -v
python -B tools/generate_demo_data.py --check
python -B tools/check_release.py
```

The synthetic generator has no input-data-reading path and refuses to overwrite existing examples. The release checker verifies complete workbook bytes against the reviewed `tools/sample_hashes.json` manifest, independently checks the synthetic rows and neutral metadata, and rejects private/unexpected tracked files. Changing the sample hashes requires reviewing the generator and data declarations together; do not update hashes to approve a real export. Run the checker before pushing, especially after handling real data. GitHub CI runs the same tests/checks. No live Drive authorization or original private data is required for any test.

The application is self-contained in this folder: code, configuration, dependencies, examples and tests do not import Version 0 or the private archive. Future work can compare other algorithms or structured/NLP career compatibility after data governance and scoring priorities are defined.
