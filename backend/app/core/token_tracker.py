import time
from typing import Dict, Any, Optional

class TokenTracker:
    """
    Priority 2: Token Budget Tracking per orchestrator call.
    Tracks prompt tokens, completion tokens, and estimated cost for governance.
    """
    def __init__(self, model_name: str = "gpt-4-mock"):
        self.model_name = model_name
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        
        # Mock pricing (per 1k tokens)
        self.rates = {
            "gpt-4-mock": {"prompt": 0.03, "completion": 0.06},
            "gpt-3.5-mock": {"prompt": 0.0015, "completion": 0.002},
            "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
            "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
            "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        }
        
    def add_call(self, prompt_tokens: int, completion_tokens: int, model_override: Optional[str] = None):
        """Register a single LLM API call."""
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.calls += 1
        if model_override and model_override != self.model_name:
            self.model_name = model_override

    def get_estimated_cost(self) -> float:
        """Calculate cost in USD based on tracked tokens."""
        rate = self.rates.get(self.model_name, self.rates["gpt-4-mock"])
        prompt_cost = (self.prompt_tokens / 1000.0) * rate["prompt"]
        comp_cost = (self.completion_tokens / 1000.0) * rate["completion"]
        return round(prompt_cost + comp_cost, 6)

    def get_summary(self) -> Dict[str, Any]:
        """Return the summary dictionary for API responses."""
        return {
            "model": self.model_name,
            "total_calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "estimated_cost_usd": self.get_estimated_cost()
        }

# Global instance for tracking across the lifecycle of a request if needed, 
# but usually it's better to instantiate per request.
