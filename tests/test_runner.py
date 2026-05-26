import shutil
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

import skillshot.runner as runner


def _make_assistant(*blocks):
    return AssistantMessage(
        content=list(blocks),
        model="test-model",
        parent_tool_use_id=None,
        error=None,
    )


def _make_result(num_turns: int = 2, cost: float = 0.0123, is_error: bool = False):
    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=is_error,
        num_turns=num_turns,
        session_id="sess-1",
        total_cost_usd=cost,
        usage={"input_tokens": 10, "output_tokens": 20},
        result=None,
        structured_output=None,
    )


@pytest.fixture
def fake_skill(tmp_path: Path) -> Path:
    d = tmp_path / "alpha"
    d.mkdir()
    (d / "SKILL.md").write_text("# alpha")
    return d


@pytest.fixture
def scripted_query(monkeypatch):
    """Replace runner.query with one that yields a configurable script."""
    script: list = []

    async def fake_query(*, prompt, options):
        for msg in script:
            yield msg

    monkeypatch.setattr(runner, "query", fake_query)
    return script


async def test_run_collects_messages_and_result(fake_skill, scripted_query):
    scripted_query.extend(
        [
            _make_assistant(
                TextBlock(text="Here's the code:\n```python\nprint(1)\n```")
            ),
            _make_assistant(
                ToolUseBlock(
                    id="t1",
                    name="Write",
                    input={"file_path": "out.py", "content": "print(2)"},
                )
            ),
            _make_result(num_turns=3, cost=0.05),
        ]
    )

    result = await runner.run(prompt="hi", skills=[fake_skill], cleanup=True)

    assert result.is_error is False
    assert result.num_turns == 3
    assert result.total_cost_usd == 0.05
    assert result.workspace is None  # cleanup=True

    assert result.assistant_text().startswith("Here's the code:")
    assert result.code_blocks(language="python") == ["print(1)\n"]
    assert result.extract_last_code_block(language="python") == "print(1)\n"

    writes = result.tool_calls("Write")
    assert len(writes) == 1
    assert writes[0].input["content"] == "print(2)"


async def test_run_preserves_workspace_when_no_cleanup(fake_skill, scripted_query):
    scripted_query.append(_make_result())
    result = await runner.run(prompt="hi", skills=[fake_skill], cleanup=False)
    try:
        assert result.workspace is not None
        assert result.workspace.exists()
        assert (result.workspace / ".claude" / "settings.json").exists()
    finally:
        if result.workspace is not None:
            shutil.rmtree(result.workspace, ignore_errors=True)


async def test_run_sets_error_when_sdk_raises(fake_skill, monkeypatch):
    async def boom(*, prompt, options):
        raise RuntimeError("transport went away")
        yield  # pragma: no cover

    monkeypatch.setattr(runner, "query", boom)

    result = await runner.run(prompt="hi", skills=[fake_skill])

    assert result.is_error is True
    assert "transport went away" in (result.error or "")
    assert result.result_message is None


async def test_run_no_result_message_is_error(fake_skill, scripted_query):
    scripted_query.append(_make_assistant(TextBlock(text="hello")))
    result = await runner.run(prompt="hi", skills=[fake_skill])
    assert result.is_error is True
    assert result.num_turns == 0
    assert result.total_cost_usd == 0.0


def test_run_sync_returns_runresult(fake_skill, monkeypatch):
    async def fake_query(*, prompt, options):
        yield _make_result(num_turns=1, cost=0.001)

    monkeypatch.setattr(runner, "query", fake_query)

    result = runner.run_sync(prompt="hi", skills=[fake_skill])
    assert result.num_turns == 1
    assert result.total_cost_usd == 0.001
