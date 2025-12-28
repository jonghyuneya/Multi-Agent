# Validation Agent

AI 생성 스크립트의 사실 정확성과 대상 적합성을 검증하는 모듈형 프레임워크

## 개요

Validation Agent는 AI 에이전트가 생성한 스크립트를 원본 데이터와 대조하여 검증합니다:

1. **사실 검증 (Fact Validation)**: 스크립트의 모든 사실적 주장이 원본 데이터와 일치하는지 확인
2. **대상 적합성 (Audience Fitness)**: 콘텐츠가 대상 독자(경제/투자 관심자)에게 적합한지 평가
3. **인용 검증 (Citation Validation)**: 모든 사실적 주장에 적절한 출처 표기가 있는지 확인

## 아키텍처

```
validation_agent/
├── __init__.py              # 패키지 초기화 및 exports
├── base.py                  # 기본 클래스 및 데이터 구조
│   ├── SourceTool           # 소스 도구 추상 클래스
│   ├── Validator            # 검증기 추상 클래스
│   ├── ValidationResult     # 검증 결과 데이터 클래스
│   └── ValidationAgent      # 메인 검증 에이전트
├── source_tools.py          # 소스 도구 구현
│   ├── TECalendarSourceTool # TradingEconomics 캘린더
│   ├── TEIndicatorsSourceTool # 거시경제 지표
│   ├── FOMCSourceTool       # FOMC 문서
│   └── NewsSourceTool       # 뉴스 기사
├── validators.py            # 검증기 구현
│   ├── FactValidator        # 사실 검증
│   ├── AudienceValidator    # 대상 적합성
│   └── CitationValidator    # 인용 검증
├── config.py                # 설정
├── main.py                  # CLI 진입점
└── examples/
    └── closing_briefing_validator.py  # closing_briefing용 예제
```

## 설치

```bash
cd /home/jhkim/validation_agent
pip install -e .
```

## 빠른 시작

### Python API 사용

```python
from validation_agent import ValidationAgent
from validation_agent.source_tools import (
    TECalendarSourceTool,
    TEIndicatorsSourceTool,
    FOMCSourceTool,
)
from validation_agent.validators import (
    FactValidator,
    AudienceValidator,
    CitationValidator,
)
from pathlib import Path

# 1. 에이전트 생성
agent = ValidationAgent()

# 2. 소스 도구 등록
agent.register_source_tool(TECalendarSourceTool())
agent.register_source_tool(TEIndicatorsSourceTool())
agent.register_source_tool(FOMCSourceTool())

# 3. 검증기 등록
agent.register_validator(FactValidator())
agent.register_validator(AudienceValidator())
agent.register_validator(CitationValidator())

# 4. 소스 데이터 로드
agent.load_sources({
    "calendar_events": Path("/home/jhkim/te_calendar_scraper/output/calendar"),
    "macro_data": Path("/home/jhkim/te_calendar_scraper/output/indicators"),
    "fomc_events": Path("/home/jhkim/te_calendar_scraper/output/fomc_press_conferences"),
})

# 5. 스크립트 검증
script = """
여러분, 오늘 미국 CPI가 3.0%로 발표되었습니다. [REF: macro_data | "CPI YoY: 3.0%"]
연준의 12월 FOMC에서는 금리를 동결했습니다. [REF: fomc_events | "December 2024 FOMC"]
"""

result = agent.validate(script)

# 6. 결과 확인
print(result.summary)
print(f"전체 유효: {result.overall_valid}")
print(f"유효 주장: {result.valid_claims}/{result.total_claims}")
```

### Closing Briefing 전용 검증기

```python
from validation_agent.examples import create_closing_briefing_validator

# 사전 구성된 검증기 생성
validator = create_closing_briefing_validator(
    te_calendar_output_path="/home/jhkim/te_calendar_scraper/output"
)

# 스크립트 검증
result = validator.validate(script_text)

# 사실 검증만 실행
result = validator.validate_fact_only(script_text)

# 대상 적합성만 검증
result = validator.validate_audience_only(script_text)
```

### CLI 사용

```bash
# 스크립트 파일 검증
python -m validation_agent.main --script closing_script.txt

# 사실 검증만 실행
python -m validation_agent.main --script script.txt --validators fact

# JSON 출력
python -m validation_agent.main --script script.txt --output-json

# 결과 파일로 저장
python -m validation_agent.main --script script.txt -o result.json --output-json
```

