import re
from pathlib import Path

from app import __version__
from app.version import SOFTWARE_RELEASE_DATE, SOFTWARE_VERSION


def test_software_version_is_semver_and_has_a_changelog_entry():
    assert re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", SOFTWARE_VERSION)
    assert __version__ == SOFTWARE_VERSION
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", SOFTWARE_RELEASE_DATE)
    changelog = (Path(__file__).parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{SOFTWARE_VERSION}] - {SOFTWARE_RELEASE_DATE}" in changelog
