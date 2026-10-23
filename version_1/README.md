# Version 1: match tutors and students

Use two questionnaire spreadsheets to create tutor-student matches. The program checks and cleans the data, keeps a record of changes, and lists students who could not be matched. It runs on your computer and leaves your input files unchanged.

## 1. Set up

Use Python 3.12. Open a terminal in the downloaded project folder and run:

```powershell
cd version_1
python -m pip install -r requirements.txt
```

Run all remaining commands from this `version_1` folder. To try the invented sample data first:

```powershell
python run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
```

Expect 8 matches and 4 unmatched students. The program prints the location of a new results folder inside `local_runs/`.

## 2. Prepare your Google Forms exports

Download the tutor and tutee response spreadsheets as Excel (`.xlsx`) or UTF-8 CSV files. You do not need to connect a Google account to this application.

For your first setup, create a local folder and copy the settings file:

```powershell
New-Item -ItemType Directory -Force private_data
Copy-Item config/default.yaml private_data/current_schema.yaml
```

Save your downloads there as `tutors.xlsx` and `tutees.xlsx`. Use your actual filenames in the commands if they differ. Keep real data in `private_data/`, which is excluded from Git, rather than replacing the examples in `data/`.

Open `private_data/current_schema.yaml` in a text editor. This file tells the program which spreadsheet questions to read. Check the worksheet names, column headings and subject choices against your exports. The supplied settings describe prepared older questionnaires, so a fresh Forms export may need different headings. An `aliases` list contains the headings accepted for that field.

Each input row must represent one person, with separate first-name and last-name fields. If a family response contains several students, prepare one row per student in a separate working copy first. Keep the original download.

## 3. Clean and check the data

```powershell
python run_matching.py clean --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml
```

The program tidies spacing and recognizes approved subject labels and spelling variants. It flags unfamiliar answers for review instead of guessing. `validate` can be used in place of `clean`; both check the inputs and produce review files without matching.

Open the new output folder printed in the terminal:

| File | What to review |
| --- | --- |
| `row_status.csv` | Which tutor and student rows are valid, invalid or blank |
| `cleaning_audit.json` | What changed and what needs attention; open it in a text editor and look for `error` or `warning` |
| `cleaned_tutors.xlsx`, `cleaned_tutees.xlsx` | Readable copies of the valid, cleaned records |

If the result says `needs_review`, resolve the flagged entries and run again. A missing worksheet or required column must be fixed in your settings before row-level review files can be produced.

**Correcting mistakes:** add an approved spelling variant to your private settings if it should apply to everyone. For one person's answer, copy the generated `corrections.template.csv` to `private_data/corrections.csv` and fill in the participant type (`tutor` or `tutee`), source-file identifier (`sha256` from `input_summary.json`), original spreadsheet row, field and replacement value. For example, use field `primary` and value `English` for a reviewed subject correction. The [cleaning guide](docs/DATA_CLEANING.md#review-correct-and-rerun) explains the columns.

Rerun cleaning with `--corrections private_data/corrections.csv` added to the command. Use that same option when matching. Corrections apply to the exact download you reviewed; recheck them after changing or downloading the inputs again. The cleaned workbooks are review copies, not the input format to use for the next run.

## 4. Handle duplicate names

- **Different people with the same name:** give each person a distinct `Tutor ID` or `Tutee ID`, using the corrections file's `id` field if needed. Both people are kept.
- **Repeated submission by one person:** decide which submission to use in a separate working copy, record that decision privately, and keep the original download. Do not assign different IDs just to make duplicate submissions pass.
- **No IDs supplied:** the program uses name and email, when available, to distinguish people. If identities collide, all affected rows are held for review; none is silently selected or merged.

Check the source rows shown in the audit before deciding whether two entries are the same person.

## 5. Run matching

Once cleaning reports `validated`, run:

```powershell
python run_matching.py run --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml
```

If you used a corrections file, run this version instead:

```powershell
python run_matching.py run --tutors private_data/tutors.xlsx --tutees private_data/tutees.xlsx --config private_data/current_schema.yaml --corrections private_data/corrections.csv
```

Add `--include-contacts` if you want a separate name/email sheet in the results. Each run creates a new folder in `local_runs/`, so earlier results stay available.

Matching normally stops if any input row is invalid. The optional `--allow-partial` flag matches only valid records; use it only deliberately, and review the invalid rows separately.

## 6. Review matches and unmatched students

Open `matches.xlsx` in the latest results folder:

| Sheet | What it shows |
| --- | --- |
| `Matches` | Each assigned student and tutor |
| `Unmatched Tutees` | Students without a match, with reasons |
| `Tutor Capacity` | Used and remaining tutoring places |

In `Unmatched Tutees`, `no_eligible_tutor` means nobody met the required conditions. Check `Candidate Rejections` for subject or gender-preference conflicts. `capacity_exhausted` means no suitable place was left when that student was considered; it also covers a run with no tutors.

Use the list to plan follow-up: review possible data mistakes, recruit suitable tutors, or confirm whether existing tutors can take more students. Unused capacity alone does not mean a tutor meets that student's requirements.

Also check `row_status.csv`: invalid records are separate from the unmatched list. Every valid student should appear in either `Matches` or `Unmatched Tutees`.

By default, matches require the first-choice subject and any stated tutor-gender preference, with one student per tutor. The program uses the original greedy approach: it assigns students in priority order without revisiting earlier pairs, so another arrangement may fit more students. Availability and grade compatibility are not checked by default; review them before confirming assignments. See [matching details](docs/ALGORITHM.md) if you need the full rules.

Keep your real downloads, corrections and results private. They can contain participant names even when contact details are omitted.
