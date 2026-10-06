"""Assembles the roster. The one module that imports every agent (agents never import each other)."""

from api.agents.framework import Roster
from api.agents.graph_agent import GRAPH_AGENT
from api.agents.orchestrator import ORCHESTRATOR
from api.agents.research import RESEARCH


def default_roster() -> Roster:
    return Roster([ORCHESTRATOR, GRAPH_AGENT, RESEARCH])
