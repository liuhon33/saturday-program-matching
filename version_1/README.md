# Match tutors and students

Version 1 helps Saturday Program coordinators turn two questionnaire spreadsheets into tutor-student pairs. It matches students by their requested subjects and tutor-gender preferences, and lists everyone still waiting for a tutor.

## Try the example

1. Install **Python 3.12** from [python.org](https://www.python.org/downloads/). On Windows, select **Add Python to PATH** during installation.
2. On the project's GitHub page, select **Code > Download ZIP**, then extract it.
3. Open PowerShell (Windows) or Terminal (Mac) in the extracted project folder. Copy the commands for your computer below, one line at a time.

The first three commands prepare the program; the last runs it with invented participants. You only need to do the setup once.

**Windows - PowerShell**

```powershell
cd version_1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
```

**Mac - Terminal**

```bash
cd version_1
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
```

Already inside `version_1`? Skip `cd version_1`. To run another example later, use just the last command from that folder.

## See the results

The 2024 example has **80 tutors and 71 students**. It produces **60 matches**, with **11 students still waiting**.

Open **`matches.xlsx`** in the results folder printed by the program, inside `local_runs/`.

- **Matches:** the suggested tutor-student pairs.
- **Unmatched Tutees:** students still waiting, with reasons.
- **Tutor Capacity:** the number of places used and still available.

By default, each tutor takes one student. A tutor must teach the student's first-choice subject and meet any stated tutor-gender preference. The program assigns students in priority order; it does not guarantee the largest possible number of matches. Check schedules and grade suitability before confirming pairs.

## Use your own spreadsheets

Download your tutor and student responses from Google Forms as Excel files. Follow the [supplementary guide](docs/DATA_CLEANING.md#use-your-own-google-forms-exports) to prepare them and run matching. It also explains cleaning, spelling variants, duplicate names and entries needing review.

Processing happens on your computer, and your original files stay unchanged. Keep real participant files and results private. The bundled examples are invented.
