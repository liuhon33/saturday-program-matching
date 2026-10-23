# Saturday Program Matching

This project helps Saturday Program coordinators pair students (tutees) with tutors using their questionnaire responses. It reads two spreadsheets, checks the data, and produces an Excel workbook of matches and students who still need a tutor.

## How it works

- Checks names, subjects and preferences, and flags entries that need review.
- Matches students one at a time using a priority score based on tutor supply and stated gender preferences. Tutors must cover the student's first-choice subject and meet any stated tutor-gender preference; additional subject matches help choose between eligible tutors.
- Keeps people with the same name separate when they have distinct IDs, and reports every valid student as matched or unmatched.

The default is one student per tutor. Availability and grade compatibility still need coordinator review unless those checks have been configured.

## Try it

With Python 3.12 installed, select **Code > Download ZIP** on this GitHub page and extract the downloaded folder. Open a terminal in that folder and run these commands one at a time. The second command installs the packages the program needs.

```powershell
cd version_1
python -m pip install -r requirements.txt
python run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
```

These example spreadsheets contain invented participants. The demo produces 8 matches and 4 unmatched students. Open `matches.xlsx` in the output folder printed by the program, inside `version_1/local_runs/`.

## Use your own responses

Download the tutor and tutee response spreadsheets, check and clean them, then run matching. Your original files stay unchanged, and processing takes place on your computer.

Follow the [Version 1 guide](version_1/README.md) for the commands, duplicate-name handling and unmatched-student review. Keep real participant files and results private; the bundled `data/` folder is for examples.
