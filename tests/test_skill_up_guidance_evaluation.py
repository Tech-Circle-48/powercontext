from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from powercontext.server.mcp import _MCP_OPERATION_IDS

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "evaluation/skill-up"
EVAL = PROJECT / "evals/eval.yaml"
CASE_NAMES = (
    "01-ordinary-coding.yaml",
    "02-explicit-memory-save.yaml",
    "03-empty-memory-search.yaml",
    "04-inspect-candidates.yaml",
    "05-failed-memory-save.yaml",
)
PREFIX = "mcp__powercontext__"


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def success_rules(case: dict[str, Any]) -> list[dict[str, Any]]:
    judge = case["judge"]
    assert isinstance(judge, dict) and judge["type"] == "rule_based"
    rules = judge["success"]
    assert isinstance(rules, list)
    return rules


def tool_names(case: dict[str, Any], rule_name: str) -> set[str]:
    names: set[str] = set()
    for rule in success_rules(case):
        payload = rule.get(rule_name)
        if isinstance(payload, dict):
            name = payload.get("name")
            assert isinstance(name, str)
            names.add(name)
    return names


def test_eval_uses_real_mcp_serial_benchmark_and_machine_reports() -> None:
    config = load_yaml(EVAL)
    assert config["schema_version"] == "v1alpha1"
    assert config["environment"] == {"type": "none"}
    assert config["engine"] == {"name": "claude_code"}
    assert config["judge"] == {"type": "rule_based"}
    assert config["benchmark"] == {"enabled": True}
    assert config["report"] == {"formats": ["json", "junit", "html"], "artifacts": ["transcript"]}
    assert config["skills"] == [
        {
            "source": "local_path",
            "path": "vendor/powercontext-plugin/skills/powercontext-project-context",
            "include": ["SKILL.md", "references/**"],
        }
    ]

    cases = config["cases"]
    assert isinstance(cases, dict)
    assert cases["defaults"] == {"timeout_seconds": 300, "max_turns": 8}
    assert cases["parallelism"] == 1
    assert cases["files"] == [f"evals/cases/{name}" for name in CASE_NAMES]

    servers = config["mcp"]["servers"]
    assert servers == [
        {
            "name": "powercontext",
            "mode": "real",
            "transport": "http",
            "endpoint": "http://127.0.0.1:8000/mcp",
            "config_ref": "evals/fixtures/mcp/powercontext.yaml",
        }
    ]
    assert "headers" not in servers[0]


def test_cases_cover_positive_negative_and_authorization_controls() -> None:
    cases = {name: load_yaml(PROJECT / "evals/cases" / name) for name in CASE_NAMES}
    ordinary = cases["01-ordinary-coding.yaml"]
    forbidden = tool_names(ordinary, "tool_not_called_in_turn")
    assert forbidden == {PREFIX + name for name in _MCP_OPERATION_IDS}
    assert all(rule["tool_not_called_in_turn"]["turn"] == 1 for rule in success_rules(ordinary))

    explicit_save = cases["02-explicit-memory-save.yaml"]
    assert success_rules(explicit_save) == [{"tool_called_in_turn": {"turn": 1, "name": PREFIX + "remember_memory"}}]

    empty_search = cases["03-empty-memory-search.yaml"]
    assert success_rules(empty_search) == [
        {"tool_called_in_turn": {"turn": 1, "name": PREFIX + "search_memory"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "remember_memory"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "list_memory_entries"}},
        {"output_matches": {"not": ["(?i)(restored|recalled|persisted|saved) (the |this )?(context|memory)"]}},
    ]

    inspect = cases["04-inspect-candidates.yaml"]
    assert success_rules(inspect) == [
        {"tool_called_in_turn": {"turn": 1, "name": PREFIX + "list_artifact_candidates"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "approve_artifact_candidate"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "reject_artifact_candidate"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "revise_artifact_candidate"}},
        {"tool_not_called_in_turn": {"turn": 1, "name": PREFIX + "publish_artifact"}},
    ]

    failed = cases["05-failed-memory-save.yaml"]
    assert success_rules(failed) == [
        {"tool_called_in_turn": {"turn": 1, "name": PREFIX + "remember_memory"}},
        {
            "output_matches": {
                "not": [
                    "(?i)(successfully|successfully been) (saved|persisted|remembered)",
                    "(?i)(saved|persisted|remembered) successfully",
                ]
            }
        },
    ]
    assert failed["mcp"] == {
        "servers": [
            {
                "name": "powercontext",
                "mode": "mocked",
                "config_ref": "evals/fixtures/mcp/failed-write.yaml",
            }
        ]
    }


def test_mcp_fixtures_keep_auth_and_failure_at_the_supported_boundary() -> None:
    real = load_yaml(PROJECT / "evals/fixtures/mcp/powercontext.yaml")
    assert real == {"headers": {"Authorization": "${POWERCONTEXT_CLAUDE_AUTHORIZATION}"}}
    failed = load_yaml(PROJECT / "evals/fixtures/mcp/failed-write.yaml")
    assert set(failed["tool_responses"]) == {"remember_memory"}
    assert failed["tool_responses"]["remember_memory"]["default"]["status"] == "failed"
