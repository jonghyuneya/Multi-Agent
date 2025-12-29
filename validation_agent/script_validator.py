"""
Script Validator for structured briefing scripts.

This module provides a validator specifically designed for validating
briefing scripts with embedded source references in JSON format.

The script schema includes:
- date: Script date
- nutshell: Summary
- chapter: List of chapters with name, start_id, end_id
- scripts: List of script items with id, speaker, text, sources, time

Each script item can have sources of type:
- article: News article with pk and title
- chart: Market data with ticker and date range
- event: Calendar event with id, title, and date
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from validation_agent.base import (
    Validator,
    ValidationResult,
    SourceMatch,
    ValidationStatus,
    AudienceFitness,
    SourceTool,
)
from validation_agent.source_tools import (
    BriefingScriptSourceTool,
    ArticleSourceTool,
    EventSourceTool,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class ScriptSource:
    """Represents a source reference in a script."""
    type: str                          # article, chart, event
    pk: Optional[str] = None           # For articles
    ticker: Optional[str] = None       # For charts
    id: Optional[str] = None           # For events
    title: Optional[str] = None
    start_date: Optional[str] = None   # For charts
    end_date: Optional[str] = None     # For charts
    date: Optional[str] = None         # For events
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScriptSource":
        return cls(
            type=data.get("type", ""),
            pk=data.get("pk"),
            ticker=data.get("ticker"),
            id=str(data.get("id", "")) if data.get("id") else None,
            title=data.get("title"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            date=data.get("date"),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type}
        if self.pk:
            result["pk"] = self.pk
        if self.ticker:
            result["ticker"] = self.ticker
        if self.id:
            result["id"] = self.id
        if self.title:
            result["title"] = self.title
        if self.start_date:
            result["start_date"] = self.start_date
        if self.end_date:
            result["end_date"] = self.end_date
        if self.date:
            result["date"] = self.date
        return result


@dataclass
class ScriptItem:
    """Represents a single script item."""
    id: int
    speaker: str
    text: str
    sources: List[ScriptSource] = field(default_factory=list)
    time: List[int] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScriptItem":
        sources = [ScriptSource.from_dict(s) for s in data.get("sources", [])]
        return cls(
            id=data.get("id", 0),
            speaker=data.get("speaker", ""),
            text=data.get("text", ""),
            sources=sources,
            time=data.get("time", []),
        )


@dataclass
class BriefingScript:
    """Represents a complete briefing script."""
    date: str
    nutshell: str
    user_tickers: List[str]
    chapters: List[Dict[str, Any]]
    scripts: List[ScriptItem]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BriefingScript":
        scripts = [ScriptItem.from_dict(s) for s in data.get("scripts", [])]
        return cls(
            date=data.get("date", ""),
            nutshell=data.get("nutshell", ""),
            user_tickers=data.get("user_tickers", []),
            chapters=data.get("chapter", []),
            scripts=scripts,
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "BriefingScript":
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @classmethod
    def from_file(cls, path: Path) -> "BriefingScript":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def get_all_sources(self) -> List[Tuple[int, ScriptSource]]:
        """Get all sources with their script item IDs."""
        all_sources = []
        for script in self.scripts:
            for source in script.sources:
                all_sources.append((script.id, source))
        return all_sources
    
    def get_article_pks(self) -> List[str]:
        """Get all article pks referenced in the script."""
        pks = []
        for script in self.scripts:
            for source in script.sources:
                if source.type == "article" and source.pk:
                    pks.append(source.pk)
        return list(set(pks))
    
    def get_event_ids(self) -> List[str]:
        """Get all event IDs referenced in the script."""
        ids = []
        for script in self.scripts:
            for source in script.sources:
                if source.type == "event" and source.id:
                    ids.append(source.id)
        return list(set(ids))
    
    def get_tickers(self) -> List[str]:
        """Get all tickers referenced in the script."""
        tickers = []
        for script in self.scripts:
            for source in script.sources:
                if source.type == "chart" and source.ticker:
                    tickers.append(source.ticker)
        return list(set(tickers))


# =============================================================================
# Script Source Validator
# =============================================================================

SCRIPT_SOURCE_VALIDATOR_PROMPT = """당신은 브리핑 스크립트의 출처 정확성을 검증하는 에이전트입니다.

## 역할
스크립트의 각 문장(text)이 해당 출처(sources)와 일치하는지 확인합니다.

