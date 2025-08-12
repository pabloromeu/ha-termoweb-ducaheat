# AGENTS.md

## Development Guidelines
- Use Python 3.11 and type hints for all new code.

- For each commit or task, make the absolute MINIMAL SURGICAL changes and only directly related to the task at hand.
- Do not make changes to parts of the code that are unrelated to your current task
- Keep imports sorted using `ruff --select I --fix` or a similar tool.
- Run tests with `pytest` and make sure they pass before committing.
- If given a formatting task format with [Black](https://black.readthedocs.io/en/stable/) and lint with [Ruff](https://docs.astral.sh/ruff/).
- Do not make formatting changes unless explicitly asked.

## Pull Request Expectations
- Keep every PR focused on a single feature or test with minimal code changes as needed.
- Provide a brief summary of your changes and how they were tested.
- Include any relevant documentation updates when behavior changes.
