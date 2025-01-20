"""Type definitions for the agent module."""

from dataclasses import dataclass


@dataclass
class AgentStats:
    """Statistics for tracking agent's token usage and steps."""

    input_tokens: int = 0
    output_tokens: int = 0
    step_counter: float = 0
