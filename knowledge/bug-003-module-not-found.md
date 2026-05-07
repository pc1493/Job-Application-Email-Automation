# Bug 003 — `ModuleNotFoundError: No module named 'pipeline'`

**Encountered:** Spec 02 execution, first successful pytest invocation attempt.
**Environment:** pytest 9.0.3, Python 3.11, no setup.py / pyproject.toml.

---

## What happened

```
$ pytest tests/test_fetcher.py -v

ERROR collecting tests/test_fetcher.py
ImportError while importing test module '/workspace/tests/test_fetcher.py'.

tests/test_fetcher.py:8: in <module>
    from pipeline.db import get_connection, init_schema
E   ModuleNotFoundError: No module named 'pipeline'
```

## Root cause

pytest discovers and imports test files, but it runs from `/workspace` with
no mechanism to add `/workspace` to `sys.path`. The `pipeline/` directory
is a plain folder (no `setup.py`, no `pyproject.toml`, no `pip install -e .`),
so Python's import system has no way to find it unless the workspace root
is on `PYTHONPATH`.

Two workarounds exist:
1. Prefix every pytest call: `PYTHONPATH=/workspace pytest ...`
2. Tell pytest to add the root to `sys.path` automatically via config.

Option 1 works but is fragile — anyone who runs `pytest` bare gets the
same error. Option 2 is a one-time fix.

## Fix

Create `pytest.ini` at the project root:

```ini
[pytest]
pythonpath = .
```

The `pythonpath` key (pytest ≥ 7.0) adds the listed paths to `sys.path`
before any test collection. `.` means the directory containing `pytest.ini`,
which is `/workspace`. After this, `from pipeline.db import ...` resolves
correctly.

```
$ pytest tests/test_fetcher.py -v
configfile: pytest.ini
...
14 passed in 0.77s
```

## Why this wasn't caught earlier

`tests/test_schema.py` had the same import pattern and the same latent bug.
It was never run bare during spec 01 — either the developer ran with
`PYTHONPATH` set, or it was never verified in CI. The bug was invisible
until spec 02's test run.

## How to prevent in future projects

Add `pytest.ini` (or the `[tool.pytest.ini_options]` table in
`pyproject.toml`) at project scaffold time (spec 01 / project init), before
any test is written. This is a zero-cost change that prevents this class
of error entirely.

```ini
[pytest]
pythonpath = .
```

For projects with `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

## Skill reference

See [skill.md §2](skill.md#2-pytest-pythonpath-in-a-flat-package-project).
