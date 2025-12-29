"""
Pydantic models for the Korean closing market briefing pipeline.

Defines the state model and supporting data structures for the LangGraph workflow.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from enum import Enum


# ============================================================================
# Supporting Data Models
# ============================================================================

class EarningsResult(BaseModel):
    """Represents a single company's earnings result."""
    company_name: str
    ticker: Optional[str] = None
    eps_actual: Optional[float] = None
    eps_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    yoy_growth_pct: Optional[float] = None
    beat_or_miss: Optional[str] = None  # "beat", "miss", "inline"
    key_drivers: List[str] = Field(default_factory=list)
    sector: Optional[str] = None
    stock_reaction: Optional[str] = None  # e.g., "+3% 상승", "-2% 하락"


class NewsItem(BaseModel):
    """Represents a notable news item."""
    headline: str
    source: Optional[str] = None
    category: str  # "macro", "company", "sector", "geopolitical"
    summary: Optional[str] = None
    market_impact: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class UpcomingEvent(BaseModel):
    """Represents an upcoming economic/market event."""
    date: str
    name: str
    importance: str  # "high", "medium", "low"
    description: Optional[str] = None
    why_it_matters: Optional[str] = None


class MacroIndicator(BaseModel):
    """Represents a macroeconomic indicator."""
    name: str
    value: float
    unit: str
    date: str
    previous: Optional[float] = None
    change_direction: Optional[str] = None  # "up", "down", "flat"


class ExtractedFact(BaseModel):
    """A structured fact extracted from source data."""
    fact_type: str  # "earnings", "news", "macro", "event"
    content: Dict[str, Any]
    importance: str = "medium"
    source_key: Optional[str] = None


class Reference(BaseModel):
    """A reference to source data used in the briefing."""
    source_type: str  # "macro_data", "calendar_events", "news_data", "earnings_data", "fomc_events", "market_summary"
    source_file: str  # The file or table the data came from
    quote: str  # The exact quote or data value
    provider: Optional[str] = None  # News provider (Reuters, Bloomberg, etc.)
    date: Optional[str] = None  # Date of the data
    
    def to_citation_tag(self) -> str:
        """Format as a citation tag for the script."""
        tag = f"[REF: {self.source_type} | \"{self.quote}\""
        if self.provider:
            tag += f" - {self.provider}"
        tag += "]"
        return tag


class StructuredSource(BaseModel):
    """
    A structured source reference for validation.
    
    Compatible with validation_agent's expected format:
    - type: "article" | "indicator" | "event" | "chart" | "earnings" | "fomc"
    - pk/id/ticker: unique identifier
    - title/name: human-readable name
    - date: date of the data
    """
    type: str  # "article", "indicator", "event", "chart", "earnings", "fomc"
    
    # Identifiers (depending on type)
    pk: Optional[str] = None  # For articles (e.g., "id#9e4894ca63cd8d66")
    id: Optional[str] = None  # For events (e.g., "387585")
    ticker: Optional[str] = None  # For charts (e.g., "^GSPC")
    
    # Human-readable fields
    title: Optional[str] = None  # For articles/events
    name: Optional[str] = None  # For indicators
    company: Optional[str] = None  # For earnings
    
    # Data fields
    value: Optional[str] = None  # For indicators
    date: Optional[str] = None
    provider: Optional[str] = None  # For articles
    
    # Original reference info
    source_type: Optional[str] = None  # Original source_type (macro_data, news_data, etc.)
    quote: Optional[str] = None  # Original quote


# ============================================================================
# Critic Feedback Model
# ============================================================================

class ChecklistItem(BaseModel):
    """Single item in the critic's checklist evaluation."""
    item_name: str
    status: str  # "충족", "미흡", or "심각한 미흡"
    explanation: str


class HallucinationItem(BaseModel):
    """A detected hallucination in the script."""
    fabricated_content: str  # What was said in the script
    explanation: str  # Why it's considered a hallucination


