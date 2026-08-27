"""
CodeFRAME: Fully Remote Autonomous Multiagent Environment for Coding

An autonomous AI development system where multiple specialized agents
collaborate to build software projects from requirements to deployment.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("codeframe-ai")
except PackageNotFoundError:  # source checkout, never installed
    __version__ = "0.0.0+unknown"

__author__ = "Frank Bria"

__all__ = ["__version__", "__author__"]
