# Knowledge Base

Bugs encountered and patterns learned while building this pipeline.
Each bug doc explains what failed, why, and how to prevent it next time.
`skill.md` is the cross-project reference — copy it into `~/.claude/python-pipeline-patterns.md`
when starting a similar project.

## Bug log

| File | Summary | Fixed in |
|---|---|---|
| [bug-001-python-command.md](bug-001-python-command.md) | `python` not found in node:20 container | Spec 02 |
| [bug-002-pep668-install.md](bug-002-pep668-install.md) | pip blocked by PEP 668 system-Python protection | Spec 02 |
| [bug-003-module-not-found.md](bug-003-module-not-found.md) | `ModuleNotFoundError: No module named 'pipeline'` — missing pytest PYTHONPATH config | Spec 02 |

## Skill reference

[skill.md](skill.md) — reusable patterns covering:

1. Dockerized Python environment (node:20 base)
2. pytest PYTHONPATH configuration
3. DuckDB: RETURNING with ON CONFLICT for insert detection
4. Logging isolation in pytest
5. Gmail API MIME walking pattern
6. Gmail API attachment filename lookup
7. RFC 2047 header decoding
8. Mocking: patch where the name is used, not where it is defined
9. Per-message error isolation in a fetch loop
