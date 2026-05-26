# skillshot

One-shot [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
runs in ephemeral workspaces, with skills exposed as `.claude/skills/<name>` and
auto-granted `Skill(<name>)` permission.

Useful for evals, fixtures, and notebook experiments where you want a fresh
working directory per run and a structured result object instead of streaming
SDK messages yourself.

## Install

```bash
uv add skillshot
# or
uv pip install skillshot
```

Requires Python 3.11+.

## Quick start

```python
from pathlib import Path
from skillshot import run_sync

r = run_sync(
    "write hello.py that prints hi",
    skills=[Path("~/.claude/skills/say-hello").expanduser()],
    cleanup=False,
)
print(r.workspace, r.is_error, r.num_turns, r.total_cost_usd)
```

Inside an `async` context use `run` directly:

```python
from skillshot import run

result = await run("write hello.py that prints hi", skills=[...])
```

## What a run produces

`run` / `run_sync` return a `RunResult` with:

| Attribute / method                        | Purpose                                             |
|-------------------------------------------|-----------------------------------------------------|
| `workspace`                               | Path to the temp workspace, or `None` if cleaned up |
| `assistant_messages`                      | Raw `AssistantMessage` list from the SDK            |
| `result_message`                          | Final `ResultMessage` (turns, cost, usage)          |
| `stderr`                                  | SDK stderr + captured `claude_agent_sdk` logs       |
| `error`                                   | Set if the SDK raised; otherwise `None`             |
| `is_error`, `num_turns`, `total_cost_usd` | Convenience properties                              |
| `assistant_text()`                        | Concatenated `TextBlock` text                       |
| `code_blocks(language=...)`               | Fenced code blocks from assistant text              |
| `extract_last_code_block(language=...)`   | The last such block, or `None`                      |
| `tool_calls(name=...)`                    | `ToolUseBlock`s, optionally filtered by name        |

## How the workspace is built

`workspace(skills, extra_dirs, cleanup=True)` is a context manager that:

1. Creates `tempfile.mkdtemp(prefix="skillshot-")`.
2. Symlinks each skill into `.claude/skills/<basename>` (raises `ValueError`
   on name collisions).
3. Symlinks any `extra_dirs` (`{link_name: source_path}`) at the workspace root.
4. Writes `.claude/settings.json` with `defaultMode: dontAsk` and an `allow`
   list containing `Skill(<basename>)` for every skill.
5. On exit, removes the workspace unless `cleanup=False`.

`build_workspace` is the same without the context-manager / cleanup behavior.

## `run` parameters

| Name              | Default                             | Notes                                         |
|-------------------|-------------------------------------|-----------------------------------------------|
| `prompt`          | —                                   | User prompt                                   |
| `skills`          | `None`                              | Skill directories to expose                   |
| `extra_dirs`      | `None`                              | `{name: path}` symlinks at the workspace root |
| `tools`           | `["Read", "Write", "Glob", "Grep"]` | Tools the agent may use                       |
| `max_turns`       | `10`                                |                                               |
| `model`           | `None`                              | SDK default if `None`                         |
| `permission_mode` | `"bypassPermissions"`               | Any SDK `PermissionMode` literal              |
| `env`             | `None`                              | Merged over `MPLBACKEND=Agg`, `CLAUDECODE=""` |
| `cleanup`         | `True`                              | Keep `RunResult.workspace` by setting `False` |

The `CLAUDECODE=""` default disables the CLI's nested-session check, so calls
from within a Claude Code session work.

SDK errors are captured into `RunResult.error` rather than raised, so a single
failing run doesn't kill a batch.

## Development

```bash
make install     # uv sync
make lint        # ruff check --fix
make format      # ruff format
make typecheck   # pyright (strict)
make test        # pytest
make check       # lint + typecheck + test
```
