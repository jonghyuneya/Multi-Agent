"""
Validators for the Validation Agent.

This module provides concrete implementations of Validator for different
validation types:
1. FactValidator - Validates factual claims against source data
2. AudienceValidator - Checks content fitness for target audience
3. CitationValidator - Ensures all claims have proper citations

Uses LLM with tool calling for intelligent validation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from validation_agent.base import (
    Validator,
    ValidationResult,
    SourceMatch,
    ValidationStatus,
    AudienceFitness,
    SourceTool,
)

logger = logging.getLogger(__name__)


# =============================================================================
# LLM Helper
# =============================================================================

def call_llm_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    source_tools: Dict[str, SourceTool],
    max_tool_iterations: int = 10,
    model: str = None,
) -> str:
    """
    Call LLM with tool support, handling tool calls iteratively.
    
    Args:
        messages: Conversation messages
        tools: Tool definitions for function calling
        source_tools: Registered source tools for execution
        max_tool_iterations: Maximum number of tool call iterations
        model: LLM model to use
        
    Returns:
        Final LLM response text
    """
    client = OpenAI()
    model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
    
    for iteration in range(max_tool_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            temperature=0.1,  # Low temperature for factual validation
        )
        
        assistant_message = response.choices[0].message
        messages.append(assistant_message.model_dump())
        
        # Check for tool calls
        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                # Execute tool
                result = execute_source_tool(tool_name, tool_args, source_tools)
                
                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            # No more tool calls, return response
            return assistant_message.content or ""
    
    logger.warning(f"Max tool iterations ({max_tool_iterations}) reached")
    return messages[-1].get("content", "") if messages else ""


def execute_source_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    source_tools: Dict[str, SourceTool],
) -> Dict[str, Any]:
    """
    Execute a source tool call.
    
    Maps tool names to source types:
    - search_calendar_events -> calendar_events
    - search_macro_data -> macro_data
    - search_fomc_events -> fomc_events
    - search_news_data -> news_data
    """
    # Map tool names to source types
    tool_to_source = {
        "search_calendar_events": "calendar_events",
        "search_macro_data": "macro_data",
        "search_fomc_events": "fomc_events",
        "search_news_data": "news_data",
    }
    
    source_type = tool_to_source.get(tool_name)
    
    if not source_type:
        # Try extracting from tool name pattern "search_{source_type}"
        if tool_name.startswith("search_"):
            source_type = tool_name[7:]
    
    if not source_type or source_type not in source_tools:
        return {"error": f"Unknown tool or source: {tool_name}"}
    
    tool = source_tools[source_type]
    query = arguments.get("query", "")
    
    try:
        results = tool.search(query)
        return {
            "source_type": source_type,
            "query": query,
            "results": results[:10],  # Limit results
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"Error executing {tool_name}: {e}")
        return {"error": str(e)}


# =============================================================================
# Fact Validator
# =============================================================================

FACT_VALIDATOR_PROMPT = """당신은 AI 생성 스크립트의 사실 정확성을 검증하는 검증 에이전트입니다.

## 역할
스크립트에 포함된 모든 사실적 주장(claim)이 원본 데이터와 일치하는지 확인합니다.

## 검증 기준
1. **수치 정확성**: 숫자, 백분율, 날짜가 출처 데이터와 정확히 일치하는가?
2. **맥락 정확성**: 정보가 올바른 맥락에서 사용되었는가?
3. **해석 정확성**: 데이터 해석이 합리적인가?
4. **출처 존재**: 인용된 출처가 실제로 존재하는가?

## 도구 사용
다음 도구를 사용하여 사실을 검증하세요:
- search_calendar_events: 경제 캘린더 이벤트 검색
- search_macro_data: 거시경제 지표 검색
- search_fomc_events: FOMC 관련 문서 검색
- search_news_data: 뉴스 기사 검색

## 출력 형식
검증 결과를 다음 JSON 형식으로 출력하세요:

```json
{
    "claims": [
        {
            "claim_text": "스크립트에서 추출한 주장",
            "source_type": "calendar_events|macro_data|fomc_events|news_data",
            "reference": "인용된 출처 정보",
            "status": "valid|partial|invalid|not_found",
            "confidence": 0.0-1.0,
            "explanation": "검증 결과 설명",
            "suggested_correction": "수정 제안 (invalid인 경우)"
        }
    ],
    "summary": "전체 검증 요약"
}
```

