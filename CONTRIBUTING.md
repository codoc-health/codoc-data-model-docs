# Contributing

The site is built with [MkDocs](https://www.mkdocs.org/) and published at
https://codoc-health.github.io/codoc-data-model-docs/ when changes are merged to `main`.

## Local setup

Requires Python 3.15 (see `.python-version`).

    python3.15 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    mkdocs serve    # live-reloading preview at http://127.0.0.1:8000

## Checks

Every pull request must pass:

* `python scripts/check_data_model.py` checks that the CSV files are consistent (no install needed).
* `mkdocs build --strict` checks that the site builds without warnings.

Merging to `main` deploys the site to GitHub Pages. A weekly job checks that external links still work.

## Conventions

* Each table has a page `docs/tables/<group>/<table>.md` that renders `docs/csv/.../<table>.csv`.
  Other CSVs on the same page list extension fields of that table (see `dwh_data`).
* Write column and table names in backticks (`` `patient_num` ``) and values in italics (`*true*`).
* Datatypes come from the list at the top of `scripts/check_data_model.py`. Add new types there.

## Project layout

    mkdocs.yml    # Site configuration and navigation.
    docs/
        index.md  # Home page.
        tables/   # One page per table.
        csv/      # Column definitions rendered on the table pages.
    scripts/      # Checks run in CI.
    generate/     # Helper that exports a table's columns from the database.
