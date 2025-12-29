# Closing Briefing - PPT 문서

---

## 01. 개요

### Closing Briefing 에이전트

당일 시장 데이터와 경제 뉴스를 기반으로 **장마감 브리핑 대본**을 자동 생성하는 AI 에이전트입니다.

- **입력**: 거시경제 지표 + FOMC + 경제 캘린더 + 뉴스 + 실적
- **방식**: LangGraph ReAct, LLM이 Tool로 근거를 직접 조회
- **검증**: Critic 에이전트가 환각/시의성/출처 검증
- **출력**: themes[], nutshell, scripts[] (후속 에이전트에게 입력으로)

---

### Why?

출력은 사람이 읽는 브리핑 대본이지만, 동시에 다음 단계 에이전트가 그대로 받아 확장해야 하는 입력 데이터이다.

themes, nutshell, scripts처럼 필드가 고정된 JSON 스키마로 결과를 내보내 필드 누락이나 형식 오류를 감지할 수 있고, 각 문장에 sources[]를 붙여 기사, 차트, 이벤트 같은 근거를 구조적으로 남긴다.

---

## 02. Structured Output

### Schema

| 필드 | 설명 |
|------|------|
| `themes[]` | 오늘 핵심 테마 1~3개 |
| `themes[].related_news[]` | 테마 근거 기사 메타 |
| `nutshell` | 오늘 장 한마디 (헤드라인) |
| `scripts[]` | 진행자/해설자 대사, 전체 방송 대본의 뼈대 |
| `scripts[].sources[]` | 기사/차트/이벤트 근거 |

### JSON 예시

```json
{
    "themes": [
        {
            "headline": "금 선물 사상 최고가 경신",
            "description": "지정학 리스크와 금리 인하 기대로...",
            "related_news": [{"pk": "id#9e48...", "title": "Gold Rises..."}]
        }
    ],
    "nutshell": "12월 연준 금리인하 베팅에 스몰캡이 이끄는 3일째 랠리",
    "scripts": [
        {
            "id": 0,
            "speaker": "진행자",
            "text": "12월 22일 장마감 브리핑입니다...",
            "sources": [
                {"type": "article", "pk": "id#...", "title": "..."},
                {"type": "chart", "ticker": "^GSPC", "start_date": "...", "end_date": "..."},
                {"type": "event", "id": "417228", "title": "...", "date": "YYYY-MM-DD"}
            ]
        }
    ]
}
```

---

## 03. 파이프라인 아키텍처

### Closing Briefing 에이전트

당일 뉴스/시장 데이터를 근거로 핵심 테마(1~3개)와 시장 한마디를 만들고, 진행자/해설자 대화 형식의 장마감 대본을 출력합니다.

- **입력**: 시장 지표 + 경제 캘린더 + 뉴스 기사 + FOMC
- **방식**: LangGraph ReAct, LLM이 Tool로 근거를 직접 조회
- **검증**: Critic 에이전트가 환각/시의성/출처 검증 (Tool Calls)
- **출력**: themes[], nutshell, scripts[] (후속 에이전트에게 입력으로)

### 흐름도

```
         START
           │
           ▼
     ┌───────────┐
     │  Caching  │  ← 데이터 로드 (te_calendar_scraper output)
     └─────┬─────┘
           │
           ▼
     ┌───────────┐        ┌─────────────────────────┐
     │  Context  │        │        Tools            │
     │           │        ├─────────────────────────┤
     │ 📄 calendar.json   │ get_macro_indicators    │
     │ 📄 indicators.csv  │ get_calendar_events     │
     │ 📄 news.json       │ get_news_articles       │
     │ 📄 fomc/           │ get_earnings_results    │
     │ 📄 market.json     │ get_fomc_events         │
     │           │◄──────►│ get_market_summary      │
     └─────┬─────┘ tool   │ search_data             │
           │       calls  └─────────────────────────┘
           ▼
     ┌───────────────────┐
     │  Agent (GPT-4o)   │
     │  ReAct + Tool     │
     │  Binding          │
     └─────────┬─────────┘
               │ [OUTPUT]
               ▼
     ┌───────────────────┐
     │ JSON parsing, save│
     └─────────┬─────────┘
               │
       ┌───────┼───────┐
       ▼       ▼       ▼
   ┌───────┐ ┌───────┐ ┌───────┐
   │themes │ │nutshell│ │scripts│
   └───────┘ └───────┘ └───────┘
```

---

## 04. Binded Tools

### 도구 목록

