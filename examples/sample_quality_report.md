# Pipeline Data-Quality Report

| Metric | Value |
|---|---|
| Total records read | 50750 |
| Valid records (loaded) | 48473 |
| Rejected records | 2277 |
| Duplicate records removed | 467 |
| Invalid records (failed a rule) | 2289 |

## Issues detected by rule

| Rule | Count |
|---|---|
| missing_order_id | 0 |
| invalid_date | 375 |
| invalid_price | 103 |
| missing_price | 1558 |
| invalid_quantity | 253 |
| invalid_status | 0 |

## Missing values per column

| Column | Missing count |
|---|---|
| order_id | 0 |
| order_date | 0 |
| customer_id | 761 |
| product | 0 |
| category | 1015 |
| unit_price | 1558 |
| quantity | 0 |
| status | 0 |
