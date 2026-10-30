"""Documented interface counts must match the code that serves them.

The README states the CLI subcommand count, the MCP tool count and the
entry-point list in prose and tables. Those numbers drift from the installed
handlers silently once the code changes, so they are pinned here against the
real parser, the real tool registry and ``pyproject.toml`` instead of being
trusted as text.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from axiomize import cli
from axiomize.server import mcp_server

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _backticked(text: str) -> set[str]:
    return set(re.findall(r"`([a-z][a-z0-9_-]*)`", text))


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("parser has no subcommands")


def _documented_subcommands(readme: str) -> set[str]:
    for line in readme.splitlines():
        if "subcommands:" in line:
            return _backticked(line.split("subcommands:", 1)[1])
    raise AssertionError("README has no line listing the CLI subcommands")


def _documented_tools(integrations: str) -> set[str]:
    lines = integrations.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("**34 tools**"):
            start = index + 1
            break
    if start is None:
        raise AssertionError("integrations.md has no `**34 tools**` marker")
    tools: set[str] = set()
    in_table = False
    for line in lines[start:]:
        if not line.startswith("|"):
            if in_table:
                break
            continue
        in_table = True
        cells = line.strip("|").split("|")
        if len(cells) < 2 or "Tools" in cells[1]:
            continue
        tools |= _backticked(cells[1])
    return tools


def test_documented_subcommands_match_the_parser() -> None:
    readme = _read("README.md")
    documented = _documented_subcommands(readme)
    choices = set(_subparsers_action(cli.build_parser()).choices)

    assert documented == choices, (
        f"README subcommands {sorted(documented)} != parser {sorted(choices)}"
    )
    assert len(choices) == 14
    assert "14 subcommands" in readme
    assert "14 subcommands" in _read("docs/integrations.md")


def test_documented_mcp_tools_match_the_registry() -> None:
    readme = _read("README.md")
    integrations = _read("docs/integrations.md")
    tools = set(mcp_server._TOOL_SCHEMAS)
    model_tools = {name for name in tools if ".model_" in name}

    assert len(tools) == 34, f"registry has {len(tools)} tools, README says 34"
    assert len(model_tools) == 15, f"registry has {len(model_tools)} model_* tools"
    assert "34 tools" in readme
    assert "**34 tools**" in integrations

    documented = _documented_tools(integrations)
    suffixes = {name.split(".", 1)[1] for name in tools}
    assert documented == suffixes, (
        f"integrations.md tools {sorted(documented)} != registry {sorted(suffixes)}"
    )
    assert len(documented) == 34


def test_documented_console_scripts_match_pyproject() -> None:
    readme = _read("README.md")
    pyproject = _read("pyproject.toml")
    scripts_block = pyproject.split("[project.scripts]", 1)[1].split("\n[", 1)[0]
    scripts = set(re.findall(r"^([a-z0-9-]+) = ", scripts_block, re.MULTILINE))

    assert len(scripts) == 9, sorted(scripts)
    assert "axiomize-reason" in scripts
    missing = scripts - _backticked(readme)
    assert not missing, f"console scripts missing from README: {sorted(missing)}"
