# repoready

Verify open-source onboarding instructions by actually running them.

`repoready` takes a repository and a commit, executes the install and test steps
that the project itself declares, and reports which steps really work - with the
evidence, not a guess.

## Status

Under active development. See `docs/superpowers/specs/` for the design.

## Requirements

- Python 3.10 or newer
- Docker (optional; without it `repoready` falls back to a local backend)

## Usage

```bash
python -m repoready doctor
python -m repoready check https://github.com/psf/requests --ref v2.32.0
```
