# Campus test set

56 phone photos of real items, taken around campus, each with:

- `description_A_lost_report`: what the owner would type when reporting it lost
- `description_B_finder_note`: what a finder would write in a logbook (keyword-baseline input)
- `description_vague`: a deliberately vague report ("a black watch"), the failure-case test
- `lookalike_pair`: two items that could be confused with each other share a code (P01, P02...)

Photos live in `eval/data/campus/` (gitignored), named exactly as in the `filename` column.

    uv run python eval/evaluate_campus.py

Writes `eval/results/campus/summary.json`, `per_item.csv` and `scores.npz`.


`Personal details (matric numbers, a name) were redacted from three descriptions (idcard_01, idcard_02, book_01) and photo links removed. Reported results were computed on the unredacted text; photos are available from the author on request.`