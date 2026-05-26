import json
import shutil
from pathlib import Path

import pytest

from skillshot.workspace import build_workspace, workspace


@pytest.fixture
def fake_skills(tmp_path: Path) -> list[Path]:
    a = tmp_path / "alpha"
    a.mkdir()
    (a / "SKILL.md").write_text("# alpha")
    b = tmp_path / "beta"
    b.mkdir()
    (b / "SKILL.md").write_text("# beta")
    return [a, b]


def test_build_workspace_creates_settings_and_symlinks(fake_skills):
    ws = build_workspace(fake_skills)
    try:
        settings = json.loads((ws / ".claude" / "settings.json").read_text())
        assert settings["defaultMode"] == "dontAsk"
        assert set(settings["permissions"]["allow"]) == {
            "Skill(alpha)",
            "Skill(beta)",
        }

        assert (ws / ".claude" / "skills" / "alpha").is_symlink()
        assert (
            ws / ".claude" / "skills" / "alpha" / "SKILL.md"
        ).read_text() == "# alpha"
        assert (ws / ".claude" / "skills" / "beta").is_symlink()
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_build_workspace_no_skills():
    ws = build_workspace([])
    try:
        settings = json.loads((ws / ".claude" / "settings.json").read_text())
        assert settings["permissions"]["allow"] == []
        assert not (ws / ".claude" / "skills").exists()
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_build_workspace_extra_dirs(tmp_path: Path, fake_skills):
    data = tmp_path / "datasets"
    data.mkdir()
    (data / "mtcars.csv").write_text("col\n1\n")

    ws = build_workspace(fake_skills, extra_dirs={"data": data})
    try:
        assert (ws / "data").is_symlink()
        assert (ws / "data" / "mtcars.csv").read_text().startswith("col")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_build_workspace_raises_on_collision(tmp_path: Path):
    a1 = tmp_path / "one" / "alpha"
    a1.mkdir(parents=True)
    a2 = tmp_path / "two" / "alpha"
    a2.mkdir(parents=True)
    with pytest.raises(ValueError, match="alpha"):
        build_workspace([a1, a2])


def test_workspace_contextmanager_cleans_up(fake_skills):
    with workspace(fake_skills) as ws:
        assert ws.exists()
        captured = ws
    assert not captured.exists()


def test_workspace_contextmanager_no_cleanup(fake_skills):
    with workspace(fake_skills, cleanup=False) as ws:
        captured = ws
    assert captured.exists()
    shutil.rmtree(captured, ignore_errors=True)
