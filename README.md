# Saturday Program participant matching

Two self-contained versions preserve the original workflow and provide a maintained local application. Version 1 keeps the original urgency-first greedy tutee algorithm. Alternative optimizers and career-goal NLP are future work.

| Folder | Purpose | Shared in Git? |
| --- | --- | --- |
| `version_0/` | Original script and its environment guide | Code/docs only |
| `version_0/data/` | Six original workbooks, unchanged | **No: private local data** |
| `version_1/` | Validated greedy matcher, cleaning tools, tests and guides | Yes |
| `version_1/data/` | Six fully synthetic example workbooks | Yes |
| `version_1/local_runs/` | Local validation reports, corrected copies and matching results | **No: private** |
| `_private_archive/` | Old Git history, earlier review, legacy code, existing results and workspace clutter | **No: private** |

These are Git publication boundaries, not changes to Windows account permissions. Do not upload a zip of the entire working folder: it includes private data and old history. The public release helper creates an allowlisted archive from tracked files.

## Try Version 1

```powershell
cd version_1
python -m pip install -r requirements.txt
python -B run_matching.py run --tutors data/2024tutor.xlsx --tutees data/2024tutee.xlsx --config config/synthetic.yaml
python -B -m unittest discover -s tests -v
python -B tools/check_release.py
```

The demo has 8 tutors and 12 tutees. Every tutee is accounted for as matched or unmatched; same-name people with different IDs remain distinct. Default matches require a primary-subject match and any explicit tutor-gender preference. See [Version 1's guide](version_1/README.md) for private downloaded exports, corrections and output explanations.

## Sharing

The current Git repository starts with clean sharing history. The old `.git` directory is retained in `_private_archive/legacy_git/`, excluded from this repository. Do not add that history as a remote/branch or force-add private files.

The public repository is [liuhon33/saturday-program-matching](https://github.com/liuhon33/saturday-program-matching). Only the code, documentation and synthetic examples are shared. `version_1/tools/check_release.py` verifies tracked content and synthetic workbook declarations before sharing. A CI workflow repeats tests and release checks.

Version 0's data remain available to the owner locally. Other people can run Version 1's samples immediately and supply their own private Forms exports through command-line paths. No connected Google account or cloud upload is part of the program.
