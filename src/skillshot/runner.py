"""
One-shot Claude Agent SDK runs in ephemeral workspaces
"""

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionMode,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from .workspace import workspace as _workspace_cm

_DEFAULT_TOOLS: list[str] = ["Read", "Write", "Glob", "Grep"]
_DEFAULT_ENV: dict[str, str] = {"MPLBACKEND": "Agg", "CLAUDECODE": ""}
_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


@dataclass
class RunResult:
    """
    Outcome of a single :func:`run` invocation
    """

    workspace: Path | None
    assistant_messages: list[AssistantMessage] = field(
        default_factory=list[AssistantMessage]
    )
    result_message: ResultMessage | None = None
    stderr: str = ""
    error: str | None = None

    def assistant_text(self) -> str:
        """
        Concatenate all `TextBlock` text across assistant messages
        """
        parts: list[str] = []
        for msg in self.assistant_messages:
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        return "\n".join(parts)

    def code_blocks(self, language: str | None = None) -> list[str]:
        """
        Extract fenced code blocks from assistant text, optionally by language
        """
        out: list[str] = []
        for match in _FENCE_RE.finditer(self.assistant_text()):
            lang, body = match.group(1), match.group(2)
            if language is None or lang == language:
                out.append(body)
        return out

    def tool_calls(self, name: str | None = None) -> list[ToolUseBlock]:
        """
        Collect `ToolUseBlock` instances, optionally filtered by tool name
        """
        out: list[ToolUseBlock] = []
        for msg in self.assistant_messages:
            for block in msg.content:
                if isinstance(block, ToolUseBlock) and (
                    name is None or block.name == name
                ):
                    out.append(block)
        return out

    def extract_last_code_block(self, language: str | None = None) -> str | None:
        """
        Return the last fenced code block in assistant text, or None
        """
        blocks = self.code_blocks(language=language)
        return blocks[-1] if blocks else None

    @property
    def num_turns(self) -> int:
        return self.result_message.num_turns if self.result_message else 0

    @property
    def total_cost_usd(self) -> float:
        if self.result_message and self.result_message.total_cost_usd is not None:
            return self.result_message.total_cost_usd
        return 0.0

    @property
    def is_error(self) -> bool:
        if self.error:
            return True
        if self.result_message is None:
            return True
        return bool(self.result_message.is_error)


class _LogCapture(logging.Handler):
    """
    Capture the `claude_agent_sdk` logger as a stderr safety net
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))


async def run(
    prompt: str,
    skills: list[Path] | None = None,
    *,
    extra_dirs: dict[str, Path] | None = None,
    tools: Iterable[str] = _DEFAULT_TOOLS,
    max_turns: int = 10,
    model: str | None = None,
    permission_mode: PermissionMode = "bypassPermissions",
    env: dict[str, str] | None = None,
    cleanup: bool = True,
) -> RunResult:
    """
    Run a prompt against the Claude Agent SDK in an ephemeral workspace

    Parameters
    ----------
    prompt
        The user prompt to send to the agent.
    skills
        Skill directories to expose to the agent.
    extra_dirs
        Additional directories to symlink into the workspace.
    tools
        Tools the agent may use.
    max_turns
        Maximum agent turns.
    model
        Model identifier passed through to the SDK. `None` uses the SDK
        default.
    permission_mode
        SDK `permission_mode`. Default `"bypassPermissions"` enables
        unattended runs.
    env
        Extra environment variables, merged over `MPLBACKEND=Agg` and
        `CLAUDECODE=""` (which bypasses the CLI's nested-session check).
    cleanup
        If True, delete the workspace after the run. `RunResult.workspace`
        will be `None`.

    Returns
    -------
    RunResult
        Raw SDK messages plus accessors. `RunResult.error` is set on SDK
        failure rather than raising.
    """
    skills = skills or []
    merged_env = {**_DEFAULT_ENV, **(env or {})}
    stderr_lines: list[str] = []

    log_capture = _LogCapture()
    sdk_logger = logging.getLogger("claude_agent_sdk")
    sdk_logger.addHandler(log_capture)
    propagate_was = sdk_logger.propagate
    sdk_logger.propagate = False

    assistant_msgs: list[AssistantMessage] = []
    result_msg: ResultMessage | None = None
    agent_error: str | None = None
    kept_ws: Path | None = None

    try:
        with _workspace_cm(skills, extra_dirs, cleanup=cleanup) as ws:
            opts = ClaudeAgentOptions(
                system_prompt={"type": "preset", "preset": "claude_code"},
                setting_sources=["project"],
                cwd=str(ws),
                env=merged_env,
                tools=list(tools),
                max_turns=max_turns,
                permission_mode=permission_mode,
                model=model,
                stderr=stderr_lines.append,
            )
            try:
                async for msg in query(prompt=prompt, options=opts):
                    if isinstance(msg, AssistantMessage):
                        assistant_msgs.append(msg)
                    elif isinstance(msg, ResultMessage):
                        result_msg = msg
            except Exception as exc:  # noqa: BLE001  SDK raises bare Exception
                agent_error = str(exc)

            kept_ws = None if cleanup else ws
    finally:
        sdk_logger.removeHandler(log_capture)
        sdk_logger.propagate = propagate_was

    return RunResult(
        workspace=kept_ws,
        assistant_messages=assistant_msgs,
        result_message=result_msg,
        stderr="\n".join(stderr_lines + log_capture.records),
        error=agent_error,
    )


def run_sync(
    prompt: str, skills: list[Path] | None = None, **kwargs: object
) -> RunResult:
    """
    Synchronous wrapper around :func:`run` for ad-hoc / notebook use

    Do not call from inside a running event loop — `asyncio.run` will
    raise.
    """
    return asyncio.run(run(prompt, skills, **kwargs))  # type: ignore[arg-type]
