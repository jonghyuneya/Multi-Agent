# TradingEconomics 경제 캘린더 & 지표 스크래퍼

이 문서는 `te_calendar_scraper/` 폴더의 코드를 기반으로, 해당 CLI 기반 스크래퍼의 동작을 정리한 것입니다.

이 스크래퍼는 **TradingEconomics 웹사이트**와 **Federal Reserve 웹사이트**에서 경제 일정, 거시경제 지표, FOMC 기자회견 자료를 수집합니다.

---

## 전체 아키텍처 개요

- **실행 방식**
    - CLI 명령어: `python -m te_calendar_scraper.main --mode <mode>`
    - 지원 모드: `dom`, `xhr`, `indicators`, `fomc`, `speeches`, `parse`

- **엔트리포인트**
    - 메인 파일: `te_calendar_scraper/main.py`
    - 비동기 실행: `asyncio.run(main_async(mode))`

- **외부 의존성**
    - `playwright`: 브라우저 자동화 (DOM/XHR 모드, Speeches 모드)
    - `requests`: HTTP 요청 (Indicators, FOMC 모드)
    - `BeautifulSoup`: HTML 파싱
    - `pandas`: CSV 저장

- **주요 출력 디렉토리**
    - `output/calendar/`: 경제 캘린더 CSV
    - `output/indicators/`: 거시경제 지표 CSV
    - `output/fomc_press_conferences/`: FOMC 기자회견 PDF
    - `output/speeches_transcripts/`: 연준 연설문 HTML

---

## 실행 모드별 동작

### 1. DOM 모드 (`--mode dom`)

TradingEconomics 캘린더 페이지를 Playwright 브라우저로 렌더링하여 DOM에서 직접 이벤트를 추출합니다.

```bash
python -m te_calendar_scraper.main --mode dom
```

**동작 흐름:**

1. `playwright_driver.with_browser()` → 헤드리스 브라우저 시작
2. `calendar_dom.goto_calendar(page)` → 캘린더 페이지 이동
3. `calendar_dom.apply_filters(page, ...)` → 쿠키로 필터 적용 (국가, 날짜 범위, 중요도)
4. `calendar_dom.load_all_rows(page)` → "Load More" 버튼 클릭하여 모든 행 로드
5. `calendar_dom.extract_rows_from_dom(page)` → DOM에서 `CalendarRow` 추출
6. `filter_rows(rows)` → 날짜 범위 및 중요도 필터링
7. `save_csv.save_calendar_csv(rows, ...)` → CSV 저장

**필터 설정 (config.py):**

```python
COUNTRY = "United States"
IMPACT_ALLOWED = {1, 2, 3}  # 중요도 1, 2, 3만 수집
```

---

### 2. XHR 모드 (`--mode xhr`)

DOM 모드와 유사하지만, XHR 엔드포인트를 직접 호출하여 캘린더 데이터를 가져옵니다.

```bash
python -m te_calendar_scraper.main --mode xhr
```

**동작 흐름:**

1. `calendar_xhr.discover_calendar_xhr(page)` → XHR URL 템플릿 탐지
2. `calendar_xhr.build_cookie_payload(...)` → 쿠키 페이로드 생성
3. `calendar_xhr.fetch_calendar_rows(url_template, cookies)` → XHR 호출
4. `filter_rows(rows)` → 필터링
5. `save_csv.save_calendar_csv(rows, ...)` → CSV 저장

---

### 3. Indicators 모드 (`--mode indicators`)

TradingEconomics의 내부 API를 리버스 엔지니어링하여 거시경제 지표를 수집합니다.

```bash
python -m te_calendar_scraper.main --mode indicators
```

**동작 흐름:**

1. `indicators_dom.collect_indicators()` → 모든 설정된 지표 수집
2. 각 지표에 대해:
   - `_fetch_series(symbol)` → CloudFront CDN에서 인코딩된 데이터 가져오기
   - `_decode_payload(text)` → Base64 → XOR → Deflate 디코딩
   - `_extract_latest_row(target)` → 최신 값 추출
