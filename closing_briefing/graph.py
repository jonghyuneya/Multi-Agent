"""
LangGraph implementation for the Korean closing market briefing pipeline.

Defines nodes and graph structure for:
- load_sources: Load data from source files
- script_writer_with_tools: Generate script using tool calls for data access
- critic: Review and critique the script
- revision_writer: Revise script based on feedback
"""

import json
import logging
from typing import Literal, Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from langgraph.graph import StateGraph, END

from closing_briefing.config import Config, InvalidLLMJSONError
from closing_briefing.models import (
    ClosingBriefingState,
    ExtractedFact,
    EarningsResult,
    NewsItem,
    UpcomingEvent,
    MacroIndicator,
    CriticFeedback,
    ChecklistItem,
    HallucinationItem,
    Reference,
)
from closing_briefing.prompts import (
    SCRIPT_WRITER_WITH_TOOLS_SYSTEM_PROMPT,
    CRITIC_WITH_TOOLS_SYSTEM_PROMPT,
    REVISION_WRITER_SYSTEM_PROMPT,
)
from closing_briefing.data_loader import ClosingBriefingDataLoader
from closing_briefing.tools import BRIEFING_TOOLS, DataToolExecutor, format_tool_result_for_llm

# Import new source tools adapter (uses same tools as validation_agent)
try:
    from closing_briefing.source_tools_adapter import (
        BriefingSourceToolAdapter,
        SourceConfig,
        create_briefing_tools,
        create_tool_executor,
        format_tool_result_for_llm as format_source_tool_result,
    )
    SOURCE_TOOLS_AVAILABLE = True
except ImportError:
    SOURCE_TOOLS_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# LLM Wrapper with Tool Support
# ============================================================================

def call_llm(
    system_prompt: str,
    user_content: str,
    response_format: Literal["json", "text"] = "text",
    model: str = None,
    temperature: float = None,
) -> str:
    """
    Call the OpenAI API with the given system prompt and user content.
    """
    Config.validate()
    
    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    
    model = model or Config.OPENAI_MODEL
    temperature = temperature if temperature is not None else Config.OPENAI_TEMPERATURE
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": Config.MAX_TOKENS,
    }
    
    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}
    
    try:
        logger.info(f"Calling LLM with model={model}, response_format={response_format}")
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        
        if response_format == "json":
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise InvalidLLMJSONError(
                    f"LLM returned invalid JSON: {str(e)}",
                    raw_response=content
                )
        
        return content
        
    except Exception as e:
        logger.error(f"Error calling LLM: {str(e)}")
        raise


def call_llm_with_tools(
    system_prompt: str,
    user_content: str,
    tools: List[Dict],
    tool_executor: DataToolExecutor,
    model: str = None,
    temperature: float = None,
    max_tool_calls: int = 20,
) -> tuple[str, List[Reference]]:
    """
    Call the OpenAI API with tool support.
    
    The LLM can call tools to retrieve data, and we execute those tools
    and feed results back until the LLM produces a final response.
    
    Args:
        system_prompt: System prompt for the LLM
        user_content: User message content
        tools: List of tool definitions
        tool_executor: DataToolExecutor instance to execute tool calls
        model: Model to use
        temperature: Temperature setting
        max_tool_calls: Maximum number of tool call rounds
        
    Returns:
        Tuple of (final_response, list_of_references)
    """
    Config.validate()
    
    client = OpenAI(api_key=Config.OPENAI_API_KEY)
    
    model = model or Config.OPENAI_MODEL
    temperature = temperature if temperature is not None else Config.OPENAI_TEMPERATURE
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    
    all_references: List[Reference] = []
    tool_call_count = 0
    
    while tool_call_count < max_tool_calls:
        logger.info(f"Calling LLM with tools (round {tool_call_count + 1})")
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=Config.MAX_TOKENS,
        )
        
        message = response.choices[0].message
        
        # Check if the model wants to call tools
        if message.tool_calls:
            # Add assistant message with tool calls
            messages.append(message)
            
            # Process each tool call
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                
                logger.info(f"Executing tool: {tool_name} with args: {arguments}")
                
                # Execute the tool
                result = tool_executor.execute_tool(tool_name, arguments)
                
                # Collect references
                for ref_dict in result.get('references', []):
                    all_references.append(Reference(
                        source_type=ref_dict.get('source_type', ''),
                        source_file=ref_dict.get('source_file', ''),
                        quote=ref_dict.get('quote', ''),
                        provider=ref_dict.get('provider'),
                        date=ref_dict.get('date'),
                    ))
                
                # Format result for LLM
                result_str = format_tool_result_for_llm(result)
                
                # Add tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_str,
                })
            
            tool_call_count += 1
        else:
            # No more tool calls, return the final response
            return message.content, all_references
    
    # If we hit max tool calls, get final response without tools
    logger.warning(f"Hit max tool calls ({max_tool_calls}), forcing final response")
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=Config.MAX_TOKENS,
    )
    
    return response.choices[0].message.content, all_references


