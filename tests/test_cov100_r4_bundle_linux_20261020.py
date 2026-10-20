"""Coverage for the post-resolution escape guard in run-bundle inspection."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from axiomize.runs import bundle


def test_bundle_member_escaping_after_resolution_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "escape.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("escape.txt", b"x")

    real_resolve = Path.resolve

    # Simulate a filesystem where a relative member without ".." resolves
    # outside the destination (a symlinked directory does this for real).
    def fake_resolve(self: Path, *args, **kwargs) -> Path:
        if self.name == "escape.txt":
            return Path(self.anchor) / "outside" / "escape.txt"
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(ValueError, match="escapes the extraction directory"):
        bundle.inspect_bundle_members(archive)
