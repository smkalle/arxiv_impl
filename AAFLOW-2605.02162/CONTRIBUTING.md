# Contributing

## Setup

```bash
python3 -m pip install -e .[dev]
```

## Test commands

- Targeted tests:

```bash
python3 -m pytest -q tests/test_cli.py
python3 -m pytest -q tests/test_integration.py
```

- Full validator chain:

```bash
bash scripts/validate_all_completed_iterations.sh
```

## Iteration workflow

Each iteration requires:

1. Code + tests
2. `RELEASE_NOTES_ITERATION_<N>.md`
3. `scripts/validate_iteration_<N>.sh`
4. Visible artifact(s) under `artifacts/iteration_<N>/`
5. UI visibility in `scripts/human_validation_ui.py`
6. Aggregate pass through `scripts/validate_all_completed_iterations.sh`

Refer to `AGENTS.md` for the authoritative iteration checklist.