| Tool | Parameters | 설명 |
|------|------------|------|
| `get_macro_indicators` | date_range | 거시경제 지표 (CPI, PMI, 금리 등) |
| `get_calendar_events` | date, importance | 경제 캘린더 이벤트 |
| `get_news_articles` | keywords, tickers | 관련 뉴스 기사 |
| `get_earnings_results` | tickers, date | 기업 실적 발표 |
| `get_fomc_events` | date_range | FOMC 일정 및 발언 |
| `get_market_summary` | date | 시장 요약 (지수, 섹터) |
| `search_data` | query | 전체 데이터 검색 |

### 도구 반환값

```json
{
    "data": [...],
    "references": [
        {
            "source_type": "macro_data",
            "source_file": "indicators_US_20251222.csv",
            "quote": "CPI YoY: 3.0%",
            "provider": "TradingEconomics",
            "date": "2025-12-22"
        }
    ]
}
```

---

## 05. 핵심 테마 찾기

### 과정

테마는 빈도 + 근거 탐색 + 가격 검증으로 찾는다.
제목에서 후보를 뽑고, 본문을 읽어 인과를 만들고, OHLCV로 시장 반응을 교차검증해 1~3개로 압축한다.

1. 기사 제목을 전부 스캔해서 후보 테마 발굴
2. 후보 테마의 키워드를 중점으로 관련 기사 풀 구성
3. 관련 기사 풀에서 최소 10개 이상의 본문 분석
4. 후보 테마를 원인-전파-결과(섹터/종목/지수) 형태로 재구성
5. 후보 테마의 움직임을 get_ohlcv로 검증
6. 테마 규칙으로 상위 1~3개 선택

### 핵심 테마 기준

- **뉴스 비중**: 관련 기사/키워드가 충분히 반복되는가
- **시장 반응**: 지수/섹터/대표 종목의 움직임이 실제로 동행하는가
- **설명력**: 다른 테마와 겹치지 않고 왜 올랐/내렸나를 설명하는가

---

## 06. 테마 발굴 상세 흐름

### 1) Title Scan → Candidate Keyword Discovery

```
🤖 LLM action: Detects repeating patterns in titles
   (from 'titles.txt'). Discovers candidate keywords.
   
🔧 Tool: 'count_keyword_frequency(source="titles")'

✓ Checkpoint: Excludes vague 'market overall' or unclear 
  stock impact keywords. Clear cause/subject required.
```

### 2) Candidate Keywords → Relevant Article Pool Construction

```
🤖 LLM action: Links filtered keywords/tickers to group
   relevant articles.
   
🔧 Tool: 'get_news_list(tickers, keywords)'

✓ Checkpoint: Noise reduction via 'AND' filters.
  Creates focused relevant article pool.
```

### 3) Read At Least 10 Articles

```
🤖 LLM action: Reads & summarizes content of min. 10 articles.
   Restructures into "Cause-Propagation-Result" themes.
   
🔧 Tool: 'get_news_content(pks=[...])'

✓ Checkpoint: ≥10 full articles read. Strong explanation 
  for each theme required. Evidence secured.
```

### 4) Cross-Verification with Price/Indicator

```
🤖 LLM action: Re-verifies market movements and provides 
   event context.
   
🔧 Tool: 'get_ohlcv(...)'
🔧 Tool: 'get_calendar(id|date)'

✓ Checkpoint: Validates moves against yesterday's close price.
  Re-confirms news claims with numerical data/events.
```

### 5) Select Top 1~3 Themes using Rules

```
🤖 LLM action: Compresses themes into 1~3 distinct ones 
   based on final rules.

✓ Checkpoint: Distinct themes, market impact explainable.
  Commodity/crypto standalone themes prohibited.
  Macro events (FED, etc.) highly sensitive. Finalized Themes.

📋 Output: Top 1~3 Confirmed Themes 
   (Headline, Description, Related News, Verification Evidence)
```

---

## 07. 스크립트 생성

### Script Writer Node

진행자/해설자 대화 형식의 스크립트를 생성합니다.

```
입력:
- themes[] (핵심 테마)
- nutshell (한줄 요약)
- sources (원본 데이터)

출력:
- scripts[] (대화 형식 대본)
  - id: 순서
  - speaker: "진행자" | "해설자"
  - text: 대사
  - sources: [출처 배열]
```

### 스크립트 구조

```json
{
    "scripts": [
        {
            "id": 0,
            "speaker": "진행자",
            "text": "12월 22일 장마감 브리핑입니다. 오늘 뉴욕 증시는...",
            "sources": []
        },
        {
            "id": 1,
            "speaker": "해설자",
            "text": "오늘 시장을 한마디로 정리하면 기록적 금값과 AI 랠리...",
            "sources": [
                {"type": "chart", "ticker": "^GSPC", ...},
                {"type": "article", "pk": "id#...", "title": "..."}
            ]
        }
    ]
}
```

