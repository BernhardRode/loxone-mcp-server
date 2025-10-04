Kiro Steering Document – What NOT To Do (Anti-Patterns & Guardrails)
Philosophy

The goal is to maximize velocity and maintainability by avoiding unnecessary complexity, duplicated tooling, and legacy patterns. Every artifact in the repo should have a clear purpose, be actively maintained, and reduce—not increase—cognitive load.

Golden Rule

“If it doesn’t serve tests, readability, or deployment — don’t build it.”

Do NOT
🚫 Extra Scripts & Tool Wrappers

No ad-hoc shell/Python scripts for running tests, linting, or formatting.

Use native pytest, mypy, ruff, black directly, or via pyproject.toml.

CI/CD pipelines should call tools directly, not wrapper scripts.

No Makefiles or custom runners to abstract what modern tooling already provides.

Example of forbidden pattern:

test:
    pytest --cov
lint:
    black . && flake8


✅ Instead: configure everything in pyproject.toml and run pytest, ruff, etc.

🚫 Reinventing Build/Dependency Management

Do not create bespoke setup.py or requirements.txt for dependencies.

✅ Use pyproject.toml (PEP 621) with poetry or uv for lockfiles.

No manual virtualenv management.

✅ Use uv pip sync or poetry install.

🚫 Duplicated Configs

Avoid multiple sources of truth (e.g., flake8.ini + .pylintrc + setup.cfg).

✅ Centralize configuration in pyproject.toml.

No .env.example drift — env var schemas belong in documentation & CI, not scattered configs.

🚫 Legacy Testing Practices

No unittest.TestCase boilerplate unless necessary for compatibility.

✅ Use pytest + fixtures.

No giant "integration.py" scripts for manual testing.

✅ Write reproducible integration tests in pytest with async fixtures.

🚫 Over-Engineering CI/CD

No multi-stage YAML gymnastics when GitHub Actions/CI matrix can handle it simply.

No manually maintained bash scripts to bootstrap jobs.

✅ Write CI in declarative steps calling native tools (pytest, mypy, ruff).

🚫 “Helper Abstractions” That Obscure Logic

No meta-wrappers around asyncio, sockets, or uvloop that hide core behavior.

No premature abstractions for "maybe we’ll need it later."

✅ Keep networking code transparent, testable, and close to the metal.

Principles Behind the Guardrails

Clarity > Cleverness: Everyone should understand how to run, test, and deploy with a single glance.

One Source of Truth: All configs live in pyproject.toml.

Modern > Legacy: Prefer PEP-compliant, modern Python practices.

Consistency > Flexibility: One way to run things is better than many.

Explicitly Allowed Patterns

pyproject.toml for: deps, tooling config, black/ruff/mypy/pytest settings.

Direct CLI usage for dev workflows:

pytest
mypy src/
ruff check .
black .


CI/CD enforces the same commands — no wrappers.

Optional: pre-commit hooks to enforce checks locally.

Success Criteria

Any dev (new hire, contractor, AI agent) can run tests/lint with one command.

Repo has zero extra Makefiles, scripts, or duplicate configs.

All tooling defined in pyproject.toml only.

CI/CD pipeline directly mirrors dev workflow (no “special” hidden commands).

Simplicity and transparency are preserved long-term.

👉 Would you like me to write this as a “developer covenant” (like a cultural statement: “we don’t do X in this codebase”) or keep it strictly technical guardrails like above?