# ============================================================================
# Node Functions
# ============================================================================

def load_sources_node(state: ClosingBriefingState) -> Dict[str, Any]:
    """
    Load data from source files.
    """
    logger.info("=== Node: load_sources ===")
    
    source_path = state.sources.get('_source_path', 'data/sample_sources')
    load_news_from_dynamodb = state.sources.get('_load_news_from_dynamodb', True)
    dynamodb_profile = state.sources.get('_dynamodb_profile', 'jonghyun')
    
    loader = ClosingBriefingDataLoader(
        source_path,
        load_news_from_dynamodb=load_news_from_dynamodb,
        dynamodb_profile=dynamodb_profile,
    )
    sources = loader.load_all_sources()
    
    briefing_date = state.briefing_date
    if not briefing_date:
        market_summary = sources.get('market_summary', {})
        briefing_date = market_summary.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    logger.info(f"Loaded sources for briefing date: {briefing_date}")
    logger.info(f"Sources loaded: macro={len(sources.get('macro_data', []))}, "
                f"earnings={len(sources.get('earnings_data', []))}, "
                f"news={len(sources.get('news_data', []))}, "
                f"calendar={len(sources.get('calendar_events', []))}")
    
    return {
        "sources": sources,
        "briefing_date": briefing_date,
    }


def script_writer_with_tools_node(state: ClosingBriefingState) -> Dict[str, Any]:
    """
    Generate the closing script using tool calls to access data.
    
    The LLM will call tools to retrieve specific data and include
    exact references in the output.
    
    Uses the same source tools as validation_agent:
    - search_calendar_events: TradingEconomics calendar
    - search_macro_indicators: TradingEconomics indicators
    - search_news_articles: News from JSON/DynamoDB
    - search_fomc_events: FOMC press conferences
    - search_yahoo_finance_news: Yahoo Finance news
    - search_market_data: Live market data
    - search_sec_filings: SEC Edgar filings
    """
    logger.info("=== Node: script_writer_with_tools ===")
    
    sources = state.sources
    briefing_date = state.briefing_date
    
    # Determine which tool system to use
    use_source_tools = SOURCE_TOOLS_AVAILABLE and sources.get('_use_source_tools', False)
    
    if use_source_tools:
        # Use new source tools (same as validation_agent)
        logger.info("Using source_tools_adapter (validation_agent compatible)")
        
        config = SourceConfig(
            te_calendar_path=Path(sources.get('_te_calendar_path')) if sources.get('_te_calendar_path') else None,
            te_indicators_path=Path(sources.get('_te_indicators_path')) if sources.get('_te_indicators_path') else None,
            te_fomc_path=Path(sources.get('_te_fomc_path')) if sources.get('_te_fomc_path') else None,
            news_path=Path(sources.get('_news_path')) if sources.get('_news_path') else None,
            market_data_path=Path(sources.get('_market_data_path')) if sources.get('_market_data_path') else None,
            sec_edgar_path=Path(sources.get('_sec_edgar_path')) if sources.get('_sec_edgar_path') else None,
            yahoo_finance_profile=sources.get('_dynamodb_profile', 'jonghyun'),
            briefing_date=briefing_date,
        )
        
        tool_executor = BriefingSourceToolAdapter(config)
        tools = create_briefing_tools()
        result_formatter = format_source_tool_result
        
        user_message = f"""오늘 날짜: {briefing_date}

장마감 브리핑 스크립트를 작성해주세요.

## 사용 가능한 도구 (Tools)
다음 도구들을 사용하여 정확한 데이터를 조회하세요:

1. `search_calendar_events` - 경제 일정 조회 (FOMC, CPI, 고용지표 등)
2. `search_macro_indicators` - 거시경제 지표 조회 (금리, 물가, PMI 등)
3. `search_news_articles` - 뉴스 기사 조회
4. `search_fomc_events` - FOMC 회의/기자회견 정보 조회
5. `search_yahoo_finance_news` - Yahoo Finance 뉴스 조회
6. `search_market_data` - 시장 데이터 조회 (지수, 주가, VIX 등)
7. `search_sec_filings` - SEC 공시 조회 (10-K, 10-Q, 8-K 등)
8. `get_all_sources_summary` - 사용 가능한 데이터 요약 확인

## 작성 규칙
1. **반드시 도구를 먼저 호출**하여 데이터를 조회한 후 스크립트를 작성하세요
2. 모든 숫자와 사실은 도구 호출 결과에서 가져와야 합니다
3. 각 정보의 출처를 [REF: source_type | "정확한 인용문"] 형식으로 표시하세요
4. 추측이나 가정 없이 조회된 데이터만 사용하세요

## 추천 작성 순서
1. `get_all_sources_summary` - 먼저 어떤 데이터가 있는지 확인
2. `search_market_data` - 주요 지수 동향 확인 (S&P 500, NASDAQ 등)
3. `search_news_articles` - 오늘의 주요 뉴스 확인
4. `search_calendar_events` - 향후 경제 일정 확인
5. `search_macro_indicators` - 관련 거시지표 확인

스크립트를 작성하세요."""
        
    else:
        # Use legacy tool system
        logger.info("Using legacy DataToolExecutor")
        tool_executor = DataToolExecutor(sources, briefing_date)
        tools = BRIEFING_TOOLS
        result_formatter = format_tool_result_for_llm
        
        user_message = f"""오늘 날짜: {briefing_date}

장마감 브리핑 스크립트를 작성해주세요.

사용 가능한 데이터:
- 거시경제 지표: {len(sources.get('macro_data', []))}개
- 경제 일정: {len(sources.get('calendar_events', []))}개
- 뉴스: {len(sources.get('news_data', []))}개
- 실적 발표: {len(sources.get('earnings_data', []))}개
- FOMC 이벤트: {len(sources.get('fomc_events', []))}개

도구(tools)를 사용하여 정확한 데이터를 조회하고, 각 정보의 출처를 명시해주세요.
모든 숫자와 사실은 반드시 도구를 통해 확인한 데이터에서 가져와야 합니다.

스크립트 작성 시:
1. 먼저 get_market_summary로 시장 개요를 확인하세요
2. get_news_articles로 주요 뉴스를 확인하세요
3. get_earnings_results로 실적 발표를 확인하세요
4. get_calendar_events로 향후 일정을 확인하세요
5. 필요시 get_macro_indicators로 거시지표를 확인하세요

각 정보를 인용할 때는 반드시 [REF: source_type | "정확한 인용문"] 형식으로 출처를 표시하세요."""

    try:
        response, references = call_llm_with_tools(
            system_prompt=SCRIPT_WRITER_WITH_TOOLS_SYSTEM_PROMPT,
            user_content=user_message,
            tools=tools,
            tool_executor=tool_executor,
        )
        
        logger.info(f"Generated script draft ({len(response)} chars) with {len(references)} references")
        
        # Extract keywords from the script (simple extraction)
        keywords = _extract_keywords_from_script(response)
        
        return {
            "script_draft": response,
            "keywords": keywords,
            "references": references,
        }
        
    except Exception as e:
        logger.error(f"Error in script_writer_with_tools: {str(e)}")
        return {
            "script_draft": None,
            "error_message": str(e),
        }


