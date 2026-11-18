"""The agents this project can run, by name.

Adding the next agent is a module in this folder plus a line in ``AGENTS``.
"""

from __future__ import annotations

from collections.abc import Callable

from agno.agent import Agent

from app.agents.insurance_parser import AGENT_NAME as INSURANCE_PARSER_NAME
from app.agents.insurance_parser import build_insurance_agent

AgentFactory = Callable[[], Agent]

AGENTS: dict[str, AgentFactory] = {
    INSURANCE_PARSER_NAME: build_insurance_agent,
}


def get_agent(name: str) -> Agent:
    """Build a fresh agent by name.

    A new instance per call keeps runs independent of each other.
    """
    try:
        factory = AGENTS[name]
    except KeyError:
        raise KeyError(
            f"unknown agent {name!r}; registered: {', '.join(sorted(AGENTS))}"
        ) from None
    return factory()