## 검증 기준
1. **출처 존재**: 인용된 출처가 실제로 존재하는가?
2. **내용 일치**: 스크립트의 내용이 출처 정보와 일치하는가?
3. **날짜 일치**: 날짜 관련 정보가 정확한가?
4. **수치 정확성**: 수치나 퍼센트가 정확한가?

## 도구 사용
다음 도구를 사용하여 출처를 검증하세요:
- search_article: 뉴스 기사 검색 (pk 또는 title로)
- search_event: 경제 이벤트 검색 (id 또는 title로)
- search_briefing_sources: 모든 출처 통합 검색

## 출력 형식
검증 결과를 다음 JSON 형식으로 출력하세요:

```json
{
    "script_id": 0,
    "sources_validated": [
        {
            "source": {"type": "article", "pk": "id#xxx", "title": "..."},
            "status": "valid|partial|invalid|not_found",
            "confidence": 0.0-1.0,
            "explanation": "검증 결과 설명"
        }
    ],
    "text_claims": [
        {
            "claim": "스크립트에서 추출한 사실적 주장",
            "matched_source": {"type": "...", ...},
            "status": "valid|partial|invalid|no_source",
            "explanation": "주장과 출처 매칭 결과"
        }
    ],
    "overall_valid": true|false,
    "issues": ["발견된 문제점"]
}
```

