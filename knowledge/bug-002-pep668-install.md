# Bug 002 — `pip install` blocked by PEP 668 (system Python protection)

**Encountered:** Spec 02 execution, installing pytest and project dependencies.
**Environment:** Debian-based Docker container, system Python 3.11.

---

## What happened

```
$ pip3 install pytest
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, the Python installation on this
    system is managed by the OS package manager (apt). ...

note: If you believe this is a mistake, please contact your Python
installation or OS distribution provider. You can override this, at
the risk of breaking your Python installation or OS, by passing
--break-system-packages.
```

## Root cause

PEP 668 (implemented in Python 3.11+) prevents pip from installing into a
system-managed Python environment. Debian/Ubuntu mark their Python
installations as "externally managed" so pip refuses to modify them without
an explicit override.

This is a safety mechanism: apt and pip can conflict on which version of a
package "owns" a given location. The protection is correct in production.
In a single-purpose Docker container where pip IS the intended package
manager, it is an obstacle.

## Fix

Add `--break-system-packages` to every `pip3 install` call:

```bash
pip3 install pytest --break-system-packages
pip3 install -r requirements.txt --break-system-packages
```

## Why this is safe in this container

The container has no pip-managed packages outside the project's own
requirements. There is no apt-managed Python package that conflicts.
The container is ephemeral and single-purpose — there is no "system"
to protect.

## Better long-term fix: venv in Dockerfile

```dockerfile
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip
```

Then `pip install` inside the venv needs no flags and cannot affect the
system Python. Any subsequent `python` or `pytest` call uses the venv
automatically because of the PATH override.

Not done here because Claude Code runs with `--dangerously-skip-permissions`
and adding venv activation to the entrypoint adds friction. Acceptable
for Phase 1; revisit if the Docker image is rebuilt for Phase 2.

## Skill reference

See [skill.md §1](skill.md#1-dockerized-python-environment-node20-base).