def _extract_keywords_from_script(script: str) -> List[str]:
    """Extract keywords from the script content."""
    keywords = []
    
    # Common market themes to look for
    theme_patterns = [
        ("AI", "AI"),
        ("인공지능", "AI"),
        ("반도체", "반도체"),
        ("금리", "금리"),
        ("연준", "연준"),
        ("Fed", "연준"),
        ("인플레이션", "인플레이션"),
        ("실적", "실적"),
        ("기술주", "기술주"),
        ("경기침체", "경기침체"),
        ("고용", "고용"),
    ]
    
    for pattern, keyword in theme_patterns:
        if pattern in script and keyword not in keywords:
            keywords.append(keyword)
        if len(keywords) >= 3:
            break
    
    if not keywords:
        keywords = ["시장 동향"]
    
    return keywords


def critic_node(state: ClosingBriefingState) -> Dict[str, Any]:
    """
    Review and critique the script draft using tool calls to verify data.
    
    Uses the same source tools as validation_agent for fact-checking.
    """
    logger.info("=== Node: critic (with tools) ===")
    
    if not state.script_draft:
        logger.error("No script draft to critique")
        return {
            "critic_feedback": None,
            "error_message": "No script draft available for critique",
        }
    
    sources = state.sources
    briefing_date = state.briefing_date
    
    # Determine which tool system to use
    use_source_tools = SOURCE_TOOLS_AVAILABLE and sources.get('_use_source_tools', False)
    
    if use_source_tools:
        # Use new source tools (same as validation_agent)
        config = SourceConfig(
            te_calendar_path=Path(sources.get('_te_calendar_path')) if sources.get('_te_calendar_path') else None,
            te_indicators_path=Path(sources.get('_te_indicators_path')) if sources.get('_te_indicators_path') else None,
            te_fomc_path=Path(sources.get('_te_fomc_path')) if sources.get('_te_fomc_path') else None,
            news_path=Path(sources.get('_news_path')) if sources.get('_news_path') else None,
            market_data_path=Path(sources.get('_market_data_path')) if sources.get('_market_data_path') else None,
            sec_edgar_path=Path(sources.get('_sec_edgar_path')) if sources.get('_sec_edgar_path') else None,
            yahoo_finance_profile=sources.get('_dynamodb_profile', 'jonghyun'),
            briefing_date=briefing_date,
        )
        tool_executor = BriefingSourceToolAdapter(config)
        tools = create_briefing_tools()
        
        user_message = f"""## 검증할 대본:

{state.script_draft}

---

## 검증 지시사항:

다음 도구들을 사용하여 대본의 모든 사실을 검증하세요:

1. `search_calendar_events` - 경제 일정 검증
2. `search_macro_indicators` - 거시경제 지표 검증
3. `search_news_articles` - 뉴스 기사 검증
4. `search_fomc_events` - FOMC 정보 검증
5. `search_yahoo_finance_news` - Yahoo Finance 뉴스 검증
6. `search_market_data` - 시장 데이터 검증

검증 프로세스:
1. 대본에서 수치/날짜/이벤트를 추출하세요
2. 각 항목에 대해 관련 도구를 호출하세요
3. 도구 결과와 대본 내용을 대조하세요
4. 불일치하는 항목을 "환각"으로 표시하세요

한국어로 검증 보고서를 작성하세요."""
    else:
        # Use legacy tool system
        tool_executor = DataToolExecutor(sources, briefing_date)
        tools = BRIEFING_TOOLS
        
        user_message = f"""## 검증할 대본:

{state.script_draft}

---

## 검증 지시사항:

1. 도구를 호출하여 원본 데이터를 가져오세요
2. 대본의 각 사실을 원본 데이터와 대조하세요
3. 불일치하거나 출처가 없는 정보를 환각으로 표시하세요
4. 한국어로 검증 보고서를 작성하세요

검증할 항목:
- 거시경제 지표 (get_macro_indicators)
- 뉴스 헤드라인 (get_news_articles)
- 경제 일정 (get_calendar_events)
- FOMC 정보 (get_fomc_events)
- 실적 수치 (get_earnings_results)
"""

    try:
        response, _ = call_llm_with_tools(
            system_prompt=CRITIC_WITH_TOOLS_SYSTEM_PROMPT,
            user_content=user_message,
            tools=tools,
            tool_executor=tool_executor,
        )
        
        critic_feedback = _parse_critic_response(response)
        
        logger.info(f"Critic evaluation complete: {critic_feedback.overall_quality}")
        
        new_iterations = state.iterations + 1
        
        return {
            "critic_feedback": critic_feedback,
            "iterations": new_iterations,
        }
        
    except Exception as e:
        logger.error(f"Error in critic: {str(e)}")
        return {
            "critic_feedback": None,
            "error_message": str(e),
        }


