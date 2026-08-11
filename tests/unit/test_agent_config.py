"""Unit tests for per-role agent configuration (ADR 0036)."""

import pytest

from workflow_app.agent_config import (
    DEFAULT_MODELS,
    ROLE_RUNTIMES,
    agent_options,
    build_agent_config,
    default_agent_config,
    read_agent_config,
    write_agent_config,
)


def test_defaults_cover_every_role_with_its_runtime():
    config = default_agent_config()

    assert set(config) == set(ROLE_RUNTIMES)
    assert config["filler"].runtime == "claude"
    assert config["reviewer"].runtime == "codex"
    # Review depth is deliberate configuration (ADR 0020).
    assert config["reviewer"].effort == "high"
    # The Claude roles keep the CLI's own default until asked otherwise.
    assert config["filler"].effort is None


def test_a_selection_changes_one_role_only():
    config = build_agent_config({"reviewer": {"model": "gpt-5.6-sol", "effort": "max"}})

    assert config["reviewer"].effort == "max"
    assert config["re_review"].effort == "high"
    assert config["filler"].model == DEFAULT_MODELS["claude"]


def test_a_mistyped_selection_fails_before_the_run_starts():
    # Rejected here, not by the agent process ten minutes into a run.
    with pytest.raises(ValueError, match="unknown agent role"):
        build_agent_config({"filer": {"model": "claude-sonnet-5"}})
    with pytest.raises(ValueError, match="unknown effort"):
        build_agent_config({"filler": {"effort": "ultra"}})
    with pytest.raises(ValueError, match="must not be blank"):
        build_agent_config({"filler": {"model": "   "}})


def test_codex_keeps_its_wider_effort_vocabulary():
    assert build_agent_config({"reviewer": {"effort": "ultra"}})["reviewer"].effort == (
        "ultra"
    )


def test_the_recorded_config_survives_a_round_trip(tmp_path):
    config = build_agent_config(
        {"filler": {"model": "claude-sonnet-5", "effort": "max"}}
    )
    path = tmp_path / "agents.json"
    write_agent_config(path, config)

    assert read_agent_config(path) == config


def test_a_run_that_recorded_nothing_reads_as_the_defaults(tmp_path):
    assert read_agent_config(tmp_path / "absent.json") == default_agent_config()


def test_options_describe_every_role_for_the_ui():
    options = {entry["role"]: entry for entry in agent_options()}

    assert set(options) == set(ROLE_RUNTIMES)
    assert options["filler"]["model_suggestions"][0] == DEFAULT_MODELS["claude"]
    assert "max" in options["filler"]["effort_choices"]
    assert "ultra" in options["reviewer"]["effort_choices"]
    assert "ultra" not in options["filler"]["effort_choices"]
