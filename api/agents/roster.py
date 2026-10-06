"""Assembles the roster. The one module that imports every agent (agents never import each other)."""

from api.agents.framework import Roster
from api.agents.orchestrator import ORCHESTRATOR
from api.agents.research import RESEARCH


def default_roster() -> Roster:
    return Roster([ORCHESTRATOR, RESEARCH])