## 새 소스 도구 추가하기

다른 데이터 소스를 추가하려면 `SourceTool`을 상속받아 구현합니다:

```python
from validation_agent.base import SourceTool, SourceMatch, ValidationStatus
from pathlib import Path
from typing import Any, Dict, List

class MyCustomSourceTool(SourceTool):
    """사용자 정의 소스 도구"""
    
    def __init__(self):
        self._data = []
        self._loaded = False
    
    @property
    def source_type(self) -> str:
        return "my_custom_source"
    
    def load_sources(self, path: Path) -> None:
        """소스 데이터 로드"""
        # CSV, JSON, DB 등에서 데이터 로드
        with open(path) as f:
            self._data = json.load(f)
        self._loaded = True
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """쿼리로 데이터 검색"""
        results = []
        for item in self._data:
            if query.lower() in str(item).lower():
                results.append(item)
        return results
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        """주장 검증"""
        matches = self.search(reference)
        
        if not matches:
            return SourceMatch(
                claim=claim,
                source_type=self.source_type,
                source_reference=reference,
                status=ValidationStatus.NOT_FOUND,
                explanation="데이터를 찾을 수 없음"
            )
        
        return SourceMatch(
            claim=claim,
            source_type=self.source_type,
            source_reference=reference,
            source_data=matches[0],
            status=ValidationStatus.VALID,
            confidence=0.9,
            explanation="검증 완료"
        )
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """OpenAI 함수 호출 스키마"""
        return {
            "type": "function",
            "function": {
                "name": "search_my_custom_source",
                "description": "내 사용자 정의 소스에서 데이터 검색",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "검색 쿼리"
                        }
                    },
                    "required": ["query"]
                }
            }
        }

# 사용법
agent = ValidationAgent()
agent.register_source_tool(MyCustomSourceTool())
agent.load_sources({"my_custom_source": Path("/path/to/data")})
```

## 다른 AI 에이전트에 적용하기

Validation Agent는 모듈형으로 설계되어 다양한 AI 에이전트 출력을 검증할 수 있습니다:

### 1. 새 검증기 구성 파일 생성

```python
# my_agent_validator.py
from validation_agent import ValidationAgent
from validation_agent.source_tools import CustomSourceTool  # 필요한 소스 도구
from validation_agent.validators import FactValidator, AudienceValidator

class MyAgentValidator:
    def __init__(self, source_path):
        self._agent = ValidationAgent()
        
        # 이 에이전트에 필요한 소스 도구 등록
        self._agent.register_source_tool(CustomSourceTool())
        
        # 필요한 검증기 등록
        self._agent.register_validator(FactValidator())
        self._agent.register_validator(AudienceValidator())
        
        # 소스 로드
        self._agent.load_sources({"custom_source": source_path})
    
    def validate(self, script: str):
        return self._agent.validate(script)
```

### 2. 프롬프트 커스터마이징

`validators.py`의 프롬프트를 수정하여 특정 도메인에 맞게 조정할 수 있습니다.

## 검증 결과 구조

```python
@dataclass
class ValidationResult:
    script_id: str              # 스크립트 식별자
    validated_at: datetime      # 검증 시간
    
    # 사실 검증
    total_claims: int           # 전체 주장 수
    valid_claims: int           # 유효한 주장 수
    invalid_claims: int         # 무효한 주장 수
    not_found_claims: int       # 출처 미확인 주장 수
    source_matches: List[SourceMatch]  # 상세 매칭 결과
    
    # 대상 적합성
    audience_fitness: AudienceFitness  # 적합성 등급
    audience_feedback: str      # 상세 피드백
    
    # 인용 검증
    citations_complete: bool    # 인용 완전성
    missing_citations: List[str] # 누락된 인용
    
    # 전체 결과
    overall_valid: bool         # 전체 통과 여부
    summary: str                # 요약
    errors: List[str]           # 오류 목록
```

## 환경 변수

```bash
# OpenAI 설정
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o

# 소스 경로 설정
VALIDATION_CALENDAR_PATH=/path/to/calendar
VALIDATION_INDICATORS_PATH=/path/to/indicators
VALIDATION_FOMC_PATH=/path/to/fomc
VALIDATION_NEWS_PATH=/path/to/news
VALIDATION_OUTPUT_DIR=/path/to/output
```

## 라이선스

MIT

