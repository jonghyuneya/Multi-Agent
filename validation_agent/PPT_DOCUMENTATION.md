# Validation Agent - PPT 문서

---

## 01. 개요

### Validation Agent

AI 에이전트가 생성한 스크립트를 원본 데이터와 대조하여 **사실 정확성과 출처 완전성**을 검증하는 프레임워크입니다.

- **입력**: AI 생성 스크립트 (텍스트 or JSON)
- **방식**: 모든 Validator 자동 실행 (모드 선택 없음)
- **검증**: 사실/대상/인용/출처/내용 5가지 관점
- **출력**: ValidationResult (통과/수정필요 + 상세 피드백)

---

### Why?

AI 에이전트가 생성한 콘텐츠는 환각(hallucination)의 위험이 있다.
특히 수치, 날짜, 이벤트명 같은 사실적 주장은 원본 데이터와 반드시 대조해야 한다.

Validation Agent는 스크립트에 포함된 모든 출처(article, chart, event)를 자동으로 검증하고, 출처가 실제로 존재하는지, 내용이 일치하는지 확인한다.

---

## 02. Structured Input

### 지원 스크립트 형식

#### 1) 텍스트 스크립트 (closing_briefing 출력)

```markdown
Host: 오늘 CPI가 3.0%로 발표되었습니다. [REF: macro_data | "CPI YoY: 3.0%"]

Analyst: 연준의 12월 FOMC에서는 금리를 동결했습니다. [REF: fomc_events | "December 2024"]
```

#### 2) JSON 스크립트 (구조화된 브리핑)

```json
{
    "date": "20251222",
    "nutshell": "기록적 금값과 AI 랠리 속 선택적 강세장",
    "scripts": [
        {
            "id": 1,
            "speaker": "해설자",
            "text": "금 선물이 사상 최고가를 기록했습니다.",
            "sources": [
                {"type": "article", "pk": "id#9e48...", "title": "Gold Rises..."},
                {"type": "chart", "ticker": "GC=F", "start_date": "...", "end_date": "..."},
                {"type": "event", "id": "387585", "title": "GDP Growth Rate", "date": "..."}
            ]
        }
    ]
}
```

### Source Types

| Type | 식별자 | 검증 방법 |
|------|--------|-----------|
| `article` | `pk` | 뉴스 DB에서 pk로 조회, title 일치 확인 |
| `chart` | `ticker` | 유효한 ticker인지, 날짜 범위 확인 |
| `event` | `id` | 캘린더에서 id로 조회, title/date 일치 확인 |

---

## 03. 파이프라인 아키텍처

### Validation Agent

스크립트를 입력받아 모든 검증을 자동으로 실행합니다.

- **입력**: 텍스트 스크립트 OR JSON 스크립트
- **방식**: 5개 Validator 동시 실행 (모드 선택 없음)
- **검증**: LLM + Tool Calls로 원본 데이터 대조
- **출력**: ValidationResult (통과/수정필요)

### 흐름도

```
         SCRIPT INPUT
         (Text or JSON)
              │
              ▼
     ┌─────────────────────┐
     │  ValidationAgent    │
     │                     │
     │ register_source_tool│
     │ register_validator  │
     │ load_sources        │
     │ validate()          │
     └──────────┬──────────┘
                │
    ┌───────────┼───────────┐
    │     ALL VALIDATORS    │
    │   (Run in Parallel)   │
    └───────────┬───────────┘
                │
    ┌───────────┼───────────┬───────────┬───────────┐
    ▼           ▼           ▼           ▼           ▼
┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐
│⚡Fact │  │⚡Audi-│  │⚡Cita-│  │Script │  │⚡Script│
│Valida-│  │ence  │  │tion  │  │Source │  │Content│
│tor    │  │Valida│  │Valida│  │Valida │  │Valida │
│       │  │tor   │  │tor   │  │tor    │  │tor    │
└───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘
    │          │          │          │          │
    └──────────┴──────────┴──────────┴──────────┘
                          │
                          ▼
               ┌─────────────────────┐
               │  Merge Results      │
               │  → ValidationResult │
               └─────────────────────┘
```

---

## 04. Source Tools

### 도구 목록

