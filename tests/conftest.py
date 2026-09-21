"""Shared fixtures.

The toolkit is a set of top-level scripts rather than an installed package,
so tests import them the same way the scripts import each other: by putting
the toolkit directory on sys.path.
"""

import shutil
import sys
from pathlib import Path

import pytest

TOOLKIT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLKIT_DIR))


@pytest.fixture(scope="session")
def toolkit_dir() -> Path:
    return TOOLKIT_DIR


@pytest.fixture(scope="session")
def chrome() -> str:
    """Path to Chrome, or skip the test.

    End-to-end tests need a real browser. Skipping rather than failing means
    `pytest` still does something useful on a machine without Chrome; CI
    always has one, so nothing important is silently skipped there.
    """
    import cv_optimiser
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    pytest.skip("no Chrome/Chromium found; end-to-end rendering tests need one")


def make_cv(entries: int = 2, bullets: int = 3) -> str:
    """A valid content file with a controllable amount of content.

    Used to produce CVs that deliberately overflow a page budget, which is
    the only way to exercise the font-shrinking descent and the
    doesn't-fit warning path.
    """
    head = (
        "---\n"
        "name: Test Person\n"
        "headline: Test Headline | Second Part\n"
        "email: test@example.com\n"
        "location: Bristol, UK\n"
        "---\n\n"
        "## Profile {prose}\n\n"
        "A short profile paragraph describing what this person does.\n\n"
        "## Core Skills {skills}\n\n"
        "Alpha · Beta · Gamma · Delta\n\n"
        "## Experience {entries}\n\n"
    )
    body = []
    for i in range(entries):
        body.append(
            f"### Role Number {i} — a short phrase about the job\n"
            f"org: Organisation {i}\n"
            f"dates: Jan 20{i:02d} – Dec 20{i:02d}\n"
            f"location: Bristol, UK\n\n"
        )
        for j in range(bullets):
            body.append(
                f"- Did a substantial piece of work numbered {i}.{j}, describing "
                f"the approach taken and the measurable outcome that followed "
                f"from it in enough words to occupy a full line or two.\n"
            )
        body.append("\n")
    return head + "".join(body)


@pytest.fixture
def cv_factory(tmp_path):
    """Write a generated CV into tmp_path and return its path."""
    def _make(entries: int = 2, bullets: int = 3, name: str = "cv.md") -> Path:
        path = tmp_path / name
        path.write_text(make_cv(entries, bullets), encoding="utf-8")
        return path
    return _make