def _parse_critic_response(response: str) -> CriticFeedback:
    """Parse the critic's text response into structured feedback."""
    
    # Extract summary evaluation
    summary_start = response.find("### 요약 평가")
    summary_end = response.find("### 핵심 검증 결과")
    if summary_end == -1:
        summary_end = response.find("### 체크리스트")
    if summary_end == -1:
        summary_end = response.find("### 내용 체크리스트")
    
    summary_evaluation = ""
    if summary_start != -1:
        if summary_end != -1:
            summary_evaluation = response[summary_start + len("### 요약 평가"):summary_end].strip()
        else:
            summary_evaluation = response[summary_start + len("### 요약 평가"):].strip()[:500]
    
    def parse_checklist_item(text: str, item_name: str) -> ChecklistItem:
        status = "충족"
        if "심각한 미흡" in text:
            status = "심각한 미흡"
        elif "미흡" in text:
            status = "미흡"
        
        explanation = text
        for s in ["**충족**", "**미흡**", "**심각한 미흡**", "충족", "미흡", "심각한 미흡"]:
            if s in explanation:
                parts = explanation.split(s, 1)
                if len(parts) > 1:
                    explanation = parts[1].strip().lstrip('-').strip()
                    break
        
        return ChecklistItem(
            item_name=item_name,
            status=status,
            explanation=explanation[:500]
        )
    
    # Extract critical validation checks
    hallucination_check = ChecklistItem(
        item_name="1. 환각(Hallucination) 검증",
        status="충족",
        explanation="검증 결과를 파싱할 수 없습니다."
    )
    timeliness_check = ChecklistItem(
        item_name="2. 시의성(Timeliness) 검증",
        status="충족",
        explanation="검증 결과를 파싱할 수 없습니다."
    )
    value_check = ChecklistItem(
        item_name="3. 정보 가치(Value) 검증",
        status="충족",
        explanation="검증 결과를 파싱할 수 없습니다."
    )
    source_citation_check = ChecklistItem(
        item_name="4. 출처 명시(Source Citation) 검증",
        status="충족",
        explanation="검증 결과를 파싱할 수 없습니다."
    )
    
    critical_start = response.find("### 핵심 검증 결과")
    critical_end = response.find("### 내용 체크리스트")
    if critical_end == -1:
        critical_end = response.find("### 스타일 체크리스트")
    
    if critical_start != -1:
        if critical_end != -1:
            critical_text = response[critical_start:critical_end]
        else:
            critical_text = response[critical_start:critical_start + 1500]
        
        lines = critical_text.split('\n')
        for line in lines:
            line = line.strip()
            if '환각' in line or 'Hallucination' in line:
                hallucination_check = parse_checklist_item(line, "1. 환각(Hallucination) 검증")
            elif '시의성' in line or 'Timeliness' in line:
                timeliness_check = parse_checklist_item(line, "2. 시의성(Timeliness) 검증")
            elif '정보 가치' in line or 'Value' in line:
                value_check = parse_checklist_item(line, "3. 정보 가치(Value) 검증")
            elif '출처' in line or 'Source Citation' in line:
                source_citation_check = parse_checklist_item(line, "4. 출처 명시(Source Citation) 검증")
    
    # Extract hallucinations found
    hallucinations_found = []
    halluc_start = response.find("### 환각 발견 목록")
    halluc_end = response.find("### 구체적인 수정 제안")
    if halluc_start != -1:
        if halluc_end != -1:
            halluc_text = response[halluc_start:halluc_end]
        else:
            halluc_text = response[halluc_start:halluc_start + 1000]
        
        if "환각 없음" not in halluc_text:
            lines = halluc_text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('-') and '→' in line:
                    parts = line.split('→')
                    if len(parts) >= 2:
                        hallucinations_found.append(HallucinationItem(
                            fabricated_content=parts[0].lstrip('-').strip(),
                            explanation=parts[1].strip()
                        ))
    
    # Extract content checklist
    checklist = []
    content_start = response.find("### 내용 체크리스트")
    content_end = response.find("### 스타일 체크리스트")
    if content_start != -1:
        if content_end != -1:
            content_text = response[content_start:content_end]
        else:
            content_text = response[content_start:content_start + 1500]
        
        lines = content_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('-') and ('충족' in line or '미흡' in line):
                if ':' in line:
                    parts = line.split(':', 1)
                    item_name = parts[0].replace('-', '').strip()
                    explanation = parts[1].strip() if len(parts) > 1 else ""
                    status = "충족" if "충족" in line and "미흡" not in line else "미흡"
                    checklist.append(ChecklistItem(
                        item_name=item_name,
                        status=status,
                        explanation=explanation[:500]
                    ))
    
    # Extract style checklist
    style_start = response.find("### 스타일 체크리스트")
    style_end = response.find("### 환각 발견 목록")
    if style_end == -1:
        style_end = response.find("### 구체적인 수정 제안")
    
    if style_start != -1:
        if style_end != -1:
            style_text = response[style_start:style_end]
        else:
            style_text = response[style_start:style_start + 1500]
        
        lines = style_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('-') and ('충족' in line or '미흡' in line):
                if ':' in line:
                    parts = line.split(':', 1)
                    item_name = parts[0].replace('-', '').strip()
                    explanation = parts[1].strip() if len(parts) > 1 else ""
                    status = "충족" if "충족" in line and "미흡" not in line else "미흡"
                    checklist.append(ChecklistItem(
                        item_name=item_name,
                        status=status,
                        explanation=explanation[:500]
                    ))
    
    # Extract specific suggestions
    suggestions = []
    suggestions_start = response.find("### 구체적인 수정 제안")
    if suggestions_start != -1:
        suggestions_text = response[suggestions_start + len("### 구체적인 수정 제안"):]
        lines = suggestions_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•'):
                suggestion = line.lstrip('-•').strip()
                if suggestion:
                    suggestions.append(suggestion)
    
    # Determine overall quality
    critical_issues = 0
    if hallucination_check.status == "심각한 미흡":
        critical_issues += 2
    elif hallucination_check.status == "미흡":
        critical_issues += 1
    if timeliness_check.status == "심각한 미흡":
        critical_issues += 2
    elif timeliness_check.status == "미흡":
        critical_issues += 1
    if value_check.status == "심각한 미흡":
        critical_issues += 2
    elif value_check.status == "미흡":
        critical_issues += 1
    
    miheup_count = sum(1 for item in checklist if "미흡" in item.status)
    
    if critical_issues >= 2 or hallucinations_found:
        overall_quality = "심각"
    elif critical_issues == 1 or miheup_count >= 4:
        overall_quality = "미흡"
    elif miheup_count >= 2:
        overall_quality = "보통"
    elif miheup_count == 1:
        overall_quality = "양호"
    else:
        overall_quality = "우수"
    
    return CriticFeedback(
        summary_evaluation=summary_evaluation or "평가를 파싱할 수 없습니다.",
        hallucination_check=hallucination_check,
        timeliness_check=timeliness_check,
        value_check=value_check,
        source_citation_check=source_citation_check,
        hallucinations_found=hallucinations_found,
        checklist=checklist,
        specific_suggestions=suggestions,
        overall_quality=overall_quality
    )