| Tool | Function | 데이터 소스 |
|------|----------|-------------|
| `TECalendarSourceTool` | `search_calendar_events` | calendar/*.csv |
| `TEIndicatorsSourceTool` | `search_macro_data` | indicators/*.csv |
| `FOMCSourceTool` | `search_fomc_events` | fomc_press_conferences/*.pdf |
| `NewsSourceTool` | `search_news_data` | news.json |
| `ArticleSourceTool` | `search_article` | articles.json (pk 기반) |
| `EventSourceTool` | `search_event` | events.json (id 기반) |
| `BriefingScriptSourceTool` | `search_briefing_sources` | script.json |

### 공통 인터페이스

```python
class SourceTool(ABC):
    @property
    def source_type(self) -> str: ...
    
    def load_sources(self, path: Path) -> None: ...
    
    def search(self, query: str) -> List[Dict]: ...
    
    def validate_claim(self, claim: str, ref: str) -> SourceMatch: ...
    
    def get_tool_definition(self) -> Dict: ...
```

---

## 05. Validators

### 5개 Validator (모두 자동 실행)

| Validator | 검증 항목 | LLM 사용 |
|-----------|-----------|----------|
| `FactValidator` | 사실 정확성 | ⚡ Yes + Tool Calls |
| `AudienceValidator` | 대상 적합성 | ⚡ Yes |
| `CitationValidator` | 인용 완전성 | ⚡ Yes |
| `ScriptSourceValidator` | 출처 존재 여부 | No (직접 조회) |
| `ScriptContentValidator` | 내용-출처 일치 | ⚡ Yes |

### 검증 흐름

```
1. FactValidator
   └── LLM이 Tool Calls로 원본 데이터 조회
   └── 스크립트 주장 vs 데이터 대조
   └── source_matches[] 생성

2. AudienceValidator
   └── LLM이 대상 적합성 평가
   └── 관련성, 접근성, 실용성, 어조 확인
   └── audience_fitness 등급

3. CitationValidator
   └── LLM이 [REF] 태그 완전성 확인
   └── 출처 누락 탐지
   └── missing_citations[] 생성

4. ScriptSourceValidator
   └── sources[] 배열에서 출처 추출
   └── 각 source type별 직접 조회
   └── 존재 여부 확인

5. ScriptContentValidator
   └── LLM이 text vs sources 일치 검증
   └── 과장/왜곡 탐지
   └── 상세 피드백 생성
```

---

## 06. FactValidator 상세

### 사실 검증 프로세스

```
🤖 LLM action: 스크립트에서 사실적 주장 추출
   "금 선물이 4,400달러를 기록했습니다"
   
🔧 Tool: 'search_macro_data(query="gold futures")'

✓ Checkpoint: 반환된 데이터와 주장 대조
   - 수치 일치 여부
   - 날짜 정확성
   - 표현 왜곡 여부

📋 Output: SourceMatch {
    claim: "금 선물이 4,400달러를 기록",
    source_type: "macro_data",
    status: "valid" | "invalid" | "not_found",
    explanation: "원본 데이터와 일치함",
    source_quote: "Gold Futures: $4,438.50"
}
```

---

## 07. ScriptSourceValidator 상세

### 출처 존재 검증 프로세스

```
입력 (JSON 스크립트):
{
    "sources": [
        {"type": "article", "pk": "id#9e48...", "title": "Gold Rises..."},
        {"type": "event", "id": "387585", "title": "GDP Growth Rate", "date": "2025-12-23"}
    ]
}

검증:
1. article 검증
   └── ArticleSourceTool.search(pk="id#9e48...")
   └── 반환된 title과 비교
   └── SourceMatch 생성

2. event 검증
   └── EventSourceTool.search(id="387585")
   └── 반환된 title, date와 비교
   └── SourceMatch 생성

출력:
source_matches: [
    {claim: "article pk=id#9e48...", status: "valid", ...},
    {claim: "event id=387585", status: "valid", ...}
]
```

---

## 08. ScriptContentValidator 상세

### 내용 일치 검증 프로세스

```
🤖 LLM action: script.text와 sources 대조

입력:
- text: "금 선물이 지정학 리스크로 사상 최고가를 기록했습니다"
- sources: [
    {"type": "article", "pk": "...", "title": "Gold Rises on Venezuela Tension"},
    {"type": "chart", "ticker": "GC=F", ...}
  ]

검증:
1. article 내용 조회 → 기사 본문 확인
2. chart 데이터 조회 → 가격 변동 확인
3. text 주장이 sources와 일치하는지 LLM 판단

✓ Checkpoint:
- 사실과 출처 일치
- 과장/왜곡 없음
- 인과관계 정확

📋 Output: {
    status: "valid",
    explanation: "text 내용이 sources와 일치함",
    details: [...]
}
```

---

## 09. ValidationResult

### 결과 구조

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
    source_matches: List[SourceMatch]
    
    # 대상 적합성
    audience_fitness: AudienceFitness  # excellent|good|fair|poor
    audience_feedback: str
    
    # 인용 검증
    citations_complete: bool
    missing_citations: List[str]
    
    # 전체 결과
    overall_valid: bool         # 최종 통과 여부
    summary: str
    errors: List[str]
```

### 출력 예시

```
════════════════════════════════════════════════════════════
검증 결과: briefing_20251222
검증 시각: 2025-12-22T18:45:00Z
════════════════════════════════════════════════════════════

📊 요약
────────────────────────────────────
전체 47개 주장 중 45개 검증 완료

📋 사실 검증: 43/47 (91.5%) 일치
  ⚠️ 불일치: 2건
  ❓ 출처 미확인: 2건

📁 출처 유형별 검증:
  - article: 28/30 확인, 1 부분일치, 0 불일치, 1 미확인
  - event: 8/8 확인
  - chart: 9/9 부분일치 (가격 검증 필요)

👥 대상 적합성: good

📝 출처 누락: 0건

════════════════════════════════════════════════════════════
전체 결과: ✅ 통과
════════════════════════════════════════════════════════════
```

---

## 10. 데이터 소스

### te_calendar_scraper 출력

```
te_calendar_scraper/output/
├── calendar/                    # 경제 일정 (CSV)
│   └── calendar_US_20251222.csv
├── indicators/                  # 거시경제 지표 (CSV)
│   └── indicators_US_20251222.csv
└── fomc_press_conferences/      # FOMC 기자회견 (PDF)
    └── 2024_dec_17-18_press_conference.pdf
```

### 추가 데이터 소스

| 파일 | 형식 | 내용 |
|------|------|------|
| `articles.json` | JSON | 뉴스 기사 (pk, title, content) |
| `events.json` | JSON | 경제 이벤트 (id, title, date) |
| `market_data/` | JSON | 시장 데이터 (ticker, OHLCV) |

---

## 11. 사용법

### Python API

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

### CLI

```bash
# 스크립트 파일 검증
python -m validation_agent.main --script briefing.json

# JSON 출력
python -m validation_agent.main --script script.txt --output-json

# 추가 데이터 소스 지정
python -m validation_agent.main --script briefing.json \
    --articles articles.json \
    --events events.json
```

---

## 12. 확장성

### 새 Source Tool 추가

```python
from validation_agent.base import SourceTool

class MyCustomSourceTool(SourceTool):
    @property
    def source_type(self) -> str:
        return "my_custom_source"
    
    def load_sources(self, path: Path) -> None:
        # 데이터 로드 로직
        pass
    
    def search(self, query: str) -> List[Dict]:
        # 검색 로직
        pass
    
    def validate_claim(self, claim: str, ref: str) -> SourceMatch:
        # 검증 로직
        pass

# 등록
agent.register_source_tool(MyCustomSourceTool())
```

### 새 Validator 추가

```python
from validation_agent.base import Validator

class MyCustomValidator(Validator):
    @property
    def name(self) -> str:
        return "my_custom"
    
    def validate(self, script: str, agent: ValidationAgent) -> ValidationResult:
        # 검증 로직
        pass

# 등록
agent.register_validator(MyCustomValidator())
```

---

## 13. 요약

### Validation Agent 파이프라인

```
1. 스크립트 입력
   텍스트 스크립트 OR JSON 스크립트
   → ValidationAgent.validate()

2. 소스 로드
   te_calendar_scraper/output + articles.json + events.json
   → 각 Source Tool에 로드

3. 검증 실행 (5개 Validator 동시 실행)
   ├── FactValidator (LLM + Tool Calls)
   ├── AudienceValidator (LLM)
   ├── CitationValidator (LLM)
   ├── ScriptSourceValidator (직접 조회)
   └── ScriptContentValidator (LLM + Sources)

4. 결과 병합
   모든 Validator 결과 → ValidationResult
   - source_matches 통합
   - overall_valid 계산
   - summary 생성

5. 출력
   ValidationResult
   - to_dict() → JSON
   - summary → 텍스트 요약
```

### 핵심 특징

- **모든 검증 자동 실행**: 모드 선택 없이 5개 Validator 동시 실행
- **Tool Binding**: LLM이 직접 원본 데이터 조회
- **다양한 출처 지원**: article, chart, event, calendar, indicators, FOMC
- **확장 가능**: 새 Source Tool / Validator 쉽게 추가
- **구조화된 출력**: ValidationResult로 프로그래밍 가능