3. `save_csv.save_indicators_csv(rows, ...)` → CSV 저장

**수집 대상 지표:**

| 버킷 | 지표명 | 심볼 |
|------|--------|------|
| CPI | CPI YoY | `cpi yoy` |
| CPI | CPI MoM | `unitedstainfratmom` |
| CPI | Core CPI YoY | `usacorecpirate` |
| CPI | Core CPI MoM | `usacirm` |
| EIA | Crude Oil Inventories | `unitedstacruoilstoch` |
| EIA | Gasoline Inventories | `unitedstagasstocha` |
| EIA | Distillate Inventories | `unitedstadissto` |
| EIA | Natural Gas Storage | `unitedstanatgasstoch` |
| UST | US 3M Yield | `usgg3m:ind` |
| UST | US 2Y Yield | `usgg2yr:ind` |
| UST | US 5Y Yield | `usgg5yr:ind` |
| UST | US 10Y Yield | `usgg10yr:ind` |
| UST | US 30Y Yield | `usgg30y:ind` |
| ISM | ISM Manufacturing PMI | `unitedstamanpmi` |
| ISM | ISM Services PMI | `unitedstaserpmi` |
| ISM | ISM Composite PMI | `unitedstacompmi` |

**페이로드 디코딩 방식:**

```python
def _decode_payload(text: str) -> Optional[dict]:
    raw = base64.b64decode(text)
    key_bytes = "tradingeconomics-charts-core-api-key".encode()
    xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
    inflated = zlib.decompress(xored, 31).decode("utf-8")
    return json.loads(inflated)
```

---

### 4. FOMC 모드 (`--mode fomc`)

Federal Reserve 웹사이트에서 최근 FOMC 기자회견 PDF를 다운로드합니다.

```bash
python -m te_calendar_scraper.main --mode fomc
```

**동작 흐름:**

1. `fomc_scraper.fetch_calendar_html()` → FOMC 캘린더 페이지 가져오기
2. `fomc_scraper.parse_calendar_for_meetings(html)` → 회의 목록 파싱
3. 각 회의에 대해:
   - `extract_transcript_from_meeting_page(material)` → PDF URL 추출
4. 최근 N개 (기본: 10개)로 필터링
5. `download_recent_transcripts(transcripts)` → PDF 다운로드

**다운로드 파일명 형식:**

```
{year}_{month_abbr}_{dates}_press_conference.pdf
예: 2024_dec_17-18_press_conference.pdf
```

**출력 디렉토리:** `output/fomc_press_conferences/`

---

### 5. Speeches 모드 (`--mode speeches`)

Federal Reserve 연설문 페이지에서 연설 transcript를 다운로드합니다.

```bash
python -m te_calendar_scraper.main --mode speeches
```

**동작 흐름:**

1. `speeches_scraper.scrape_speeches(page)` → 연설 목록 스크래핑
2. 각 연설에 대해:
   - HTML transcript 페이지 다운로드
3. `output/speeches_transcripts/`에 저장

---

### 6. Parse 모드 (`--mode parse`)

저장된 CSV 파일들의 요약 정보를 출력합니다.

```bash
python -m te_calendar_scraper.main --mode parse
```

---

## 외부 사이트 크롤링

### TradingEconomics Calendar

- **대상 URL**: `https://tradingeconomics.com/calendar`
- **필터 방식**: 쿠키 기반 (`calendar-countries`, `calendar-importance`, `cal-custom-range`)
- **주요 선택자**:
    - 행: `#calendar tr[data-country]`
    - 시간: `td:nth-of-type(1) span`
    - 제목: `td:nth-of-type(3) a.calendar-event`
    - 카테고리: `td:nth-of-type(3)`

### TradingEconomics Indicators (CloudFront CDN)

- **대상 URL**: `https://d3ii0wo49og5mi.cloudfront.net/economics/<symbol>`
- **인증 방식**: `key=20240229:nazare` 파라미터
- **응답 형식**: Base64 인코딩 → XOR 난독화 → Deflate 압축 → JSON

### Federal Reserve FOMC Calendar

