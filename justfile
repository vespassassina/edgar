set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# ruff format + ruff check + mypy --strict + offline tests. Run before every commit.
check:
    uv run ruff format --check
    uv run ruff check
    uv run mypy
    uv run pytest -q

# The offline suite: what CI runs on every PR.
test *args:
    uv run pytest {{args}}

# Branch coverage report.
cov:
    uv run pytest -q --cov --cov-report=term-missing

# Format and apply safe lint fixes.
fmt:
    uv run ruff format
    uv run ruff check --fix

# Size against the tier budget [NFR-4].
loc:
    uv run python tests/support/budget.py