검증할 스크립트 항목:
"""


class ScriptSourceValidator(Validator):
    """
    Validates that script content matches its source references.
    
    For each script item:
    1. Verifies that all source references exist
    2. Checks that the script text aligns with source content
    3. Validates factual claims against sources
    """
    
    def __init__(self):
        self._article_tool: Optional[ArticleSourceTool] = None
        self._event_tool: Optional[EventSourceTool] = None
        self._briefing_tool: Optional[BriefingScriptSourceTool] = None
    
    @property
    def validator_type(self) -> str:
        return "script_source"
    
    def set_article_tool(self, tool: ArticleSourceTool) -> None:
        """Set the article source tool for validation."""
        self._article_tool = tool
    
    def set_event_tool(self, tool: EventSourceTool) -> None:
        """Set the event source tool for validation."""
        self._event_tool = tool
    
    def set_briefing_tool(self, tool: BriefingScriptSourceTool) -> None:
        """Set the briefing script source tool for validation."""
        self._briefing_tool = tool
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """
        Validate a briefing script.
        
        Args:
            script: JSON string of the briefing script
            source_tools: Dictionary of registered source tools
            **kwargs: Additional parameters
            
        Returns:
            ValidationResult with validation outcomes
        """
        script_id = kwargs.get("script_id", "unknown")
        result = ValidationResult(script_id=script_id)
        
        # Check if this looks like JSON (skip validation for text/markdown scripts)
        script_stripped = script.strip()
        if not (script_stripped.startswith("{") or script_stripped.startswith("[")):
            # This is not a JSON script, skip this validator
            result.summary = "스크립트가 JSON 형식이 아니므로 출처 검증을 건너뜁니다."
            result.overall_valid = True  # Not applicable, so don't fail
            return result
        
        # Parse script
        try:
            briefing = BriefingScript.from_json(script)
        except json.JSONDecodeError as e:
            # JSON-like but invalid - this is an actual error
            result.errors.append(f"Failed to parse script JSON: {e}")
            result.overall_valid = False
            return result
        
        # Get source tools
        article_tool = self._article_tool or source_tools.get("article")
        event_tool = self._event_tool or source_tools.get("event")
        briefing_tool = self._briefing_tool or source_tools.get("briefing_script")
        
        # Validate each script item with sources
        for script_item in briefing.scripts:
            if not script_item.sources:
                # No sources to validate for this item
                continue
            
            for source in script_item.sources:
                match = self._validate_source(
                    script_item,
                    source,
                    article_tool,
                    event_tool,
                    briefing_tool,
                )
                result.source_matches.append(match)
                result.total_claims += 1
                
                if match.status == ValidationStatus.VALID:
                    result.valid_claims += 1
                elif match.status == ValidationStatus.INVALID:
                    result.invalid_claims += 1
                elif match.status == ValidationStatus.NOT_FOUND:
                    result.not_found_claims += 1
        
        # Determine overall validity
        result.overall_valid = (
            result.invalid_claims == 0 and
            result.not_found_claims <= result.total_claims * 0.1  # Allow up to 10% not found
        )
        
        # Generate summary
        result.summary = self._generate_summary(briefing, result)
        
        return result
    
    def _validate_source(
        self,
        script_item: ScriptItem,
        source: ScriptSource,
        article_tool: Optional[ArticleSourceTool],
        event_tool: Optional[EventSourceTool],
        briefing_tool: Optional[BriefingScriptSourceTool],
    ) -> SourceMatch:
        """Validate a single source reference."""
        
        claim = f"[Script {script_item.id}] {script_item.text[:100]}..."
        reference = json.dumps(source.to_dict(), ensure_ascii=False)
        
        if source.type == "article":
            if article_tool and source.pk:
                article = article_tool.search_by_pk(source.pk)
                if article:
                    # Check title match
                    if source.title and source.title.lower() in article.get("title", "").lower():
                        return SourceMatch(
                            claim=claim,
                            source_type="article",
                            source_reference=reference,
                            source_data=article,
                            status=ValidationStatus.VALID,
                            confidence=0.95,
                            explanation=f"Article verified: {article.get('title', '')[:60]}"
                        )
                    else:
                        return SourceMatch(
                            claim=claim,
                            source_type="article",
                            source_reference=reference,
                            source_data=article,
                            status=ValidationStatus.PARTIAL,
                            confidence=0.7,
                            explanation=f"Article found but title may differ"
                        )
                else:
                    return SourceMatch(
                        claim=claim,
                        source_type="article",
                        source_reference=reference,
                        status=ValidationStatus.NOT_FOUND,
                        explanation=f"Article not found: {source.pk}"
                    )
            elif briefing_tool:
                # Use briefing tool for validation
                return briefing_tool.validate_claim(claim, reference)
            else:
                return SourceMatch(
                    claim=claim,
                    source_type="article",
                    source_reference=reference,
                    status=ValidationStatus.ERROR,
                    explanation="No article source tool available"
                )
        
        elif source.type == "event":
            if event_tool and source.id:
                event = event_tool.search_by_id(source.id)
                if event:
                    return SourceMatch(
                        claim=claim,
                        source_type="event",
                        source_reference=reference,
                        source_data=event,
                        status=ValidationStatus.VALID,
                        confidence=0.95,
                        explanation=f"Event verified: {event.get('title', '')} on {source.date}"
                    )
                else:
                    return SourceMatch(
                        claim=claim,
                        source_type="event",
                        source_reference=reference,
                        status=ValidationStatus.NOT_FOUND,
                        explanation=f"Event not found: id={source.id}"
                    )
            elif briefing_tool:
                return briefing_tool.validate_claim(claim, reference)
            else:
                return SourceMatch(
                    claim=claim,
                    source_type="event",
                    source_reference=reference,
                    status=ValidationStatus.ERROR,
                    explanation="No event source tool available"
                )
        
        elif source.type == "chart":
            # Chart validation - we can only verify the ticker is valid
            # Full price validation would require market data API
            return SourceMatch(
                claim=claim,
                source_type="chart",
                source_reference=reference,
                status=ValidationStatus.PARTIAL,
                confidence=0.5,
                explanation=f"Chart source: {source.ticker} ({source.start_date} to {source.end_date}). "
                           f"Price validation requires market data API."
            )
        
        else:
            return SourceMatch(
                claim=claim,
                source_type=source.type,
                source_reference=reference,
                status=ValidationStatus.ERROR,
                explanation=f"Unknown source type: {source.type}"
            )
    
    def _generate_summary(self, briefing: BriefingScript, result: ValidationResult) -> str:
        """Generate a summary of validation results."""
        lines = []
        
        lines.append(f"📅 스크립트 날짜: {briefing.date}")
        lines.append(f"📝 요약: {briefing.nutshell}")
        lines.append("")
        
        if result.total_claims > 0:
            valid_pct = (result.valid_claims / result.total_claims) * 100
            lines.append(f"📊 출처 검증: {result.valid_claims}/{result.total_claims} ({valid_pct:.1f}%) 확인됨")
            
            if result.invalid_claims > 0:
                lines.append(f"  ⚠️ 불일치: {result.invalid_claims}건")
            if result.not_found_claims > 0:
                lines.append(f"  ❓ 미확인: {result.not_found_claims}건")
        
        # Count by source type
        type_counts = {}
        for match in result.source_matches:
            st = match.source_type
            if st not in type_counts:
                type_counts[st] = {"valid": 0, "invalid": 0, "not_found": 0, "partial": 0}
            if match.status == ValidationStatus.VALID:
                type_counts[st]["valid"] += 1
            elif match.status == ValidationStatus.INVALID:
                type_counts[st]["invalid"] += 1
            elif match.status == ValidationStatus.NOT_FOUND:
                type_counts[st]["not_found"] += 1
            elif match.status == ValidationStatus.PARTIAL:
                type_counts[st]["partial"] += 1
        
        if type_counts:
            lines.append("")
            lines.append("📋 출처 유형별:")
            for st, counts in type_counts.items():
                total = sum(counts.values())
                lines.append(f"  - {st}: {counts['valid']}/{total} 확인")
        
        # Overall
        lines.append("")
        overall_emoji = "✅" if result.overall_valid else "❌"
        lines.append(f"전체 결과: {overall_emoji} {'통과' if result.overall_valid else '수정 필요'}")
        
        return "\n".join(lines)


# =============================================================================
# Script Content Validator (uses LLM to check text vs sources)
# =============================================================================

SCRIPT_CONTENT_VALIDATOR_PROMPT = """당신은 브리핑 스크립트의 내용 정확성을 검증하는 AI 에이전트입니다.

