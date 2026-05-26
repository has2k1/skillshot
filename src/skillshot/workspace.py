"""Build ephemeral workspaces that expose skills to the Claude Agent SDK."""

import json
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_DEFAULT_SETTINGS: dict[str, Any] = {
    "defaultMode": "dontAsk",
    "permissions": {"allow": [], "deny": []},
}


def build_workspace(
    skills: list[Path],
    extra_dirs: dict[str, Path] | None = None,
    prefix: str = "skillshot-",
) -> Path:
    """
    Create a temporary workspace with skills symlinked and settings.json written

    Parameters
    ----------
    skills
        Skill directories to expose. Each is symlinked into
        ``.claude/skills/<basename>`` and granted ``Skill(<basename>)``
        permission.
    extra_dirs
        Additional directories to symlink at the workspace root. Keys are
        link names, values are source paths.
    prefix
        Prefix for the temp directory name.

    Returns
    -------
    Path
        The workspace root.

    Raises
    ------
    ValueError
        If two skill paths share a basename.
    """
    names = [s.name for s in skills]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"Skill name collision: {dupes}")

    ws = Path(tempfile.mkdtemp(prefix=prefix))
    claude = ws / ".claude"
    claude.mkdir()

    allow = [f"Skill({s.name})" for s in skills]
    settings: dict[str, Any] = {
        **_DEFAULT_SETTINGS,
        "permissions": {"allow": allow, "deny": []},
    }
    (claude / "settings.json").write_text(json.dumps(settings, indent=2))

    if skills:
        (claude / "skills").mkdir()
        for s in skills:
            (claude / "skills" / s.name).symlink_to(s.resolve())

    for name, src in (extra_dirs or {}).items():
        (ws / name).symlink_to(src.resolve())

    return ws


@contextmanager
def workspace(
    skills: list[Path],
    extra_dirs: dict[str, Path] | None = None,
    cleanup: bool = True,
    prefix: str = "skillshot-",
) -> Generator[Path]:
    """
    Context-managed wrapper around :func:`build_workspace`

    Parameters
    ----------
    skills
        See :func:`build_workspace`.
    extra_dirs
        See :func:`build_workspace`.
    cleanup
        If True, recursively remove the workspace on exit.
    prefix
        Prefix for the temp directory name.

    Yields
    ------
    Path
        The workspace root.
    """
    ws = build_workspace(skills, extra_dirs, prefix=prefix)
    try:
        yield ws
    finally:
        if cleanup:
            shutil.rmtree(ws, ignore_errors=True)
