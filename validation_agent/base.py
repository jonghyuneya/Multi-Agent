"""
Base classes for the Validation Agent framework.

This module defines the abstract base classes and core data structures
that all source tools and validators must implement.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class ValidationStatus(Enum):
    """Status of a validation check."""
    VALID = "valid"           # Fact matches source exactly
    PARTIAL = "partial"       # Fact partially matches (minor differences)
    INVALID = "invalid"       # Fact does not match source
    NOT_FOUND = "not_found"   # Source reference not found
    ERROR = "error"           # Error during validation


class AudienceFitness(Enum):
    """How well content fits target audience."""
    EXCELLENT = "excellent"   # Perfect fit for audience
    GOOD = "good"             # Good fit with minor issues
    FAIR = "fair"             # Acceptable but could be improved
    POOR = "poor"             # Not suitable for audience


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SourceMatch:
    """Result of matching a claim against source data."""
    claim: str                          # The claim from the script
    source_type: str                    # Type of source (calendar, indicator, news, etc.)
    source_reference: str               # Reference string from script
    source_data: Optional[Dict[str, Any]] = None  # Actual source data found
    status: ValidationStatus = ValidationStatus.NOT_FOUND
    confidence: float = 0.0             # 0.0 to 1.0
    explanation: str = ""               # Human-readable explanation
    suggested_correction: Optional[str] = None  # Suggested fix if invalid


@dataclass
class ValidationResult:
    """Complete validation result for a script."""
    script_id: str
    validated_at: datetime = field(default_factory=datetime.now)
    
    # Fact validation results
    total_claims: int = 0
    valid_claims: int = 0
    invalid_claims: int = 0
    not_found_claims: int = 0
    source_matches: List[SourceMatch] = field(default_factory=list)
    
    # Audience fitness
    audience_fitness: AudienceFitness = AudienceFitness.GOOD
    audience_feedback: str = ""
    
    # Citation validation
    citations_complete: bool = True
    missing_citations: List[str] = field(default_factory=list)
    
    # Overall assessment
    overall_valid: bool = True
    summary: str = ""
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "script_id": self.script_id,
            "validated_at": self.validated_at.isoformat(),
            "total_claims": self.total_claims,
            "valid_claims": self.valid_claims,
            "invalid_claims": self.invalid_claims,
            "not_found_claims": self.not_found_claims,
            "source_matches": [
                {
                    "claim": sm.claim,
                    "source_type": sm.source_type,
                    "source_reference": sm.source_reference,
                    "status": sm.status.value,
                    "confidence": sm.confidence,
                    "explanation": sm.explanation,
                    "suggested_correction": sm.suggested_correction,
                }
                for sm in self.source_matches
            ],
            "audience_fitness": self.audience_fitness.value,
            "audience_feedback": self.audience_feedback,
            "citations_complete": self.citations_complete,
            "missing_citations": self.missing_citations,
            "overall_valid": self.overall_valid,
            "summary": self.summary,
            "errors": self.errors,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# =============================================================================
# Abstract Base Classes
# =============================================================================

class SourceTool(ABC):
    """
    Abstract base class for source data tools.
    
    Implement this class to add new source types for validation.
    Each source tool provides methods to:
    1. Load source data from files/databases
    2. Search for specific claims in the source
    3. Validate claims against source data
    
    To add a new source type:
    1. Subclass SourceTool
    2. Implement all abstract methods
    3. Register with ValidationAgent
    
    Example:
        class MySourceTool(SourceTool):
            @property
            def source_type(self) -> str:
                return "my_source"
            
            def load_sources(self, path: Path) -> None:
                # Load your source data
                pass
            
            def search(self, query: str) -> List[Dict[str, Any]]:
                # Search for matching data
                pass
            
            def validate_claim(self, claim: str, reference: str) -> SourceMatch:
                # Validate a specific claim
                pass
    """
    
    @property
    @abstractmethod
    def source_type(self) -> str:
        """Return the source type identifier (e.g., 'calendar', 'indicator')."""
        pass
    
    @abstractmethod
    def load_sources(self, path: Path) -> None:
        """
        Load source data from the given path.
        
        Args:
            path: Path to source data (file or directory)
        """
        pass
    
    @abstractmethod
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for data matching the query.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching source records
        """
        pass
    
    @abstractmethod
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """
        Validate a specific claim against source data.
        
        Args:
            claim: The claim text from the script
            reference: The reference string (e.g., from [REF: ...] tag)
            
        Returns:
            SourceMatch with validation result
        """
        pass
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Return OpenAI function calling tool definition.
        Override to customize the tool schema.
        """
        return {
            "type": "function",
            "function": {
                "name": f"search_{self.source_type}",
                "description": f"Search {self.source_type} source data for validation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find matching source data."
                        }
                    },
                    "required": ["query"]
                }
            }
        }


class Validator(ABC):
    """
    Abstract base class for validators.
    
    Implement this class to add new validation types.
    """
    
    @property
    @abstractmethod
    def validator_type(self) -> str:
        """Return the validator type identifier."""
        pass
    
    @abstractmethod
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """
        Perform validation on the script.
        
        Args:
            script: The script text to validate
            source_tools: Dictionary of registered source tools
            **kwargs: Additional validation parameters
            
        Returns:
            ValidationResult with validation outcomes
        """
        pass


# =============================================================================
# Validation Agent
# =============================================================================

class ValidationAgent:
    """
    Main validation agent that orchestrates source tools and validators.
    
    Usage:
        agent = ValidationAgent()
        
        # Register source tools
        agent.register_source_tool(TECalendarSourceTool())
        agent.register_source_tool(TEIndicatorsSourceTool())
        
        # Register validators
        agent.register_validator(FactValidator())
        agent.register_validator(AudienceValidator())
        
        # Load source data
        agent.load_sources({
            "calendar": Path("output/calendar"),
            "indicators": Path("output/indicators"),
        })
        
        # Validate a script
        result = agent.validate(script_text)
    """
    
    def __init__(self):
        self._source_tools: Dict[str, SourceTool] = {}
        self._validators: Dict[str, Validator] = {}
        self._sources_loaded: bool = False
    
    def register_source_tool(self, tool: SourceTool) -> None:
        """Register a source tool for validation."""
        self._source_tools[tool.source_type] = tool
        logger.info(f"Registered source tool: {tool.source_type}")
    
    def register_validator(self, validator: Validator) -> None:
        """Register a validator."""
        self._validators[validator.validator_type] = validator
        logger.info(f"Registered validator: {validator.validator_type}")
    
    def load_sources(self, source_paths: Dict[str, Path]) -> None:
        """
        Load source data for registered tools.
        
        Args:
            source_paths: Mapping of source_type to path
        """
        for source_type, path in source_paths.items():
            if source_type in self._source_tools:
                try:
                    self._source_tools[source_type].load_sources(path)
                    logger.info(f"Loaded sources for {source_type} from {path}")
                except Exception as e:
                    logger.error(f"Failed to load sources for {source_type}: {e}")
            else:
                logger.warning(f"No tool registered for source type: {source_type}")
        
        self._sources_loaded = True
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get OpenAI function calling definitions for all source tools."""
        return [tool.get_tool_definition() for tool in self._source_tools.values()]
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a source tool call.
        
        Args:
            tool_name: Name of the tool (e.g., "search_calendar")
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        # Extract source type from tool name (e.g., "search_calendar" -> "calendar")
        if tool_name.startswith("search_"):
            source_type = tool_name[7:]  # Remove "search_" prefix
        else:
            source_type = tool_name
        
        if source_type not in self._source_tools:
            return {"error": f"Unknown source type: {source_type}"}
        
        tool = self._source_tools[source_type]
        query = arguments.get("query", "")
        
        try:
            results = tool.search(query)
            return {
                "source_type": source_type,
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}
    
    def validate_claim(
        self,
        claim: str,
        source_type: str,
        reference: str
    ) -> SourceMatch:
        """
        Validate a single claim against source data.
        
        Args:
            claim: The claim text
            source_type: Type of source to validate against
            reference: The reference string
            
        Returns:
            SourceMatch with validation result
        """
        if source_type not in self._source_tools:
            return SourceMatch(
                claim=claim,
                source_type=source_type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"Unknown source type: {source_type}"
            )
        
        tool = self._source_tools[source_type]
        return tool.validate_claim(claim, reference)
    
    def validate(
        self,
        script: str,
        script_id: str = None,
        validators: List[str] = None,
        **kwargs
    ) -> ValidationResult:
        """
        Validate a script using registered validators.
        
        Args:
            script: The script text to validate
            script_id: Optional identifier for the script
            validators: List of validator types to use (None = all)
            **kwargs: Additional parameters passed to validators
            
        Returns:
            Combined ValidationResult
        """
        if not self._sources_loaded:
            logger.warning("Sources not loaded. Call load_sources() first.")
        
        script_id = script_id or f"script_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Determine which validators to run
        validators_to_run = validators or list(self._validators.keys())
        
        # Initialize combined result
        combined_result = ValidationResult(script_id=script_id)
        
        # Run each validator
        for validator_type in validators_to_run:
            if validator_type not in self._validators:
                logger.warning(f"Validator not found: {validator_type}")
                continue
            
            validator = self._validators[validator_type]
            try:
                result = validator.validate(script, self._source_tools, **kwargs)
                
                # Merge results
                combined_result.total_claims += result.total_claims
                combined_result.valid_claims += result.valid_claims
                combined_result.invalid_claims += result.invalid_claims
                combined_result.not_found_claims += result.not_found_claims
                combined_result.source_matches.extend(result.source_matches)
                combined_result.missing_citations.extend(result.missing_citations)
                combined_result.errors.extend(result.errors)
                
                # Use worst audience fitness
                if result.audience_fitness.value < combined_result.audience_fitness.value:
                    combined_result.audience_fitness = result.audience_fitness
                    combined_result.audience_feedback = result.audience_feedback
                
                # Update citation status
                if not result.citations_complete:
                    combined_result.citations_complete = False
                
            except Exception as e:
                logger.error(f"Error running validator {validator_type}: {e}")
                combined_result.errors.append(f"Validator {validator_type} error: {str(e)}")
        
        # Determine overall validity
        combined_result.overall_valid = (
            combined_result.invalid_claims == 0 and
            combined_result.citations_complete and
            combined_result.audience_fitness in [AudienceFitness.EXCELLENT, AudienceFitness.GOOD]
        )
        
        # Generate summary
        combined_result.summary = self._generate_summary(combined_result)
        
        return combined_result
    
    def _generate_summary(self, result: ValidationResult) -> str:
        """Generate a human-readable summary of validation results."""
        lines = []
        
        # Fact validation summary
        if result.total_claims > 0:
            valid_pct = (result.valid_claims / result.total_claims) * 100
            lines.append(f"사실 검증: {result.valid_claims}/{result.total_claims} ({valid_pct:.1f}%) 일치")
            
            if result.invalid_claims > 0:
                lines.append(f"  ⚠️ 불일치: {result.invalid_claims}건")
            if result.not_found_claims > 0:
                lines.append(f"  ❓ 출처 미확인: {result.not_found_claims}건")
        
        # Citation summary
        if not result.citations_complete:
            lines.append(f"출처 누락: {len(result.missing_citations)}건")
        
        # Audience fitness
        fitness_emoji = {
            AudienceFitness.EXCELLENT: "✅",
            AudienceFitness.GOOD: "👍",
            AudienceFitness.FAIR: "⚠️",
            AudienceFitness.POOR: "❌",
        }
        lines.append(f"대상 적합성: {fitness_emoji.get(result.audience_fitness, '')} {result.audience_fitness.value}")
        
        # Overall
        overall_emoji = "✅" if result.overall_valid else "❌"
        lines.append(f"전체 검증 결과: {overall_emoji} {'통과' if result.overall_valid else '수정 필요'}")
        
        return "\n".join(lines)