## 역할
스크립트의 텍스트 내용이 인용된 출처의 정보와 일치하는지 상세히 검증합니다.

## 검증 기준
1. **사실 일치**: 스크립트에서 언급된 수치, 날짜, 이름이 출처와 일치하는가?
2. **맥락 정확성**: 출처의 내용을 올바른 맥락에서 인용했는가?
3. **과장/축소 없음**: 출처의 정보를 과장하거나 축소하지 않았는가?
4. **인과관계**: 언급된 인과관계가 출처에 근거하는가?

## 대상 청중
경제 뉴스와 주식 시장에 관심 있는 투자자

## 출력 형식
```json
{
    "content_validation": [
        {
            "script_id": 0,
            "text_excerpt": "검증된 텍스트 일부",
            "claims": [
                {
                    "claim": "추출된 사실적 주장",
                    "source_support": "출처에서 이를 뒷받침하는 내용",
                    "status": "supported|unsupported|exaggerated|misinterpreted",
                    "explanation": "상세 설명"
                }
            ]
        }
    ],
    "audience_fitness": {
        "rating": "excellent|good|fair|poor",
        "feedback": "대상 적합성 피드백"
    },
    "overall_assessment": "전체 평가 요약"
}
```
"""


class ScriptContentValidator(Validator):
    """
    Uses LLM to validate that script content accurately reflects sources.
    
    This validator:
    1. Extracts factual claims from script text
    2. Compares claims against source data (articles, events)
    3. Checks for accuracy, exaggeration, misinterpretation
    4. Evaluates audience fitness
    """
    
    @property
    def validator_type(self) -> str:
        return "script_content"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate script content using LLM."""
        script_id = kwargs.get("script_id", "unknown")
        result = ValidationResult(script_id=script_id)
        
        # Check if this looks like JSON (skip validation for text/markdown scripts)
        script_stripped = script.strip()
        if not (script_stripped.startswith("{") or script_stripped.startswith("[")):
            # This is not a JSON script, skip this validator
            result.summary = "스크립트가 JSON 형식이 아니므로 내용 검증을 건너뜁니다."
            result.overall_valid = True  # Not applicable, so don't fail
            return result
        
        # Parse script
        try:
            briefing = BriefingScript.from_json(script)
        except json.JSONDecodeError as e:
            # JSON-like but invalid - this is an actual error
            result.errors.append(f"Failed to parse script JSON: {e}")
            result.overall_valid = False
            return result
        
        # Build validation context
        # For each script item with sources, prepare the data
        validation_items = []
        for script_item in briefing.scripts:
            if script_item.sources:
                sources_data = self._gather_source_data(script_item.sources, source_tools)
                validation_items.append({
                    "script_id": script_item.id,
                    "speaker": script_item.speaker,
                    "text": script_item.text,
                    "sources": sources_data,
                })
        
        if not validation_items:
            result.summary = "스크립트에 검증할 출처가 없습니다."
            result.overall_valid = True
            return result
        
        # Call LLM for content validation
        try:
            llm_result = self._validate_with_llm(validation_items)
            
            # Parse LLM result
            content_validation = llm_result.get("content_validation", [])
            
            for item in content_validation:
                for claim_data in item.get("claims", []):
                    status = self._map_status(claim_data.get("status", "unsupported"))
                    
                    result.source_matches.append(SourceMatch(
                        claim=claim_data.get("claim", ""),
                        source_type="content",
                        source_reference=claim_data.get("source_support", ""),
                        status=status,
                        confidence=0.8 if status == ValidationStatus.VALID else 0.5,
                        explanation=claim_data.get("explanation", ""),
                    ))
                    
                    result.total_claims += 1
                    if status == ValidationStatus.VALID:
                        result.valid_claims += 1
                    elif status == ValidationStatus.INVALID:
                        result.invalid_claims += 1
            
            # Audience fitness
            audience_data = llm_result.get("audience_fitness", {})
            result.audience_fitness = self._map_fitness(audience_data.get("rating", "good"))
            result.audience_feedback = audience_data.get("feedback", "")
            
            result.summary = llm_result.get("overall_assessment", "")
            
        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            result.errors.append(str(e))
        
        # Determine overall validity
        result.overall_valid = (
            result.invalid_claims == 0 and
            result.audience_fitness in [AudienceFitness.EXCELLENT, AudienceFitness.GOOD]
        )
        
        return result
    
    def _gather_source_data(
        self,
        sources: List[ScriptSource],
        source_tools: Dict[str, SourceTool],
    ) -> List[Dict[str, Any]]:
        """Gather actual source data for validation."""
        sources_data = []
        
        article_tool = source_tools.get("article")
        event_tool = source_tools.get("event")
        
        for source in sources:
            source_dict = source.to_dict()
            
            if source.type == "article" and article_tool and source.pk:
                article = article_tool.search_by_pk(source.pk) if hasattr(article_tool, "search_by_pk") else None
                if article:
                    source_dict["data"] = article
            
            elif source.type == "event" and event_tool and source.id:
                event = event_tool.search_by_id(source.id) if hasattr(event_tool, "search_by_id") else None
                if event:
                    source_dict["data"] = event
            
            sources_data.append(source_dict)
        
        return sources_data
    
    def _validate_with_llm(self, validation_items: List[Dict]) -> Dict[str, Any]:
        """Call LLM to validate content."""
        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        
        user_message = f"""다음 스크립트 항목들을 검증해주세요:

{json.dumps(validation_items, ensure_ascii=False, indent=2)}

각 스크립트의 텍스트 내용이 인용된 출처(sources)와 일치하는지 확인하고,
출처에 근거하지 않은 주장이 있는지 검토해주세요."""
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SCRIPT_CONTENT_VALIDATOR_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        
        response_text = response.choices[0].message.content or ""
        
        # Parse JSON from response
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            return {"overall_assessment": response_text}
    
    def _map_status(self, status_str: str) -> ValidationStatus:
        """Map status string to ValidationStatus."""
        mapping = {
            "supported": ValidationStatus.VALID,
            "valid": ValidationStatus.VALID,
            "unsupported": ValidationStatus.INVALID,
            "invalid": ValidationStatus.INVALID,
            "exaggerated": ValidationStatus.PARTIAL,
            "misinterpreted": ValidationStatus.PARTIAL,
            "partial": ValidationStatus.PARTIAL,
        }
        return mapping.get(status_str.lower(), ValidationStatus.NOT_FOUND)
    
    def _map_fitness(self, fitness_str: str) -> AudienceFitness:
        """Map fitness string to AudienceFitness."""
        mapping = {
            "excellent": AudienceFitness.EXCELLENT,
            "good": AudienceFitness.GOOD,
            "fair": AudienceFitness.FAIR,
            "poor": AudienceFitness.POOR,
        }
        return mapping.get(fitness_str.lower(), AudienceFitness.GOOD)


