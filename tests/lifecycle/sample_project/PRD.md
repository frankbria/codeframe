# CSV Statistics Tool

## Overview

A command-line Python script that reads a CSV file and prints summary statistics.
This is a self-contained tool with no external dependencies beyond Python stdlib.

## Requirements

### Script: `csv_stats.py`

**Usage:**
```
python csv_stats.py <path/to/file.csv>
```

**Output format (exact):**
```
Rows: 42
Columns: name, age, score, city
age:
  min: 18.00
  max: 65.00
  mean: 34.21
score:
  min: 55.00
  max: 99.00
  mean: 78.45
```

Rules:
- List all column names on the `Columns:` line, comma-separated
- For each **numeric** column, print its name followed by min/max/mean (2 decimal places)
- Skip non-numeric columns (no output for them beyond listing in Columns)
- Skip blank/missing values when computing stats
- Non-numeric columns are silently skipped in the stats section

**Error handling:**
- File not found → print `Error: file not found: <path>` to stderr, exit code 1
- Not a valid CSV (unparseable) → print `Error: not a valid CSV file` to stderr, exit code 1
- Empty file (no rows after header) → print `Rows: 0` and column names, skip stats

### Test file: `test_csv_stats.py`

Must include at least 4 pytest tests:
1. Happy path: numeric columns produce correct min/max/mean output
2. Mixed columns: non-numeric columns are skipped in stats
3. Missing values: blanks are excluded from calculations
4. File not found: exits with code 1 and correct error message

### Code quality
- Must pass `ruff check .` with zero errors
- No third-party imports (stdlib only: csv, sys, pathlib, statistics, etc.)