class CriticFeedback(BaseModel):
    """Feedback from the Critic Agent."""
    summary_evaluation: str  # 3-5 sentence summary
    
    # Critical validation results
    hallucination_check: ChecklistItem  # 환각 검증
    timeliness_check: ChecklistItem  # 시의성 검증
    value_check: ChecklistItem  # 정보 가치 검증
    source_citation_check: ChecklistItem = Field(
        default_factory=lambda: ChecklistItem(
            item_name="4. 출처 명시(Source Citation) 검증",
            status="충족",
            explanation="검증 결과를 파싱할 수 없습니다."
        ),
        description="출처 명시 검증"
    )
    hallucinations_found: List[HallucinationItem] = Field(
        default_factory=list,
        description="List of detected hallucinations/fabricated content"
    )
    
    # Content and style checklist
    checklist: List[ChecklistItem]
    specific_suggestions: List[str]
    overall_quality: str = "needs_improvement"  # "우수", "양호", "보통", "미흡", "심각"
    
    @property
    def needs_revision(self) -> bool:
        """Check if this feedback indicates revision is needed."""
        # Hallucinations always require revision
        if self.hallucinations_found:
            return True
        # Failed critical checks require revision
        if self.hallucination_check.status in ["미흡", "심각한 미흡"]:
            return True
        if self.timeliness_check.status in ["미흡", "심각한 미흡"]:
            return True
        if self.value_check.status == "심각한 미흡":
            return True
        # Poor overall quality requires revision
        if self.overall_quality in ["심각", "미흡"]:
            return True
        return False
    
    @property
    def revision_reason(self) -> str:
        """Get the reason why revision is needed."""
        reasons = []
        if self.hallucinations_found:
            reasons.append(f"환각 {len(self.hallucinations_found)}개 발견")
        if self.hallucination_check.status in ["미흡", "심각한 미흡"]:
            reasons.append("환각 검증 실패")
        if self.timeliness_check.status in ["미흡", "심각한 미흡"]:
            reasons.append("시의성 검증 실패")
        if self.value_check.status == "심각한 미흡":
            reasons.append("정보 가치 심각히 미흡")
        if self.overall_quality in ["심각", "미흡"]:
            reasons.append(f"전체 품질: {self.overall_quality}")
        return ", ".join(reasons) if reasons else "품질 기준 충족"


# ============================================================================
# Main Graph State Model
# ============================================================================

class ClosingBriefingState(BaseModel):
    """
    State object passed through the LangGraph pipeline for closing market briefing.
    
    This state contains all data and intermediate outputs as the pipeline
    progresses through its nodes.
    """
    
    # -------------------------------------------------------------------------
    # Raw source data
    # -------------------------------------------------------------------------
    sources: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw data loaded from source files (macro, earnings, news, calendar)"
    )
    
    # -------------------------------------------------------------------------
    # Extracted and processed data
    # -------------------------------------------------------------------------
    extracted_facts: List[ExtractedFact] = Field(
        default_factory=list,
        description="Structured key facts extracted from sources"
    )
    
    keywords: List[str] = Field(
        default_factory=list,
        description="Today's main keywords/themes (1-3 items)"
    )
    
    # Detailed extractions for script generation
    earnings_results: List[EarningsResult] = Field(
        default_factory=list,
        description="Parsed earnings results with key metrics"
    )
    
    news_items: List[NewsItem] = Field(
        default_factory=list,
        description="Notable news items categorized by type"
    )
    
    upcoming_events: List[UpcomingEvent] = Field(
        default_factory=list,
        description="Key upcoming events for next week outlook"
    )
    
    macro_summary: List[MacroIndicator] = Field(
        default_factory=list,
        description="Summary of key macro indicators"
    )
    
    # -------------------------------------------------------------------------
    # Script generation outputs
    # -------------------------------------------------------------------------
    script_draft: Optional[str] = Field(
        default=None,
        description="First full script draft (Host + Analyst dialogue)"
    )
    
    critic_feedback: Optional[CriticFeedback] = Field(
        default=None,
        description="Critic's review and suggestions"
    )
    
    script_revised: Optional[str] = Field(
        default=None,
        description="Final revised script after critic feedback"
    )
    
    # -------------------------------------------------------------------------
    # References tracking
    # -------------------------------------------------------------------------
    references: List[Reference] = Field(
        default_factory=list,
        description="List of all references used in the script"
    )
    
    structured_sources: List[StructuredSource] = Field(
        default_factory=list,
        description="Structured source list for validation agent (article, event, chart, indicator)"
    )
    
    # -------------------------------------------------------------------------
    # Iteration control
    # -------------------------------------------------------------------------
    iterations: int = Field(
        default=0,
        description="Number of refinement loops performed"
    )
    
    max_iterations: int = Field(
        default=1,
        description="Maximum number of critic-revision iterations"
    )
    
    # -------------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------------
    briefing_date: Optional[str] = Field(
        default=None,
        description="Date of the briefing (YYYY-MM-DD)"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if any step fails"
    )
    
    class Config:
        arbitrary_types_allowed = True


# ============================================================================
# Input Configuration Model
# ============================================================================

class BriefingConfig(BaseModel):
    """Configuration for running the closing briefing pipeline."""
    source_path: str = Field(
        description="Path to the source data directory or bundle"
    )
    max_iterations: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Max critic-revision iterations (1-10). Stops early if quality is acceptable."
    )
    briefing_date: Optional[str] = Field(
        default=None,
        description="Override date for the briefing (YYYY-MM-DD)"
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Path to save the final script"
    )