# =============================================================================
# Convenience Functions
# =============================================================================

def validate_briefing_script(
    script_json: str,
    articles_path: Optional[Path] = None,
    events_path: Optional[Path] = None,
    validate_content: bool = True,
) -> ValidationResult:
    """
    Convenience function to validate a briefing script.
    
    Args:
        script_json: JSON string of the briefing script
        articles_path: Path to articles JSON file
        events_path: Path to events JSON file
        validate_content: Whether to also validate content with LLM
        
    Returns:
        Combined ValidationResult
    """
    from validation_agent.base import ValidationAgent
    
    # Create agent
    agent = ValidationAgent()
    
    # Register source tools
    if articles_path:
        article_tool = ArticleSourceTool()
        article_tool.load_sources(articles_path)
        agent.register_source_tool(article_tool)
    
    if events_path:
        event_tool = EventSourceTool()
        event_tool.load_sources(events_path)
        agent.register_source_tool(event_tool)
    
    briefing_tool = BriefingScriptSourceTool()
    agent.register_source_tool(briefing_tool)
    
    # Register validators
    source_validator = ScriptSourceValidator()
    agent.register_validator(source_validator)
    
    if validate_content:
        content_validator = ScriptContentValidator()
        agent.register_validator(content_validator)
    
    # Validate
    return agent.validate(script_json)

