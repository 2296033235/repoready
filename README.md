# repoready:开源项目验证工具

Verify open-source onboarding instructions by actually running them.

`repoready` takes a repository and a commit, executes the install and test steps
that the project itself declares, and reports which steps really work - with the
evidence, not a guess.

## Status

Under active development. See `docs/superpowers/specs/` for the design.

## Requirements

- Python 3.10 or newer
- Docker (strongly recommended; local execution must be requested explicitly)

## Usage

```bash
python -m repoready doctor
python -m repoready check https://github.com/psf/requests --ref v2.32.0
python -m repoready check ./repo --backend local --allow-local-network
```

The local backend is explicitly opt-in, runs in a temporary checkout with a
scrubbed environment and independent virtualenv, and disables network access
unless `--allow-local-network` is passed. Prefer Docker for untrusted
repositories.