def revision_writer_node(state: ClosingBriefingState) -> Dict[str, Any]:
    """
    Revise the script based on critic feedback using tools.
    
    Uses the same source tools as validation_agent for verification.
    """
    logger.info("=== Node: revision_writer ===")
    
    if state.critic_feedback:
        if state.critic_feedback.hallucinations_found:
            logger.warning(f"Revising to fix {len(state.critic_feedback.hallucinations_found)} hallucinations")
    
    if not state.script_draft or not state.critic_feedback:
        logger.error("Missing script draft or critic feedback for revision")
        return {
            "script_revised": state.script_draft,
            "error_message": "Missing data for revision",
        }
    
    sources = state.sources
    briefing_date = state.briefing_date
    
    # Determine which tool system to use
    use_source_tools = SOURCE_TOOLS_AVAILABLE and sources.get('_use_source_tools', False)
    
    if use_source_tools:
        # Use new source tools (same as validation_agent)
        config = SourceConfig(
            te_calendar_path=Path(sources.get('_te_calendar_path')) if sources.get('_te_calendar_path') else None,
            te_indicators_path=Path(sources.get('_te_indicators_path')) if sources.get('_te_indicators_path') else None,
            te_fomc_path=Path(sources.get('_te_fomc_path')) if sources.get('_te_fomc_path') else None,
            news_path=Path(sources.get('_news_path')) if sources.get('_news_path') else None,
            market_data_path=Path(sources.get('_market_data_path')) if sources.get('_market_data_path') else None,
            sec_edgar_path=Path(sources.get('_sec_edgar_path')) if sources.get('_sec_edgar_path') else None,
            yahoo_finance_profile=sources.get('_dynamodb_profile', 'jonghyun'),
            briefing_date=briefing_date,
        )
        tool_executor = BriefingSourceToolAdapter(config)
        tools = create_briefing_tools()
    else:
        # Use legacy tool system
        tool_executor = DataToolExecutor(sources, briefing_date)
        tools = BRIEFING_TOOLS
    
    # Build user message with feedback
    user_message = f"""## 수정이 필요한 스크립트:

{state.script_draft}

## 비평 피드백:

### 요약 평가:
{state.critic_feedback.summary_evaluation}

### 전체 품질: {state.critic_feedback.overall_quality}

### 수정 제안:
{chr(10).join('- ' + s for s in state.critic_feedback.specific_suggestions)}

### 발견된 환각 (허위 정보):
{chr(10).join('- ' + h.fabricated_content + ' → ' + h.explanation for h in state.critic_feedback.hallucinations_found) if state.critic_feedback.hallucinations_found else '없음'}

---

위 피드백을 바탕으로 스크립트를 수정해주세요.
도구를 사용하여 모든 정보를 다시 확인하고, 정확한 출처와 함께 스크립트를 작성해주세요."""

    try:
        response, references = call_llm_with_tools(
            system_prompt=REVISION_WRITER_SYSTEM_PROMPT,
            user_content=user_message,
            tools=tools,  # Use the appropriate tool set
            tool_executor=tool_executor,
        )
        
        logger.info(f"Generated revised script ({len(response)} chars)")
        
        # Merge new references with existing ones
        all_references = list(state.references) if state.references else []
        all_references.extend(references)
        
        return {
            "script_revised": response,
            "script_draft": response,
            "references": all_references,
        }
        
    except Exception as e:
        logger.error(f"Error in revision_writer: {str(e)}")
        return {
            "script_revised": state.script_draft,
            "error_message": str(e),
        }


