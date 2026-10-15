"""Assembles the roster. The one module that imports every agent (agents never import each other)."""

from api.agents.fact_checker import FACT_CHECKER
from api.agents.framework import Roster
from api.agents.graph_agent import GRAPH_AGENT
from api.agents.orchestrator import ORCHESTRATOR
from api.agents.research import RESEARCH
from api.agents.studio import STUDIO


def default_roster() -> Roster:
    return Roster([ORCHESTRATOR, GRAPH_AGENT, RESEARCH, STUDIO, FACT_CHECKER])
