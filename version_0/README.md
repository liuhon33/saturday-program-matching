# Version 0: preserved original

`2024dataframe.py` is the original working-tree script, preserved byte-for-byte. The six original Excel files are kept unchanged in local `data/`. That folder is deliberately excluded from Git and GitHub. A fresh Git clone therefore contains the runnable original code and dependencies but does not include private participant data.

The script is preserved for reference, including known behavior: name-based tutor removal, prefix truncation of tutees, zero-score fallback assignments, and fixed output filenames. It is not the recommended operational entry point. Use Version 1 for the reviewed workflow.

Use Python 3.12 with `python -m pip install -r requirements.txt`. If you need to reproduce an original run, first create a **new private run directory**, then run from that directory with absolute paths to this script and the tutor/tutee files. The script writes `Master_dataframe.xlsx` and `un_matched_tutor.xlsx` in its working directory and can overwrite previous results. It never requires Google login; inputs are downloaded Excel files.

Local original inputs:

- `data/2023tutor.xlsx` and `data/2023tutee.xlsx`
- `data/2024tutor.xlsx` and `data/2024tutee.xlsx`
- `data/scratch_tutor.xlsx` and `data/scratch_tutee.xlsx`

The 2023 and 2024 pairs completed during the earlier review; scratch failed because duplicate tutor names exhausted the pool. Do not treat successful execution as proof every pair is compatible.

No source or input cleanup was applied to this version. Its original file hashes and the old repository history are preserved privately outside this version's public Git contents.
