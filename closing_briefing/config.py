"""
Configuration for the Korean closing market briefing pipeline.
"""

import os
from typing import Optional


class Config:
    """Configuration settings for the closing briefing pipeline."""
    
    # OpenAI API settings
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    
    # Pipeline settings
    DEFAULT_MAX_ITERATIONS: int = 1
    
    # LLM response settings
    MAX_TOKENS: int = 8192  # Larger for script generation
    
    # Output settings
    OUTPUT_DIR: str = os.getenv("CLOSING_BRIEFING_OUTPUT_DIR", "output/closing_briefings")
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present."""
        if not cls.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Please set it before running the pipeline."
            )


class InvalidLLMJSONError(Exception):
    """Raised when the LLM returns invalid JSON that cannot be parsed."""
    
    def __init__(self, message: str, raw_response: Optional[str] = None):
        super().__init__(message)
        self.raw_response = raw_response

