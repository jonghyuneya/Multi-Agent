# Validation Agent

AI 생성 스크립트의 사실 정확성과 대상 적합성을 검증하는 프레임워크

## 개요

Validation Agent는 AI 에이전트가 생성한 스크립트를 원본 데이터와 대조하여 **모든 검증을 한번에** 수행합니다:

1. **사실 검증 (Fact Validation)**: 스크립트의 모든 사실적 주장이 원본 데이터와 일치하는지 확인
2. **대상 적합성 (Audience Fitness)**: 콘텐츠가 대상 독자(경제/투자 관심자)에게 적합한지 평가
3. **인용 검증 (Citation Validation)**: 모든 사실적 주장에 적절한 출처 표기가 있는지 확인
4. **출처 검증 (Source Validation)**: 스크립트에 포함된 출처(article, chart, event)가 실제 존재하는지 확인
5. **내용 검증 (Content Validation)**: LLM을 사용하여 스크립트 내용이 출처와 일치하는지 심층 검증

## 설치

```bash
cd /home/jhkim/validation_agent
pip install -e .
```

## 빠른 시작

### Python API 사용

```python
from validation_agent.examples import create_closing_briefing_validator

# 검증기 생성 (모든 검증 자동 실행)
validator = create_closing_briefing_validator(
    te_calendar_output_path="/home/jhkim/te_calendar_scraper/output"
)

# 스크립트 검증
result = validator.validate(script_text)

# 결과 확인
print(result.summary)
print(f"전체 유효: {result.overall_valid}")
print(f"유효 주장: {result.valid_claims}/{result.total_claims}")
```

### 구조화된 JSON 스크립트 검증

```python
from validation_agent import validate_briefing_script
from pathlib import Path

# JSON 스크립트 읽기
with open("briefing_script.json") as f:
    script_json = f.read()

# 검증 (모든 검증 자동 실행)
result = validate_briefing_script(
    script_json,
    articles_path=Path("articles.json"),
    events_path=Path("events.json"),
)

print(result.summary)
```

### CLI 사용

```bash
# 스크립트 파일 검증 (모든 검증 자동 실행)
python -m validation_agent.main --script closing_script.txt

# JSON 출력
python -m validation_agent.main --script script.txt --output-json

# 구조화된 JSON 스크립트 검증
python -m validation_agent.main --script briefing.json \
    --articles articles.json \
    --events events.json

# 결과 파일로 저장
python -m validation_agent.main --script script.txt -o result.json --output-json
```

## 지원하는 스크립트 형식

### 1. 텍스트 스크립트 (closing_briefing 출력)

```markdown
# 장마감 브리핑 - 2025-12-22

**Host:** 오늘 미국 CPI가 3.0%로 발표되었습니다. [REF: macro_data | "CPI YoY: 3.0%"]

**Analyst:** 연준의 12월 FOMC에서는 금리를 동결했습니다. [REF: fomc_events | "December 2024 FOMC"]
```

### 2. 구조화된 JSON 스크립트

```json
{
    "date": "20251222",
    "nutshell": "기록적 금값과 AI 랠리 속 선택적 강세장",
    "scripts": [
        {
            "id": 1,
            "speaker": "해설자",
            "text": "금 선물은 온스당 4천4백달러를 기록했습니다.",
            "sources": [
                {"type": "article", "pk": "id#9e4894ca63cd8d66", "title": "Gold Rises to Record High"},
                {"type": "chart", "ticker": "GC=F", "start_date": "2025-12-19", "end_date": "2025-12-22"},
                {"type": "event", "id": "387585", "title": "gdp growth rate qoq", "date": "2025-12-23"}
            ],
            "time": [14871, 60602]
        }
    ]
}
```

## 출처 유형

| 유형 | 설명 | 식별자 |
|------|------|--------|
| `article` | 뉴스 기사 | `pk` (예: `id#9e4894ca63cd8d66`) |
| `chart` | 시장 데이터 | `ticker` (예: `^GSPC`, `GC=F`) |
| `event` | 경제 이벤트 | `id` (예: `387585`) |

## 데이터 소스

### te_calendar_scraper 출력

```
te_calendar_scraper/output/
├── calendar/           # 경제 이벤트 일정 (CSV)
├── indicators/         # 거시경제 지표 (CSV)
├── fomc_press_conferences/  # FOMC 기자회견 (PDF)
└── speeches_transcripts/    # 연준 연설문
```

### 추가 데이터

- `articles.json`: 뉴스 기사 (pk, title, provider 등)
- `events.json`: 경제 이벤트 (id, title, date 등)

## 검증 결과

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

## 새 소스 도구 추가하기

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
        # 데이터 로드 로직
        pass
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        # 검색 로직
        pass
    
    def validate_claim(self, claim: str, reference: str) -> SourceMatch:
        # 검증 로직
        pass

# 등록
from validation_agent import ValidationAgent
agent = ValidationAgent()
agent.register_source_tool(MyCustomSourceTool())
```

## 환경 변수

```bash
# OpenAI 설정
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4o
```

## 라이선스

MIT