# ============================================================================
# Conditional Edge Logic
# ============================================================================

def _check_needs_revision(critic_feedback: CriticFeedback) -> tuple[bool, str]:
    """Check if the script needs revision based on critic feedback."""
    if critic_feedback.hallucinations_found:
        return True, f"환각 발견: {len(critic_feedback.hallucinations_found)}개의 허위 정보가 발견되었습니다."
    
    if critic_feedback.hallucination_check.status in ["미흡", "심각한 미흡"]:
        return True, f"환각 검증 미흡: {critic_feedback.hallucination_check.explanation}"
    
    if critic_feedback.timeliness_check.status in ["미흡", "심각한 미흡"]:
        return True, f"시의성 검증 미흡: {critic_feedback.timeliness_check.explanation}"
    
    if critic_feedback.value_check.status == "심각한 미흡":
        return True, f"정보 가치 심각하게 미흡: {critic_feedback.value_check.explanation}"
    
    if critic_feedback.overall_quality in ["심각", "미흡"]:
        return True, f"전체 품질 미흡: {critic_feedback.overall_quality}"
    
    critical_failures = sum(
        1 for item in critic_feedback.checklist 
        if "미흡" in item.status and any(
            keyword in item.item_name.lower() 
            for keyword in ["키워드", "실적", "뉴스", "이벤트"]
        )
    )
    
    if critical_failures >= 2:
        return True, f"핵심 체크리스트 항목 {critical_failures}개 미흡"
    
    return False, "품질 기준 충족"


