"""
Investment Briefing Script Validator.

This module provides validators for validating investment briefing scripts
with embedded source references like SEC filings, news articles, and market data.

The investment briefing schema includes:
- ticker: Stock ticker symbol
- timestamp: When the briefing was generated
- rounds: List of debate rounds with fundamental, risk, growth, sentiment analysis
- conclusion: Final summary and recommendation
- sources: Dictionary with sec_filings, news_articles, market_data
- structured_conclusion: Structured recommendation output

Source types:
- sec_filings: SEC filings with form, filed_date, accession_number, file_path
- news_articles: News with id, title, published_at, source
- market_data: Current price, P/E ratio, market cap, etc.
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

logger = logging.getLogger(__name__)


# =============================================================================
# Data Structures for Investment Briefing
# =============================================================================

@dataclass
class SECFiling:
    """Represents an SEC filing source."""
    form: str
    filed_date: str
    reporting_for: str
    accession_number: str
    file_path: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SECFiling":
        return cls(
            form=data.get("form", ""),
            filed_date=data.get("filed_date", ""),
            reporting_for=data.get("reporting_for", ""),
            accession_number=data.get("accession_number", ""),
            file_path=data.get("file_path", ""),
        )
    
    def to_reference(self) -> str:
        return f"{self.form} ({self.filed_date}) - {self.accession_number}"


@dataclass
class NewsArticle:
    """Represents a news article source."""
    id: int
    title: str
    published_at: str
    source: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NewsArticle":
        return cls(
            id=data.get("id", 0),
            title=data.get("title", ""),
            published_at=data.get("published_at", ""),
            source=data.get("source", ""),
        )
    
    def to_reference(self) -> str:
        return f"[{self.id}] \"{self.title}\" - {self.source}"


@dataclass
class MarketData:
    """Represents market data source."""
    source: str
    fetched_at: str
    current_price: float
    pe_ratio: float
    market_cap: float
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketData":
        return cls(
            source=data.get("source", ""),
            fetched_at=data.get("fetched_at", ""),
            current_price=data.get("current_price", 0.0),
            pe_ratio=data.get("pe_ratio", 0.0),
            market_cap=data.get("market_cap", 0.0),
        )


@dataclass
class InvestmentBriefingSources:
    """Sources for an investment briefing."""
    ticker: str
    collected_at: str
    sec_filings: List[SECFiling]
    news_articles: List[NewsArticle]
    market_data: Optional[MarketData] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestmentBriefingSources":
        return cls(
            ticker=data.get("ticker", ""),
            collected_at=data.get("collected_at", ""),
            sec_filings=[SECFiling.from_dict(f) for f in data.get("sec_filings", [])],
            news_articles=[NewsArticle.from_dict(a) for a in data.get("news_articles", [])],
            market_data=MarketData.from_dict(data["market_data"]) if data.get("market_data") else None,
        )
    
    def get_news_by_id(self, news_id: int) -> Optional[NewsArticle]:
        """Get a news article by its ID."""
        for article in self.news_articles:
            if article.id == news_id:
                return article
        return None
    
    def get_sec_filing_by_form(self, form: str) -> List[SECFiling]:
        """Get SEC filings by form type."""
        return [f for f in self.sec_filings if f.form == form]
    
    def get_sec_filing_by_date(self, date: str) -> List[SECFiling]:
        """Get SEC filings by filed date or reporting_for date."""
        return [f for f in self.sec_filings if f.filed_date == date or f.reporting_for == date]


@dataclass
class InvestmentBriefing:
    """Complete investment briefing structure."""
    ticker: str
    timestamp: str
    rounds: List[Dict[str, Any]]
    conclusion: str
    readable_summary: str
    debate_transcript: str
    sources: InvestmentBriefingSources
    structured_conclusion: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestmentBriefing":
        sources_data = data.get("sources", {})
        return cls(
            ticker=data.get("ticker", ""),
            timestamp=data.get("timestamp", ""),
            rounds=data.get("rounds", []),
            conclusion=data.get("conclusion", ""),
            readable_summary=data.get("readable_summary", ""),
            debate_transcript=data.get("debate_transcript", ""),
            sources=InvestmentBriefingSources.from_dict(sources_data),
            structured_conclusion=data.get("structured_conclusion", {}),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "InvestmentBriefing":
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @classmethod
    def from_file(cls, path: Path) -> "InvestmentBriefing":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def get_all_text_content(self) -> str:
        """Get all text content from the briefing for analysis."""
        content_parts = []
        
        # Add rounds content
        for i, round_data in enumerate(self.rounds):
            content_parts.append(f"=== Round {i + 1} ===")
            for role in ["fundamental", "risk", "growth", "sentiment"]:
                if role in round_data:
                    content_parts.append(f"[{role.upper()}]")
                    content_parts.append(round_data[role])
        
        # Add conclusion
        content_parts.append("=== CONCLUSION ===")
        content_parts.append(self.conclusion)
        
        return "\n\n".join(content_parts)
    
    def extract_cited_news_ids(self) -> List[int]:
        """
        Extract news article IDs cited in the briefing text.
        
        Looks for patterns like:
        - "뉴스 ID 7"
        - "기사 ID 8"
        - "2025-12-23 뉴스"
        - "8번 뉴스"
        """
        text = self.get_all_text_content()
        
        # Pattern: "뉴스 ID 7" or "ID 7" or "id 7"
        id_pattern = r'(?:뉴스|기사|news|article)?\s*(?:ID|id|Id)\s*(\d+)'
        
        # Pattern: "7번 뉴스" or "7번 기사"
        num_pattern = r'(\d+)번\s*(?:뉴스|기사)'
        
        ids = set()
        for match in re.finditer(id_pattern, text, re.IGNORECASE):
            ids.add(int(match.group(1)))
        for match in re.finditer(num_pattern, text):
            ids.add(int(match.group(1)))
        
        return sorted(ids)
    
    def extract_cited_sec_dates(self) -> List[str]:
        """
        Extract SEC filing dates cited in the briefing.
        
        Looks for patterns like:
        - "2025-10-30 제출된 10-Q"
        - "10-Q 공시(2025-10-30)"
        """
        text = self.get_all_text_content()
        
        # Pattern: YYYY-MM-DD with context
        date_pattern = r'(\d{4}-\d{2}-\d{2})\s*(?:제출|공시|기준)'
        
        dates = set()
        for match in re.finditer(date_pattern, text):
            dates.add(match.group(1))
        
        return sorted(dates)


# =============================================================================
# Investment Briefing Source Validator
# =============================================================================

class InvestmentBriefingSourceValidator(Validator):
    """
    Validates that an investment briefing correctly cites its sources.
    
    Checks:
    1. SEC filings cited in the text actually exist in sources
    2. News articles cited by ID exist in sources
    3. Market data values (price, P/E) match sources
    """
    
    @property
    def validator_type(self) -> str:
        return "investment_briefing_source"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate investment briefing sources."""
        script_id = kwargs.get("script_id", "unknown")
        result = ValidationResult(script_id=script_id)
        
        # Check if this looks like JSON
        script_stripped = script.strip()
        if not (script_stripped.startswith("{") or script_stripped.startswith("[")):
            result.summary = "스크립트가 JSON 형식이 아니므로 투자 브리핑 출처 검증을 건너뜁니다."
            result.overall_valid = True
            return result
        
        # Parse script
        try:
            briefing = InvestmentBriefing.from_json(script)
        except (json.JSONDecodeError, KeyError) as e:
            # Check if it's a different JSON format (closing_briefing script)
            try:
                data = json.loads(script)
                # If it has "scripts" and "chapter" keys, it's a closing_briefing format
                if "scripts" in data or "chapter" in data or "nutshell" in data:
                    result.summary = "이것은 투자 브리핑이 아닌 다른 형식의 JSON입니다. 검증을 건너뜁니다."
                    result.overall_valid = True
                    return result
                # If it doesn't have "ticker" or "rounds", skip
                if "ticker" not in data or "rounds" not in data:
                    result.summary = "투자 브리핑 형식이 아닙니다. 검증을 건너뜁니다."
                    result.overall_valid = True
                    return result
            except:
                pass
            
            result.errors.append(f"투자 브리핑 JSON 파싱 실패: {e}")
            result.overall_valid = False
            return result
        
        # Validate sources
        issues = []
        
        # 1. Check cited news articles
        cited_news_ids = briefing.extract_cited_news_ids()
        available_news_ids = [a.id for a in briefing.sources.news_articles]
        
        for news_id in cited_news_ids:
            if news_id in available_news_ids:
                article = briefing.sources.get_news_by_id(news_id)
                result.source_matches.append(SourceMatch(
                    claim=f"뉴스 ID {news_id} 인용",
                    source_type="news_article",
                    source_reference=article.to_reference() if article else "",
                    source_data={"id": news_id, "title": article.title if article else ""},
                    status=ValidationStatus.VALID,
                    confidence=0.95,
                    explanation=f"뉴스 기사 확인됨: {article.title[:60] if article else 'N/A'}"
                ))
                result.valid_claims += 1
            else:
                result.source_matches.append(SourceMatch(
                    claim=f"뉴스 ID {news_id} 인용",
                    source_type="news_article",
                    source_reference=f"ID {news_id}",
                    status=ValidationStatus.NOT_FOUND,
                    explanation=f"뉴스 ID {news_id}가 sources.news_articles에 없습니다. 사용 가능한 ID: {available_news_ids}"
                ))
                result.not_found_claims += 1
                issues.append(f"뉴스 ID {news_id} 미확인")
            result.total_claims += 1
        
        # 2. Check cited SEC filings
        cited_sec_dates = briefing.extract_cited_sec_dates()
        # Include both filed_date and reporting_for dates
        available_sec_dates = set()
        for f in briefing.sources.sec_filings:
            available_sec_dates.add(f.filed_date)
            available_sec_dates.add(f.reporting_for)
        available_sec_dates = list(available_sec_dates)
        
        for sec_date in cited_sec_dates:
            if sec_date in available_sec_dates:
                filings = briefing.sources.get_sec_filing_by_date(sec_date)
                filing = filings[0] if filings else None
                result.source_matches.append(SourceMatch(
                    claim=f"SEC 공시 {sec_date} 인용",
                    source_type="sec_filing",
                    source_reference=filing.to_reference() if filing else "",
                    source_data={"filed_date": sec_date, "form": filing.form if filing else ""},
                    status=ValidationStatus.VALID,
                    confidence=0.95,
                    explanation=f"SEC 공시 확인됨: {filing.form if filing else 'N/A'} ({sec_date})"
                ))
                result.valid_claims += 1
            else:
                result.source_matches.append(SourceMatch(
                    claim=f"SEC 공시 {sec_date} 인용",
                    source_type="sec_filing",
                    source_reference=sec_date,
                    status=ValidationStatus.NOT_FOUND,
                    explanation=f"SEC 공시 날짜 {sec_date}가 sources.sec_filings에 없습니다"
                ))
                result.not_found_claims += 1
                issues.append(f"SEC 공시 {sec_date} 미확인")
            result.total_claims += 1
        
        # 3. Check market data
        if briefing.sources.market_data:
            md = briefing.sources.market_data
            text = briefing.get_all_text_content()
            
            # Check price mention
            price_str = f"{md.current_price:.2f}"
            if price_str in text or str(int(md.current_price)) in text:
                result.source_matches.append(SourceMatch(
                    claim=f"현재 주가 ${md.current_price:.2f} 인용",
                    source_type="market_data",
                    source_reference=f"current_price: {md.current_price}",
                    source_data={"current_price": md.current_price},
                    status=ValidationStatus.VALID,
                    confidence=0.9,
                    explanation=f"주가 확인됨: ${md.current_price:.2f}"
                ))
                result.valid_claims += 1
                result.total_claims += 1
            
            # Check P/E mention
            pe_str = f"{md.pe_ratio:.2f}"
            if pe_str in text or f"P/E {int(md.pe_ratio)}" in text or f"PER {int(md.pe_ratio)}" in text:
                result.source_matches.append(SourceMatch(
                    claim=f"P/E 비율 {md.pe_ratio:.2f} 인용",
                    source_type="market_data",
                    source_reference=f"pe_ratio: {md.pe_ratio}",
                    source_data={"pe_ratio": md.pe_ratio},
                    status=ValidationStatus.VALID,
                    confidence=0.9,
                    explanation=f"P/E 비율 확인됨: {md.pe_ratio:.2f}"
                ))
                result.valid_claims += 1
                result.total_claims += 1
        
        # Determine overall validity
        result.overall_valid = len(issues) == 0
        
        # Generate summary
        summary_lines = [
            f"📊 티커: {briefing.ticker}",
            f"📅 생성 시간: {briefing.timestamp}",
            "",
            f"📰 뉴스 기사: {len(briefing.sources.news_articles)}개 제공됨",
            f"   - 인용됨: {len(cited_news_ids)}개 (ID: {cited_news_ids})",
            f"📋 SEC 공시: {len(briefing.sources.sec_filings)}개 제공됨",
            f"   - 인용됨: {len(cited_sec_dates)}개 (날짜: {cited_sec_dates})",
            "",
            f"📊 검증 결과: {result.valid_claims}/{result.total_claims} 확인됨",
        ]
        
        if issues:
            summary_lines.append("")
            summary_lines.append("⚠️ 문제점:")
            for issue in issues:
                summary_lines.append(f"  - {issue}")
        
        summary_lines.append("")
        overall_emoji = "✅" if result.overall_valid else "❌"
        summary_lines.append(f"전체 결과: {overall_emoji} {'통과' if result.overall_valid else '수정 필요'}")
        
        result.summary = "\n".join(summary_lines)
        
        return result


