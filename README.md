# SurakshaSetu Claims Console (Group 9, Project 8)

A small internal tool built in Python on top of the same SQL view the notebook and
the workbook use. It shows the Monday review (volumes, document gaps, time, the review
queue), lets a manager move the routing cut-off live, approve document requests with a
named sign-off, compare SurakshaSetu with public industry figures, and switch to the
external view that a policyholder or the regulator would see.

## Run it (two commands)

Windows: double-click `run_console.bat`
Mac or Linux: `./run_console.sh`

Or by hand:

    pip install -r requirements.txt
    streamlit run app.py

A browser tab opens at http://localhost:8501. Close the black command window to stop it.

## Data

By default the console reads `data/claims.csv`, which is an export of `dbo.vw_ClaimMaster`
(900 claims, same control totals: 900 / Rs 24,30,00,973.88 / 863 / 37 / 105 / 275).

To read live from SQL Server instead, set an environment variable before starting:

    set SQL_CONN=DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost;DATABASE=SurakshaSetu;Trusted_Connection=yes;

and `pip install pyodbc sqlalchemy`. If the connection fails the console falls back to
the CSV and says so in the sidebar, so the demo cannot break.

## Files

    app.py                  the console
    data/claims.csv         one row per claim (the SQL view)
    data/human_reviews.csv  180 human review records
    data/workflow_tests.csv 24 workflow test cases
    data/benchmarks.csv     public industry and regulator figures with sources (editable in the app)
    data/approvals_log.csv  created when the first request is approved in the app

## What is live

- Gate 2 slider (sidebar): every lane, chart, queue and the what-if page recompute.
- Approve and send (Review queue tab): logs approver, time and claim; the awaiting count drops.
- Benchmark table: edit a figure or add a row, click Save.
- Filters: region, product, risk tier.

## Rules the console keeps

- Claim amounts are reported amounts, not payouts. No savings figures anywhere.
- Time measures use closed claims only; open claims are shown as ageing.
- The score uses intake fields only (evidence on file, share of limit, amount).
  Status, ResolutionDays and InvestigationReferral are never inputs.
- A referral is a review step, not a finding. Nothing is sent without a named approval.