def should_continue_revision(state: ClosingBriefingState) -> Literal["revision_writer", "end"]:
    """Determine whether to continue with revision or end."""
    if not state.script_draft:
        logger.warning("No script draft available, ending workflow")
        return "end"
    
    if not state.critic_feedback:
        logger.warning("No critic feedback available, ending workflow")
        return "end"
    
    if state.iterations > state.max_iterations:
        logger.info("Max iterations reached, ending workflow")
        return "end"
    
    needs_revision, reason = _check_needs_revision(state.critic_feedback)
    
    if needs_revision:
        logger.info(f"Revision needed: {reason} (iteration {state.iterations}/{state.max_iterations})")
        return "revision_writer"
    else:
        logger.info(f"Quality acceptable, no revision needed: {reason}")
        return "end"


def should_iterate(state: ClosingBriefingState) -> Literal["critic", "end"]:
    """Determine whether to iterate (critic again) or end after revision."""
    if not state.script_revised:
        logger.warning("No revised script available, ending workflow")
        return "end"
    
    if state.iterations >= state.max_iterations:
        logger.info(f"Max iterations ({state.max_iterations}) reached, ending workflow")
        return "end"
    
    if state.critic_feedback:
        had_hallucinations = bool(state.critic_feedback.hallucinations_found)
        had_critical_failure = state.critic_feedback.hallucination_check.status in ["미흡", "심각한 미흡"]
        had_timeliness_issue = state.critic_feedback.timeliness_check.status in ["미흡", "심각한 미흡"]
        
        if had_hallucinations or had_critical_failure or had_timeliness_issue:
            logger.info(f"Re-validating after critical issue fix (iteration {state.iterations + 1}/{state.max_iterations})")
            return "critic"
    
    logger.info("Revision complete, ending workflow")
    return "end"


# ============================================================================
# Graph Construction
# ============================================================================