# =============================================================================
# Investment Briefing Content Validator (uses LLM)
# =============================================================================

INVESTMENT_BRIEFING_VALIDATOR_PROMPT = """당신은 투자 브리핑 스크립트의 내용 정확성을 검증하는 AI 에이전트입니다.

## 역할
브리핑 분석 내용이 제공된 출처(SEC 공시, 뉴스 기사, 시장 데이터)와 일치하는지 검증합니다.

## 검증 기준
1. **사실 정확성**: 언급된 수치(주가, P/E, 마진 등)가 출처와 일치하는가?
2. **인용 정확성**: 뉴스나 SEC 공시를 인용할 때 내용이 정확한가?
3. **날짜 정확성**: 공시 날짜, 뉴스 발행일이 정확한가?
4. **해석 타당성**: 데이터에서 도출한 해석이 논리적인가?

## 출력 형식
```json
{
    "source_verification": [
        {
            "source_type": "sec_filing|news_article|market_data",
            "source_id": "id or date",
            "cited_content": "브리핑에서 인용된 내용",
            "matches_source": true|false,
            "explanation": "검증 설명"
        }
    ],
    "factual_claims": [
        {
            "claim": "추출된 사실적 주장",
            "source_support": "이를 뒷받침하는 출처",
            "status": "verified|unverified|incorrect",
            "explanation": "설명"
        }
    ],
    "overall_accuracy_score": 0.0-1.0,
    "summary": "전체 검증 요약"
}
```
"""