- **대상 URL**: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- **크롤링 방식**: `requests` + `BeautifulSoup`
- **수집 대상**: Press Conference Transcript PDF

### Federal Reserve Speeches

- **대상 URL**: `https://www.federalreserve.gov/newsevents/speeches.htm`
- **크롤링 방식**: Playwright + `BeautifulSoup`
- **수집 대상**: Transcript HTML 페이지

---

## 데이터 모델

### CalendarRow

경제 캘린더 이벤트를 나타내는 데이터 클래스입니다.

```python
@dataclass(slots=True)
class CalendarRow:
    dt_utc: Optional[datetime]      # UTC 시간
    dt_kst: Optional[datetime]      # KST 시간
    title: str                       # 이벤트 제목
    category: Optional[str]          # 카테고리 (Interest Rate, Employment 등)
    impact: Optional[int]            # 중요도 (1, 2, 3)
    country: Optional[str]           # 국가
    raw_time_text: Optional[str]     # 원본 시간 텍스트
    source_url: Optional[str]        # 출처 URL
```

### IndicatorRow

거시경제 지표 값을 나타내는 데이터 클래스입니다.

```python
@dataclass(slots=True)
class IndicatorRow:
    indicator_bucket: str            # 버킷 (CPI, UST, ISM 등)
    indicator_name: str              # 지표명
    latest_value: Optional[str]      # 최신 값
    unit: Optional[str]              # 단위
    day_change: Optional[str]        # 일간 변화
    month_change: Optional[str]      # 월간 변화
    year_change: Optional[str]       # 연간 변화
    obs_date: Optional[str]          # 관측 날짜
    source_url: Optional[str]        # 출처 URL
    raw_source_note: Optional[str]   # 원본 메모
```

### TranscriptMaterial

FOMC 기자회견 자료를 나타내는 데이터 클래스입니다.

```python
@dataclass
class TranscriptMaterial:
    year: int                                    # 연도
    month: str                                   # 월
    dates: str                                   # 날짜 (예: "28-29")
    press_conference_pdf_url: Optional[str]      # PDF URL
    meeting_page_url: Optional[str]              # 회의 페이지 URL
    release_date: Optional[datetime]             # 공개 날짜
```

### Speech

연준 연설을 나타내는 데이터 클래스입니다.

```python
@dataclass
class Speech:
    title: str                       # 연설 제목
    speaker: str                     # 연설자
    date: Optional[str]              # 날짜
    transcript_url: Optional[str]    # Transcript URL
    source_url: Optional[str]        # 출처 URL
```

---

## CSV 출력 스키마

### Calendar CSV

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `datetime_utc` | String | UTC ISO8601 시간 | `2025-11-13T13:30:00+00:00` |
| `datetime_kst` | String | KST ISO8601 시간 | `2025-11-13T22:30:00+09:00` |
| `title` | String | 이벤트 제목 | `CPI YoY` |
| `category` | String | 카테고리 | `Inflation` |
| `impact` | Integer | 중요도 (1-3) | `3` |
| `country` | String | 국가 | `United States` |
| `raw_time_text` | String | 원본 시간 텍스트 | `08:30 AM` |
| `source_url` | String | TradingEconomics URL | `https://tradingeconomics.com/...` |

**파일명 형식:** `calendar_US_{start_date}_{end_date}.csv`

**예:** `calendar_US_20251112_20251126.csv`

### Indicators CSV

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `indicator_bucket` | String | 지표 버킷 | `CPI`, `UST`, `ISM` |
| `indicator_name` | String | 지표명 | `US 10Y Yield` |
| `latest_value` | String | 최신 값 | `4.08` |
| `unit` | String | 단위 | `percent`, `points` |
| `day_change` | String | 일간 변화 | `0.02` |
| `month_change` | String | 월간 변화 | `-0.15` |
| `year_change` | String | 연간 변화 | `0.5` |
| `obs_date` | String | 관측 날짜 | `2025-11-13` |
| `source_url` | String | TradingEconomics URL | `https://tradingeconomics.com/...` |
| `raw_source_note` | String | 원본 메모 | `symbol=usgg10yr:ind; points=12` |

