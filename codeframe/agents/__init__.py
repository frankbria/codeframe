"""Agent utilities for CodeFRAME.

The legacy multi-agent orchestration (LeadAgent/WorkerAgent/AgentFactory) was
removed during the v1 cleanup. Only the dependency resolver remains, used by the
live ``cf`` task-scheduling commands. Import it directly:

    from codeframe.agents.dependency_resolver import ...
"""
