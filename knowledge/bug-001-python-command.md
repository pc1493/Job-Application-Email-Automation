# Bug 001 — `python: command not found` in Docker container

**Encountered:** Spec 02 execution, first test run attempt.
**Environment:** node:20 Docker image with Python 3.11 installed via apt.

---

## What happened

```
$ python -m pytest tests/test_fetcher.py -v
/bin/bash: line 1: python: command not found
```

## Root cause

The Dockerfile installs Python as `python3.11` and creates a `python3`
alternative via `update-alternatives`. It does NOT create a `python`
symlink. The `node:20` base image has no Python at all — only the
explicitly installed `python3` is present.

```dockerfile
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
# No: update-alternatives ... python python3.11 ...
```

## Fix

Use `python3` everywhere:

```bash
python3 -m pytest tests/test_fetcher.py -v
python3 -m pipeline.fetcher
```

## How to prevent in future projects

- In CLAUDE.md or methodology notes: "This container has `python3`, not
  `python`. Use `python3` for all invocations."
- Alternatively, add to Dockerfile:
  ```dockerfile
  RUN ln -s /usr/bin/python3 /usr/bin/python
  ```
  This is a one-line fix if you control the image.

## Skill reference

See [skill.md §1](skill.md#1-dockerized-python-environment-node20-base).