**파일명 형식:** `indicators_US_{date}.csv`

**예:** `indicators_US_20251113.csv`

---

## FOMC PDF 파일 구조

### 저장 위치

```
output/fomc_press_conferences/
├── 2024_dec_17-18_press_conference.pdf
├── 2024_nov_6-7_press_conference.pdf
├── 2024_sep_17-18_press_conference.pdf
└── ...
```

### 파일명 형식

```
{year}_{month_abbr}_{dates}_press_conference.pdf
```

| 구성요소 | 설명 | 예시 |
|----------|------|------|
| `year` | 4자리 연도 | `2024` |
| `month_abbr` | 월 약어 (소문자) | `jan`, `feb`, `dec` |
| `dates` | 회의 날짜 | `17-18`, `28-29` |

---

## Speeches HTML 파일 구조

### 저장 위치

```
output/speeches_transcripts/
├── 2025_01_15_Governor_Bowman_Speech_Title.html
├── 2025_01_10_Chair_Powell_Economic_Outlook.html
└── ...
```

### 파일명 형식

```
{date}_{speaker}_{title}.html
```

---

## 설정 (config.py)

### 주요 설정 값

```python
# 대상 국가 및 중요도
COUNTRY = "United States"
IMPACT_ALLOWED = {1, 2, 3}

# 타임존
TZ_DISPLAY = "Asia/Seoul"
SITE_TIMEZONE_HINT = "UTC"

# TradingEconomics API
TE_CHARTS_DATASOURCE = "https://d3ii0wo49og5mi.cloudfront.net"
TE_CHARTS_TOKEN = "20240229:nazare"
TE_OBFUSCATION_KEY = "tradingeconomics-charts-core-api-key"

# Federal Reserve URLs
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_SPEECHES_URL = "https://www.federalreserve.gov/newsevents/speeches.htm"

# 출력 디렉토리
OUTPUT_DIR = PROJECT_ROOT / "output"
CALENDAR_OUTPUT_DIR = OUTPUT_DIR / "calendar"
INDICATOR_OUTPUT_DIR = OUTPUT_DIR / "indicators"
FOMC_DOWNLOADS_DIR = OUTPUT_DIR / "fomc_press_conferences"
SPEECHES_DOWNLOADS_DIR = OUTPUT_DIR / "speeches_transcripts"
```

### Playwright 설정

```python
PLAYWRIGHT_HEADLESS = True
PLAYWRIGHT_VIEWPORT = {"width": 1440, "height": 900}
PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
```

---

## 에러 처리 및 멱등성

### 멱등성 보장

- **CSV 저장 시**: `dedupe.dedupe_by_key()` 함수로 중복 제거
    - Calendar: `(datetime_kst, title, source_url)` 키 기준
- **PDF 다운로드 시**: 파일이 이미 존재하면 스킵
- **HTML 다운로드 시**: 파일이 이미 존재하면 스킵

### 실패 처리

- 네트워크 요청 실패: 로그 출력 후 다음 항목 진행
- 페이로드 디코딩 실패: `raw_source_note`에 에러 메시지 기록
- 다운로드 실패: 결과 요약에 `failed` 카운트로 표시

---

## 요약

- 이 스크래퍼는 **TradingEconomics**와 **Federal Reserve** 웹사이트에서 다음 데이터를 수집합니다:
    - **경제 캘린더**: 미국 경제 이벤트 (CPI, FOMC, 고용지표 등)
    - **거시경제 지표**: CPI, PMI, 국채 금리 등 실시간 값
    - **FOMC 기자회견**: Press Conference Transcript PDF
    - **연준 연설문**: Speech Transcript HTML

- 출력 형식:
    - **Calendar/Indicators**: CSV 파일 (pandas DataFrame)
    - **FOMC**: PDF 파일
    - **Speeches**: HTML 파일

- 날짜 범위: 현재 날짜 기준 ±7일 (rolling window)

- 중복 방지: 키 기반 dedupe 및 파일 존재 여부 체크

