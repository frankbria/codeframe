"""
CodeFRAME: Fully Remote Autonomous Multiagent Environment for Coding

An autonomous AI development system where multiple specialized agents
collaborate to build software projects from requirements to deployment.
"""

__version__ = "0.1.0"
__author__ = "Frank Bria"

from codeframe.core.project import Project
from codeframe.agents.lead_agent import LeadAgent
from codeframe.agents.worker_agent import WorkerAgent

__all__ = ["Project", "LeadAgent", "WorkerAgent"]
