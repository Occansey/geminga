"""Portable Gemini agent core.

Built for All Things Agentic; the plan/step model and tool layer are meant to
survive the port to Agentic Cinema (partner tool swap) and Agents for Humans
(AWS Strands). See ports.py for the seam.
"""

from .config import settings
from .ports import Plan, Step

__all__ = ["settings", "Plan", "Step"]
__version__ = "0.1.0"