---

## 08. Critic & Revision

### Critic 에이전트

스크립트의 사실 정확성을 검증합니다.

```
검증 항목:
1. 환각(Hallucination): 출처 없는 주장 탐지
2. 시의성(Timeliness): 오래된 정보 사용 여부
3. 정보 가치(Value): 대상 독자에게 유용한가
4. 출처 명시(Citation): sources[] 완전성

도구 사용:
- LLM이 Tool Calls로 원본 데이터 직접 조회
- 스크립트 주장 vs 원본 데이터 대조

출력:
- CriticFeedback {
    hallucinations_found: [],
    overall_quality: "우수|양호|보통|미흡|심각",
    specific_suggestions: [],
    needs_revision: bool
  }
```

### Revision Writer

Critic 피드백을 반영하여 스크립트를 수정합니다.

```
입력:
- script_draft (초안)
- critic_feedback (피드백)

처리:
- 환각 제거
- 출처 누락 보완
- 표현 개선

출력:
- script_revised (수정본)

반복:
- needs_revision = true → Critic 재검증
- max_iterations 도달 → 종료
```

---

## 09. Source Types

### 출처 유형

| Type | 식별자 | 설명 | 예시 |
|------|--------|------|------|
| `article` | `pk` | 뉴스 기사 | `{"type": "article", "pk": "id#9e48...", "title": "Gold Rises..."}` |
| `chart` | `ticker` | 시장 데이터 | `{"type": "chart", "ticker": "^GSPC", "start_date": "2025-12-19", "end_date": "2025-12-22"}` |
| `event` | `id` | 경제 이벤트 | `{"type": "event", "id": "387585", "title": "GDP Growth Rate QoQ", "date": "2025-12-23"}` |

### 출처 검증

후속 Validation Agent에서 각 출처의 실제 존재 여부를 검증합니다.

---

## 10. 데이터 소스

### te_calendar_scraper 출력

```
te_calendar_scraper/output/
├── calendar/                    # 경제 일정
│   └── calendar_US_20251222.csv
├── indicators/                  # 거시경제 지표
│   └── indicators_US_20251222.csv
├── fomc_press_conferences/      # FOMC 기자회견
│   └── 2024_dec_17-18_press_conference.pdf
└── speeches_transcripts/        # 연준 연설문
    └── 2024-12-20_powell_remarks.html
```

### 추가 데이터 소스

| 소스 | 형식 | 내용 |
|------|------|------|
| DynamoDB | JSON | 뉴스 기사 (pk, title, content, provider) |
| Market API | JSON | 시장 요약 (indices, sectors, movers) |
| Earnings | JSON | 기업 실적 (ticker, EPS, revenue) |

---

## 11. 출력 파일

### 최종 출력

```
output/
├── closing_briefing_20251222.json      # 전체 구조화 출력
├── closing_briefing_20251222.md        # 마크다운 대본
└── closing_briefing_20251222_meta.json # 메타데이터
```

### JSON 출력 구조

```json
{
    "date": "20251222",
    "nutshell": "기록적 금값과 AI 랠리 속 선택적 강세장",
    "themes": [...],
    "scripts": [...],
    "metadata": {
        "generated_at": "2025-12-22T18:30:00Z",
        "model": "gpt-4o",
        "iterations": 2,
        "sources_used": 47
    }
}
```

---

## 12. 요약

### Closing Briefing 파이프라인

```
1. 데이터 수집
   te_calendar_scraper → calendar, indicators, FOMC
   DynamoDB → news articles
   Market API → market summary

2. 테마 발굴 (LLM + Tool Calls)
   Title Scan → Keyword Discovery → Article Pool
   → Theme Construction → Price Verification
   → Top 1~3 Themes

3. 스크립트 생성 (LLM + Tool Calls)
   themes + nutshell + sources
   → 진행자/해설자 대화 형식
   → sources[] 출처 첨부

4. 검증 & 수정 (Critic + Revision)
   환각/시의성/출처 검증
   → 피드백 반영 수정
   → 반복 (max 3회)

5. 출력
   JSON (구조화) + Markdown (대본)
```

### 핵심 특징

- **Tool Binding**: LLM이 직접 데이터 조회
- **Source Tracking**: 모든 주장에 출처 첨부
- **Critic Loop**: 자동 검증 및 수정
- **Structured Output**: 후속 에이전트 입력 호환

