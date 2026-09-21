from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKAGE_MANAGER_PRECEDENCE = (
    ("poetry.lock", "poetry"),
    ("Pipfile", "pipenv"),
    ("environment.yml", "conda"),
    ("pyproject.toml", "pip"),
    ("requirements.txt", "pip"),
    ("setup.py", "pip"),
    ("setup.cfg", "pip"),
)

PYTHON_SIGNAL_EXTRAS = (
    ".python-version",
    "Makefile",
    "requirements-dev.txt",
    "tox.ini",
)

PYTHON_SIGNALS = (
    tuple(name for name, _ in PACKAGE_MANAGER_PRECEDENCE) + PYTHON_SIGNAL_EXTRAS
)

OTHER_LANGUAGE_SIGNALS = {
    "package.json": "node",
    "pom.xml": "java",
    "build.gradle": "java",
    "go.mod": "go",
    "Cargo.toml": "rust",
}


@dataclass(frozen=True)
class ProjectProfile:
    languages: tuple[str, ...]
    package_manager: str | None
    signals: tuple[str, ...]


def detect_project(root: Path) -> ProjectProfile:
    root = Path(root)
    signals: list[str] = []
    languages: list[str] = []

    python_signals = list(PYTHON_SIGNALS)
    for path in sorted(root.glob("requirements*.txt")):
        if path.is_file() and path.name not in python_signals:
            python_signals.append(path.name)

    for name in python_signals:
        if (root / name).is_file():
            signals.append(name)
    if signals:
        languages.append("python")

    for name, language in OTHER_LANGUAGE_SIGNALS.items():
        if (root / name).is_file():
            signals.append(name)
            if language not in languages:
                languages.append(language)

    package_manager: str | None = None
    for name, manager in PACKAGE_MANAGER_PRECEDENCE:
        if (root / name).is_file():
            package_manager = manager
            break
    if package_manager is None and any(
        (root / name).is_file() for name in python_signals if name.endswith(".txt")
    ):
        package_manager = "pip"

    return ProjectProfile(
        languages=tuple(languages),
        package_manager=package_manager,
        signals=tuple(signals),
    )
