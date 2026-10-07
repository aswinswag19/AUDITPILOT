# AuditPilot backend

## Setup
    pip install -r requirements.txt
    cp .env.example .env      # then add your GROQ_API_KEY (optional; the rules planner works offline)

## Run
    python run.py             # from this folder, API on http://127.0.0.1:8000
    # or, from the folder that CONTAINS backend/:
    uvicorn backend.app.main:app

## Test (works from this folder or from the parent)
    pytest tests
    pytest backend/tests

Relative paths in `.env` (e.g. `DATA_DIR=./data`) are resolved against this folder, not the current directory.

## API
| Endpoint | Purpose |
|---|---|
| `POST /datasets/upload` | Upload a `.csv`. Refuses to replace an existing file unless `?overwrite=true`. |
| `POST /profile`, `POST /plan` | Profile a dataset / turn a question into a plan. Understands any quarter (`Q1`-`Q4`), a year, and `fiscal Q4`; refuses unknown entities and profit questions. |
| `POST /currency/check` | Which currencies in the plan's scope still need confirming, with the questions and answer options to show the user. `/plan` also returns this as `currency_confirmation`. |
| `POST /execute`, `POST /verify` | Run both engines. Compare/rank questions return one independently verified figure per entity. |
| `POST /trust` | Trust decision, contradiction check against the executive summary, unsupported-currency and conflicting-invoice risks. |
| `POST /impact` | What each cleaning rule did: raw total, duplicates, conflicts, refunds, excluded rows. Reconciles to the verified total. |
| `POST /sensitivity` | How far the answer moves if dates are MM/DD, "Q4" means fiscal Q4, or refunds are excluded. |
| `POST /proof` | Proof bundle. The generated script is run in a separate process and must reproduce the answer, or no proof is issued. |
| `POST /reports/generate`, `GET /reports/{id}/pdf` | PDF audit report. |

## Currency confirmation (asked before any figure is computed)
If the question's scope contains a currency other than the reporting currency (USD / EUR when reporting in INR), or a blank / unrecognised code, `/execute`, `/verify`, `/trust`, `/proof`, `/impact` and `/sensitivity` answer **409 `CURRENCY_CONFIRMATION_REQUIRED`** with the questions to ask:

1. **Confirm each currency** - "N rows are in EUR. Is that correct?" Options: keep it, reassign it to another currency (suggestions come from the rates table; common mis-spellings such as `RS` or `$` are recognised), or enter another 3-letter code. Blank currencies can be assigned or left unknown (`XXX`, excluded and listed).
2. **Choose the conversion basis** - `transaction_date` (the rate in force on each row's date, the accounting default) or `latest` (the present rate on file, applied to every row). Details per currency (first/latest rate, rows that have no rate on their date) are included to inform the choice.

Send the same request again with the answers in the policy:

    "policy": {"currency_map": {"EUR": "USD", "USD": "USD"}, "conversion_basis": "latest"}

`currency_map` maps *a code found in the data* to *the code it really is* (identity = "yes, correct"). Only currencies that are actually in scope are asked about, so an INR-only question needs no answers. All three calculations (Pandas Analyst, DuckDB Inspector and the standalone proof script) apply the map and the basis identically; the proof bundle and PDF record both, and `/sensitivity` shows how far the answer moves under the other basis.

## Plan pre-flight
Hand-built plans are checked before computing and rejected with **422 `INVALID_PLAN`** when a filter names an unknown entity, uses an operator other than `eq`, refers to a column that does not exist, or groups by anything but the entity column. (These used to be ignored silently and returned a "verified" figure for the wrong scope.)

## Policy options (request field `policy`)
* `unsupported_currency`: `block_and_list` (default) excludes rows with no exchange rate **and lists them**;
  `block_answer` refuses to answer at all if any such row is in scope.
* `conflicting_duplicate`: `flag_exclude_and_block_if_in_scope` (default) excludes the conflicting invoice and flags it;
  `block_answer` refuses to answer if a conflicting invoice is in scope.
* `refunds`: `include_as_negative` (default) or `exclude`.
* `date_format`: `DD/MM/YYYY` (default) or `MM/DD/YYYY`.

## Assumptions
* Fiscal year runs April-March (India): fiscal Q4 = January-March.
* A refund counts in the period of the *refund date*, for the entity of the order it refunds, converted at the rate on the refund date.
* If a question gives no year, the latest year present in the data is used.

## Regenerate data
    python data_gen/generate_data.py
    python data_gen/compute_ground_truth.py