def build_graph() -> StateGraph:
    """
    Build and compile the LangGraph workflow for closing briefing generation.
    """
    workflow = StateGraph(ClosingBriefingState)
    
    # Add nodes - using tool-based script writer
    workflow.add_node("load_sources", load_sources_node)
    workflow.add_node("script_writer", script_writer_with_tools_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("revision_writer", revision_writer_node)
    
    # Set entry point
    workflow.set_entry_point("load_sources")
    
    # Add edges
    workflow.add_edge("load_sources", "script_writer")
    workflow.add_edge("script_writer", "critic")
    
    # Conditional edge after critic
    workflow.add_conditional_edges(
        "critic",
        should_continue_revision,
        {
            "revision_writer": "revision_writer",
            "end": END,
        }
    )
    
    # Conditional edge after revision
    workflow.add_conditional_edges(
        "revision_writer",
        should_iterate,
        {
            "critic": "critic",
            "end": END,
        }
    )
    
    app = workflow.compile()
    
    logger.info("Graph compiled successfully")
    
    return app


def save_output(state: ClosingBriefingState, output_path: str = None) -> str:
    """
    Save the final script to a file with references and structured sources.
    """
    from pathlib import Path
    
    output_dir = Path(output_path) if output_path else Path(Config.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    briefing_date = state.briefing_date or timestamp[:8]
    
    # Save final script (Markdown format)
    final_script = state.script_revised or state.script_draft
    script_file = output_dir / f"closing_briefing_{briefing_date}_{timestamp}.md"
    
    with open(script_file, 'w', encoding='utf-8') as f:
        f.write(f"# 장마감 브리핑 - {briefing_date}\n\n")
        f.write(f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"키워드: {', '.join(state.keywords)}\n\n")
        f.write("---\n\n")
        f.write(final_script or "스크립트를 생성할 수 없습니다.")
        
        # Add references section
        if state.references:
            f.write("\n\n---\n\n")
            f.write("## 📚 참고 자료 (References)\n\n")
            
            # Group by source type
            by_type: Dict[str, List[Reference]] = {}
            for ref in state.references:
                if ref.source_type not in by_type:
                    by_type[ref.source_type] = []
                by_type[ref.source_type].append(ref)
            
            type_labels = {
                "macro_data": "📊 거시경제 지표",
                "calendar_events": "📅 경제 일정",
                "news_data": "📰 뉴스",
                "earnings_data": "💰 실적 발표",
                "fomc_events": "🏛️ FOMC",
                "market_summary": "📈 시장 요약"
            }
            
            for source_type, refs in by_type.items():
                label = type_labels.get(source_type, source_type)
                f.write(f"### {label}\n\n")
                
                seen_quotes = set()
                for ref in refs:
                    quote = ref.quote
                    if quote in seen_quotes:
                        continue
                    seen_quotes.add(quote)
                    
                    line = f"- {quote}"
                    if ref.provider:
                        line += f" — {ref.provider}"
                    if ref.date:
                        line += f" ({ref.date})"
                    f.write(line + "\n")
                
                f.write("\n")
    
    logger.info(f"Saved script to: {script_file}")
    
    # Convert references to structured sources format (for validation agent)
    structured_sources = _convert_references_to_sources(state.references, state.sources)
    
    # Save metadata with structured sources
    meta_file = output_dir / f"closing_briefing_{briefing_date}_{timestamp}_meta.json"
    metadata = {
        "briefing_date": state.briefing_date,
        "keywords": state.keywords,
        "iterations": state.iterations,
        "sources": structured_sources,  # Structured sources for validation
        "references": [ref.model_dump() for ref in state.references] if state.references else [],
        "critic_feedback": state.critic_feedback.model_dump() if state.critic_feedback else None,
        "error_message": state.error_message,
    }
    
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Also save a standalone sources file for validation
    sources_file = output_dir / f"closing_briefing_{briefing_date}_{timestamp}_sources.json"
    with open(sources_file, 'w', encoding='utf-8') as f:
        json.dump({
            "date": briefing_date,
            "generated_at": datetime.now().isoformat(),
            "sources": structured_sources,
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved sources to: {sources_file}")
    
    return str(script_file)


def _convert_references_to_sources(references: List[Reference], raw_sources: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert Reference objects to structured sources format for validation agent.
    
    Output format compatible with validation_agent:
    - type: "article" | "indicator" | "event" | "chart"
    - pk/id/ticker: identifier
    - title/name: human-readable name
    - date: date of the data
    - value: for indicators
    - provider: for news
    """
    structured = []
    seen_keys = set()
    
    if not references:
        return structured
    
    for ref in references:
        # Create a unique key to avoid duplicates
        key = f"{ref.source_type}:{ref.quote[:50]}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        
        source_entry = {
            "source_type": ref.source_type,
            "quote": ref.quote,
            "date": ref.date,
        }
        
        # Map to validation agent format based on source type
        if ref.source_type == "news_data":
            source_entry["type"] = "article"
            # Try to find pk from raw sources
            pk = _find_news_pk(ref.quote, raw_sources.get("news_data", []))
            if pk:
                source_entry["pk"] = pk
            source_entry["title"] = ref.quote.strip('"')
            if ref.provider:
                source_entry["provider"] = ref.provider
        
        elif ref.source_type == "calendar_events":
            source_entry["type"] = "event"
            # Extract event name and try to find id
            event_name = ref.quote.split(",")[0].strip() if ref.quote else ""
            source_entry["title"] = event_name
            event_id = _find_event_id(event_name, raw_sources.get("calendar_events", []))
            if event_id:
                source_entry["id"] = event_id
        
        elif ref.source_type == "macro_data":
            source_entry["type"] = "indicator"
            # Parse name and value from quote
            parts = ref.quote.split(":")
            if len(parts) >= 2:
                source_entry["name"] = parts[0].strip()
                source_entry["value"] = parts[1].strip().split(",")[0]
        
        elif ref.source_type == "market_summary":
            source_entry["type"] = "chart"
            # Try to extract ticker from quote
            ticker = _extract_ticker_from_quote(ref.quote)
            if ticker:
                source_entry["ticker"] = ticker
        
        elif ref.source_type == "earnings_data":
            source_entry["type"] = "earnings"
            # Parse company info
            parts = ref.quote.split(",")
            if parts:
                company_part = parts[0].strip()
                source_entry["company"] = company_part
                # Extract ticker if present
                if "(" in company_part and ")" in company_part:
                    ticker = company_part.split("(")[1].split(")")[0]
                    source_entry["ticker"] = ticker
        
        elif ref.source_type == "fomc_events":
            source_entry["type"] = "fomc"
            source_entry["title"] = ref.quote.split(",")[0].strip() if ref.quote else ""
        
        structured.append(source_entry)
    
    return structured


def _find_news_pk(quote: str, news_data: List[Dict]) -> Optional[str]:
    """Find the pk for a news article by matching headline."""
    headline = quote.strip('"')
    for article in news_data:
        article_headline = article.get("headline", "") or article.get("title", "")
        if headline.lower() in article_headline.lower() or article_headline.lower() in headline.lower():
            return article.get("pk") or article.get("id")
    return None


def _find_event_id(event_name: str, calendar_events: List[Dict]) -> Optional[str]:
    """Find the id for a calendar event by matching name."""
    for event in calendar_events:
        name = event.get("name", "") or event.get("title", "")
        if event_name.lower() in name.lower() or name.lower() in event_name.lower():
            return event.get("id")
    return None


def _extract_ticker_from_quote(quote: str) -> Optional[str]:
    """Extract ticker symbol from market summary quote."""
    # Common index mappings
    index_map = {
        "s&p 500": "^GSPC",
        "nasdaq": "^IXIC",
        "dow": "^DJI",
        "russell 2000": "^RUT",
        "vix": "^VIX",
    }
    
    quote_lower = quote.lower()
    for name, ticker in index_map.items():
        if name in quote_lower:
            return ticker
    
    return None