class InvestmentBriefingContentValidator(Validator):
    """
    Uses LLM to validate investment briefing content against sources.
    """
    
    @property
    def validator_type(self) -> str:
        return "investment_briefing_content"
    
    def validate(
        self,
        script: str,
        source_tools: Dict[str, SourceTool],
        **kwargs
    ) -> ValidationResult:
        """Validate investment briefing content using LLM."""
        script_id = kwargs.get("script_id", "unknown")
        result = ValidationResult(script_id=script_id)
        
        # Check if this looks like JSON
        script_stripped = script.strip()
        if not (script_stripped.startswith("{") or script_stripped.startswith("[")):
            result.summary = "스크립트가 JSON 형식이 아니므로 내용 검증을 건너뜁니다."
            result.overall_valid = True
            return result
        
        # Parse script
        try:
            briefing = InvestmentBriefing.from_json(script)
        except (json.JSONDecodeError, KeyError) as e:
            # Check if it's a different JSON format
            try:
                data = json.loads(script)
                if "ticker" not in data or "rounds" not in data:
                    result.summary = "투자 브리핑 형식이 아닙니다. 검증을 건너뜁니다."
                    result.overall_valid = True
                    return result
            except:
                pass
            
            result.errors.append(f"투자 브리핑 JSON 파싱 실패: {e}")
            result.overall_valid = False
            return result
        
        # Prepare validation context
        validation_context = {
            "ticker": briefing.ticker,
            "sources": {
                "sec_filings": [
                    {
                        "form": f.form,
                        "filed_date": f.filed_date,
                        "reporting_for": f.reporting_for,
                    }
                    for f in briefing.sources.sec_filings
                ],
                "news_articles": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "published_at": a.published_at,
                    }
                    for a in briefing.sources.news_articles
                ],
                "market_data": {
                    "current_price": briefing.sources.market_data.current_price,
                    "pe_ratio": briefing.sources.market_data.pe_ratio,
                    "market_cap": briefing.sources.market_data.market_cap,
                } if briefing.sources.market_data else None,
            },
            "content_to_validate": {
                "conclusion": briefing.conclusion[:3000],  # Limit for API
                "readable_summary": briefing.readable_summary,
            },
        }
        
        try:
            llm_result = self._validate_with_llm(validation_context)
            
            # Process LLM result
            source_verifications = llm_result.get("source_verification", [])
            for sv in source_verifications:
                status = ValidationStatus.VALID if sv.get("matches_source") else ValidationStatus.INVALID
                result.source_matches.append(SourceMatch(
                    claim=sv.get("cited_content", ""),
                    source_type=sv.get("source_type", "unknown"),
                    source_reference=sv.get("source_id", ""),
                    status=status,
                    confidence=0.85 if status == ValidationStatus.VALID else 0.5,
                    explanation=sv.get("explanation", ""),
                ))
                result.total_claims += 1
                if status == ValidationStatus.VALID:
                    result.valid_claims += 1
                else:
                    result.invalid_claims += 1
            
            factual_claims = llm_result.get("factual_claims", [])
            for fc in factual_claims:
                status_str = fc.get("status", "unverified").lower()
                if status_str == "verified":
                    status = ValidationStatus.VALID
                    result.valid_claims += 1
                elif status_str == "incorrect":
                    status = ValidationStatus.INVALID
                    result.invalid_claims += 1
                else:
                    status = ValidationStatus.PARTIAL
                
                result.source_matches.append(SourceMatch(
                    claim=fc.get("claim", ""),
                    source_type="content",
                    source_reference=fc.get("source_support", ""),
                    status=status,
                    confidence=0.8 if status == ValidationStatus.VALID else 0.4,
                    explanation=fc.get("explanation", ""),
                ))
                result.total_claims += 1
            
            result.summary = llm_result.get("summary", "검증 완료")
            
            accuracy_score = llm_result.get("overall_accuracy_score", 0.5)
            result.overall_valid = accuracy_score >= 0.7
            
        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            result.errors.append(str(e))
            result.overall_valid = False
        
        return result
    
    def _validate_with_llm(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Call LLM to validate content."""
        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        
        user_message = f"""다음 투자 브리핑을 검증해주세요:

티커: {context['ticker']}

## 제공된 출처
{json.dumps(context['sources'], ensure_ascii=False, indent=2)}

## 검증할 내용
{json.dumps(context['content_to_validate'], ensure_ascii=False, indent=2)}

출처와 브리핑 내용이 일치하는지 확인하고, 특히:
1. SEC 공시 날짜가 정확한지
2. 뉴스 기사 인용이 올바른지
3. 시장 데이터(주가, P/E)가 정확한지
검증해주세요."""
        
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": INVESTMENT_BRIEFING_VALIDATOR_PROMPT},
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
            return {"summary": response_text, "overall_accuracy_score": 0.5}


# =============================================================================
# Convenience Function
# =============================================================================

def validate_investment_briefing(
    script_json: str,
    validate_content: bool = True,
) -> ValidationResult:
    """
    Convenience function to validate an investment briefing.
    
    Args:
        script_json: JSON string of the investment briefing
        validate_content: Whether to also validate content with LLM
        
    Returns:
        Combined ValidationResult
    """
    from validation_agent.base import ValidationAgent
    
    agent = ValidationAgent()
    
    # Register validators
    source_validator = InvestmentBriefingSourceValidator()
    agent.register_validator(source_validator)
    
    if validate_content:
        content_validator = InvestmentBriefingContentValidator()
        agent.register_validator(content_validator)
    
    return agent.validate(script_json)