검증할 스크립트:
"""

class FactValidator(Validator):
    """
    Validates factual claims in scripts against source data.
    
    Uses LLM with tool calling to:
    1. Extract claims from the script
    2. Identify the source type for each claim
    3. Search source data to verify claims
    4. Report validation results
    """
    
    @property
    def validator_type(self) -> str:
        return "fact"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate factual claims in the script."""
        result = ValidationResult(script_id=kwargs.get("script_id", "unknown"))
        
        # Get tool definitions
        tools = [tool.get_tool_definition() for tool in source_tools.values()]
        
        # Build messages
        messages = [
            {"role": "system", "content": FACT_VALIDATOR_PROMPT},
            {"role": "user", "content": script},
        ]
        
        try:
            # Call LLM with tools
            response = call_llm_with_tools(messages, tools, source_tools)
            
            # Parse response
            validation_data = self._parse_validation_response(response)
            
            # Convert to ValidationResult
            for claim_data in validation_data.get("claims", []):
                status = self._map_status(claim_data.get("status", "not_found"))
                
                source_match = SourceMatch(
                    claim=claim_data.get("claim_text", ""),
                    source_type=claim_data.get("source_type", "unknown"),
                    source_reference=claim_data.get("reference", ""),
                    status=status,
                    confidence=claim_data.get("confidence", 0.0),
                    explanation=claim_data.get("explanation", ""),
                    suggested_correction=claim_data.get("suggested_correction"),
                )
                
                result.source_matches.append(source_match)
                result.total_claims += 1
                
                if status == ValidationStatus.VALID:
                    result.valid_claims += 1
                elif status == ValidationStatus.INVALID:
                    result.invalid_claims += 1
                elif status == ValidationStatus.NOT_FOUND:
                    result.not_found_claims += 1
            
            result.summary = validation_data.get("summary", "")
            
        except Exception as e:
            logger.error(f"FactValidator error: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _parse_validation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to extract validation data."""
        # Try to extract JSON from response
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try parsing entire response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Return empty if parsing fails
        logger.warning("Could not parse validation response as JSON")
        return {"claims": [], "summary": response}
    
    def _map_status(self, status_str: str) -> ValidationStatus:
        """Map status string to ValidationStatus enum."""
        mapping = {
            "valid": ValidationStatus.VALID,
            "partial": ValidationStatus.PARTIAL,
            "invalid": ValidationStatus.INVALID,
            "not_found": ValidationStatus.NOT_FOUND,
            "error": ValidationStatus.ERROR,
        }
        return mapping.get(status_str.lower(), ValidationStatus.NOT_FOUND)


# =============================================================================
# Audience Validator
# =============================================================================

AUDIENCE_VALIDATOR_PROMPT = """당신은 AI 생성 스크립트의 대상 적합성을 평가하는 검증 에이전트입니다.

## 대상 독자
경제 뉴스와 주식 시장에 관심이 있는 투자자들

## 평가 기준

### 1. 관련성 (Relevance)
- 내용이 경제/금융 뉴스와 관련이 있는가?
- 투자 결정에 도움이 되는 정보인가?
- 불필요하거나 관련 없는 내용이 포함되어 있는가?

### 2. 접근성 (Accessibility)
- 전문 용어가 적절히 설명되어 있는가?
- 일반 투자자도 이해할 수 있는 수준인가?
- 너무 기초적이거나 너무 전문적이지 않은가?

### 3. 실용성 (Actionability)
- 정보가 투자 판단에 도움이 되는가?
- 시장에 대한 통찰을 제공하는가?
- 단순 데이터 나열이 아닌 분석이 있는가?

### 4. 어조 (Tone)
- 전문적이면서도 친근한 어조인가?
- 과장되거나 선정적이지 않은가?
- 균형 잡힌 시각을 제공하는가?

### 5. 구조 (Structure)
- 논리적인 흐름으로 구성되어 있는가?
- 중요한 정보가 명확하게 전달되는가?
- 청취자가 따라가기 쉬운가?

## 출력 형식
평가 결과를 다음 JSON 형식으로 출력하세요:

```json
{
    "fitness": "excellent|good|fair|poor",
    "scores": {
        "relevance": 1-5,
        "accessibility": 1-5,
        "actionability": 1-5,
        "tone": 1-5,
        "structure": 1-5
    },
    "strengths": ["장점 1", "장점 2"],
    "improvements": ["개선점 1", "개선점 2"],
    "specific_issues": [
        {
            "location": "문제가 있는 부분 인용",
            "issue": "문제 설명",
            "suggestion": "개선 제안"
        }
    ],
    "summary": "전체 평가 요약"
}
```

평가할 스크립트:
"""

class AudienceValidator(Validator):
    """
    Validates content fitness for target audience.
    
    Evaluates:
    - Relevance to economic/financial news
    - Accessibility for general investors
    - Actionability of information
    - Professional but approachable tone
    - Logical structure and flow
    """
    
    @property
    def validator_type(self) -> str:
        return "audience"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate audience fitness of the script."""
        result = ValidationResult(script_id=kwargs.get("script_id", "unknown"))
        
        # Build messages (no tools needed for audience validation)
        messages = [
            {"role": "system", "content": AUDIENCE_VALIDATOR_PROMPT},
            {"role": "user", "content": script},
        ]
        
        try:
            client = OpenAI()
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
            )
            
            response_text = response.choices[0].message.content or ""
            
            # Parse response
            evaluation = self._parse_evaluation_response(response_text)
            
            # Map fitness
            fitness_str = evaluation.get("fitness", "good")
            result.audience_fitness = self._map_fitness(fitness_str)
            
            # Build feedback
            feedback_parts = []
            
            if evaluation.get("strengths"):
                feedback_parts.append("✅ 장점:\n" + "\n".join(f"  - {s}" for s in evaluation["strengths"]))
            
            if evaluation.get("improvements"):
                feedback_parts.append("⚠️ 개선점:\n" + "\n".join(f"  - {i}" for i in evaluation["improvements"]))
            
            if evaluation.get("specific_issues"):
                feedback_parts.append("📝 구체적 이슈:")
                for issue in evaluation["specific_issues"]:
                    feedback_parts.append(f"  위치: {issue.get('location', '?')}")
                    feedback_parts.append(f"  문제: {issue.get('issue', '?')}")
                    feedback_parts.append(f"  제안: {issue.get('suggestion', '?')}")
            
            result.audience_feedback = "\n\n".join(feedback_parts)
            result.summary = evaluation.get("summary", "")
            
        except Exception as e:
            logger.error(f"AudienceValidator error: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to extract evaluation data."""
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        return {"fitness": "good", "summary": response}
    
    def _map_fitness(self, fitness_str: str) -> AudienceFitness:
        """Map fitness string to AudienceFitness enum."""
        mapping = {
            "excellent": AudienceFitness.EXCELLENT,
            "good": AudienceFitness.GOOD,
            "fair": AudienceFitness.FAIR,
            "poor": AudienceFitness.POOR,
        }
        return mapping.get(fitness_str.lower(), AudienceFitness.GOOD)


# =============================================================================
# Citation Validator
# =============================================================================

CITATION_VALIDATOR_PROMPT = """당신은 AI 생성 스크립트의 인용 완전성을 검증하는 에이전트입니다.

## 역할
스크립트에 포함된 모든 사실적 주장에 적절한 출처 표기가 있는지 확인합니다.

## 인용이 필요한 정보 유형
1. **수치 데이터**: 경제 지표, 가격, 변동률 등
2. **이벤트 정보**: FOMC 결정, 경제 지표 발표 등
3. **인용문**: 연준 의장 발언, 분석가 코멘트 등
4. **뉴스 내용**: 특정 뉴스 기사 내용
5. **예측/전망**: 공식적인 예측이나 전망치

## 인용 형식
올바른 인용 형식: [REF: source_type | "인용문"]

예시:
- [REF: macro_data | "미국 CPI 3.0%"]
- [REF: fomc_events | "연준, 금리 동결 결정"]
- [REF: news_data | "애플, 신제품 발표"]

## 출력 형식
검증 결과를 다음 JSON 형식으로 출력하세요:

```json
{
    "citations_complete": true|false,
    "citation_count": 0,
    "claims_without_citation": [
        {
            "claim": "인용 없는 주장",
            "suggested_source_type": "calendar_events|macro_data|fomc_events|news_data",
            "reason": "인용이 필요한 이유"
        }
    ],
    "citation_issues": [
        {
            "citation": "문제가 있는 인용",
            "issue": "문제 설명",
            "suggestion": "개선 제안"
        }
    ],
    "summary": "전체 검증 요약"
}
```

검증할 스크립트:
"""

class CitationValidator(Validator):
    """
    Validates that all factual claims have proper citations.
    
    Checks:
    - All numerical data has citations
    - Event information has citations
    - Quotes are properly attributed
    - Citation format is correct
    """
    
    @property
    def validator_type(self) -> str:
        return "citation"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate citation completeness in the script."""
        result = ValidationResult(script_id=kwargs.get("script_id", "unknown"))
        
        # Build messages
        messages = [
            {"role": "system", "content": CITATION_VALIDATOR_PROMPT},
            {"role": "user", "content": script},
        ]
        
        try:
            client = OpenAI()
            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            
            response_text = response.choices[0].message.content or ""
            
            # Parse response
            validation_data = self._parse_citation_response(response_text)
            
            # Update result
            result.citations_complete = validation_data.get("citations_complete", True)
            
            # Extract missing citations
            for claim in validation_data.get("claims_without_citation", []):
                result.missing_citations.append(claim.get("claim", ""))
            
            result.summary = validation_data.get("summary", "")
            
        except Exception as e:
            logger.error(f"CitationValidator error: {e}")
            result.errors.append(str(e))
        
        return result
    
    def _parse_citation_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response to extract citation validation data."""
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        return {"citations_complete": True, "summary": response}

