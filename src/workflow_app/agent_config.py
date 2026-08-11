"""Per-role model and reasoning-effort configuration (ADR 0036).

The product configuration layer for agent selection: which runtime runs
each role, what model and effort it uses, and what an operator may
choose. Adapters stay free of product policy (plan section 31) — an
adapter built with no arguments still runs its CLI's own default.

Both entry points read these: the CLI resolves flags against them, and
the server serves them to the UI and validates run requests with them.
"""

import json
from dataclasses import dataclass

CLAUDE = "claude"
CODEX = "codex"

# Role -> runtime. Roles name invocation kinds (ADR 0014); the mapping
# itself is an engine decision, not an operator choice.
ROLE_RUNTIMES = {
    "scoping": CLAUDE,
    "filler": CLAUDE,
    "revision": CLAUDE,
    "reviewer": CODEX,
    "re_review": CODEX,
}

# Pinned product defaults (ADR 0020): a CLI upgrade or account-default
# change must never silently shift engine behavior.
DEFAULT_MODELS = {
    CLAUDE: "claude-opus-4-6[1m]",
    CODEX: "gpt-5.6-sol",
}

# Effort vocabularies are the CLIs' own. Claude's `--effort` is newer
# than ADR 0020, which recorded that no dependable knob existed.
EFFORT_CHOICES = {
    CLAUDE: ("low", "medium", "high", "xhigh", "max"),
    CODEX: ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"),
}

# None means "leave the CLI's own default in place". Review depth is
# deliberate configuration, so the review roles pin high (ADR 0020);
# the Claude roles keep the CLI default until an operator asks for more.
DEFAULT_EFFORTS = {
    CLAUDE: None,
    CODEX: "high",
}

# Offered in the UI as suggestions, not as a closed list: model names
# change faster than this file, so the field stays free text.
MODEL_SUGGESTIONS = {
    CLAUDE: (
        "claude-opus-4-6[1m]",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
    ),
    CODEX: ("gpt-5.6-sol",),
}


@dataclass(frozen=True)
class AgentChoice:
    runtime: str
    model: str
    effort: str | None

    def as_dict(self):
        return {"model": self.model, "effort": self.effort}


def default_agent_config():
    return {
        role: AgentChoice(
            runtime=runtime,
            model=DEFAULT_MODELS[runtime],
            effort=DEFAULT_EFFORTS[runtime],
        )
        for role, runtime in ROLE_RUNTIMES.items()
    }


def build_agent_config(selections=None, base=None):
    """Resolve operator selections against `base` (the defaults by default).

    `selections` maps a role to {"model": str | None, "effort": str | None};
    an absent role, key, or None value keeps the base value. Resuming
    passes the run's recorded config as the base, so an unflagged resume
    continues on the models the run started with. Raises ValueError on an
    unknown role, an unknown effort level, or a blank model — a mistyped
    selection must fail before the run starts, not when the agent
    process rejects it mid-run.
    """
    config = dict(base or default_agent_config())
    for role, selection in (selections or {}).items():
        if role not in config:
            raise ValueError(
                f"unknown agent role {role!r};"
                f" known roles are {sorted(ROLE_RUNTIMES)}"
            )
        current = config[role]
        model = selection.get("model") if selection else None
        effort = selection.get("effort") if selection else None
        if model is not None and not str(model).strip():
            raise ValueError(f"model for role {role!r} must not be blank")
        if effort is not None and effort not in EFFORT_CHOICES[current.runtime]:
            raise ValueError(
                f"unknown effort {effort!r} for role {role!r};"
                f" {current.runtime} accepts"
                f" {list(EFFORT_CHOICES[current.runtime])}"
            )
        config[role] = AgentChoice(
            runtime=current.runtime,
            model=current.model if model is None else str(model).strip(),
            effort=current.effort if effort is None else effort,
        )
    return config


def agent_options():
    """What an operator may choose, per role — the UI's source of truth."""
    return [
        {
            "role": role,
            "runtime": runtime,
            "model": DEFAULT_MODELS[runtime],
            "model_suggestions": list(MODEL_SUGGESTIONS[runtime]),
            "effort": DEFAULT_EFFORTS[runtime],
            "effort_choices": list(EFFORT_CHOICES[runtime]),
        }
        for role, runtime in ROLE_RUNTIMES.items()
    ]


def write_agent_config(path, config):
    """Persist the run's agent choices beside its inputs.

    A resume is a fresh process — often a fresh server — so the run has
    to carry its own configuration or the second half would silently run
    on different models than the first.
    """
    path.write_text(
        json.dumps(
            {role: choice.as_dict() for role, choice in config.items()}, indent=2
        )
    )


def read_agent_config(path):
    """The choices a run was started with; defaults if it recorded none."""
    if not path.is_file():
        return default_agent_config()
    return build_agent_config(json.loads(path.read_text()))
