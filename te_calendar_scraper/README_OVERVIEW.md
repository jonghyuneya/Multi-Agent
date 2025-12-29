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

## CLI 핸들러 동작 흐름

핸들러: `te_calendar_scraper/main.py`

```python
async def main_async(mode: str) -> None:
    if mode == "dom":
        rows = await run_dom_mode()
        start_kst, end_kst = date_window_kst()
        output_path = save_csv.save_calendar_csv(rows, start_kst, end_kst)
        print(f"Saved {len(rows)} rows to {output_path}")

    elif mode == "xhr":
        rows = await run_xhr_mode()
        start_kst, end_kst = date_window_kst()
        output_path = save_csv.save_calendar_csv(rows, start_kst, end_kst)

    elif mode == "indicators":
        indicator_rows: List[IndicatorRow] = indicators_dom.collect_indicators()
        today_kst = datetime.now(tz_kst).date()
        output_path = save_csv.save_indicators_csv(
            [asdict(row) for row in indicator_rows],
            today_kst,
        )

    elif mode == "fomc":
        await run_fomc_mode()

    elif mode == "speeches":
        await run_speeches_mode()

    elif mode == "parse":
        await run_parse_output_mode()
```

- **날짜 윈도우 (`date_window_kst`)**
    - `main.py`의 `date_window_kst()` 함수로 수집 범위 결정
    - 현재 날짜(KST) 기준 **±7일** (rolling window)
    
    ```python
    def date_window_kst() -> tuple[datetime, datetime]:
        tz_kst = pytz.timezone("Asia/Seoul")
        now_kst = datetime.now(tz_kst)
        start = (now_kst - timedelta(days=7)).replace(hour=0, minute=0, second=0)
        end = (now_kst + timedelta(days=7)).replace(hour=23, minute=59, second=59)
        return start, end
    ```

- **행 필터링 (`filter_rows`)**
    - 국가, 중요도, 날짜 범위로 필터링
    
    ```python
    def filter_rows(rows: Iterable[CalendarRow]) -> List[dict]:
        start_kst, end_kst = date_window_kst()
        filtered = []
        for row in rows:
            if row.country and row.country != config.COUNTRY:
                continue  # 국가 필터: "United States"만
            if row.impact and row.impact not in config.IMPACT_ALLOWED:
                continue  # 중요도 필터: {1, 2, 3}만
            dt_kst = row.dt_kst or parse_utils.to_kst(row.dt_utc)
            if not dt_kst or not (start_kst <= dt_kst <= end_kst):
                continue  # 날짜 범위 필터
            filtered.append({...})
        return filtered
    ```

---

## 외부 사이트 크롤링: TradingEconomics Calendar

### 목록 크롤링 (`scraper/calendar_dom.py`)

- 대상 URL: `https://tradingeconomics.com/calendar`
- HTTP 클라이언트: Playwright (헤드리스 Chrome)
- 필터 방식: **쿠키 기반** (URL 파라미터가 아님)
- User-Agent: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36`

- 주요 선택자:
    - 행 선택: `#calendar tr[data-country]`
    - 시간: `td:nth-of-type(1) span`
    - 제목: `td:nth-of-type(3) a.calendar-event`
    - 카테고리: `row.get_attribute("data-category")`
    - 국가: `row.get_attribute("data-country")`
    - 중요도: `span` 태그의 `class` 속성에서 `calendar-date-{N}` 또는 `importance-{N}` 추출

### 쿠키 필터 적용 (`calendar_dom.apply_filters`)

```python
async def apply_filters(
    page: Page,
    country: str,              # "United States"
    start_date: date,          # 2025-12-21
    end_date: date,            # 2026-01-04
    impacts: Iterable[int],    # {1, 2, 3}
) -> None:
    # 국가명 → 쿠키값 변환: "United States" → "usa"
    country_cookie = _country_to_cookie(country)
    
    # 중요도 → 쉼표 구분 문자열: {1, 2, 3} → "1,2,3"
    impacts_cookie = ",".join(str(i) for i in sorted(set(impacts)))
    
    # 날짜 범위 → 파이프 구분 문자열: "2025-12-21|2026-01-04"
    custom_range = f"{start_date:%Y-%m-%d}|{end_date:%Y-%m-%d}"

    await page.context.add_cookies([
        {
            "name": "calendar-countries",
            "value": country_cookie,           # "usa"
            "domain": "tradingeconomics.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "None",
        },
        {
            "name": "calendar-importance",
            "value": impacts_cookie,           # "1,2,3"
            "domain": "tradingeconomics.com",
            ...
        },
        {
            "name": "calendar-range",
            "value": "0",                      # custom range 사용 표시
            ...
        },
        {
            "name": "cal-custom-range",
            "value": custom_range,             # "2025-12-21|2026-01-04"
            ...
        },
    ])
    await page.reload(wait_until="domcontentloaded")
```

### DOM 추출 (`calendar_dom.extract_rows_from_dom`)

```python
async def extract_rows_from_dom(page: Page) -> List[CalendarRow]:
    row_locator = page.locator("#calendar tr[data-country]")
    row_count = await row_locator.count()
    
    for idx in range(row_count):
        row = row_locator.nth(idx)
        
        # data-id 속성이 있는 행만 처리 (헤더 행 제외)
        if not await _is_data_row(row):
            continue

        # 날짜 추출: td 첫 번째 셀의 class 속성에서 ISO 날짜 추출
        # 예: class="themark 2025-12-23 ..." → date(2025, 12, 23)
        event_date = await _extract_row_date(row)

        # 시간: "08:30 AM" 형식
        raw_time = await parse_utils.locator_text(row, "td:nth-of-type(1) span")

        # 제목: 이벤트 링크 텍스트
        title = await parse_utils.locator_text(row, "td:nth-of-type(3) a.calendar-event")

        # 카테고리/국가: data-* 속성에서 추출
        category_attr = await row.get_attribute("data-category")  # "interest rate"
        category = category_attr.title()  # "Interest Rate"
        
        country_attr = await row.get_attribute("data-country")    # "united states"
        country = country_attr.title()  # "United States"

        # 중요도: bull 아이콘 개수 (CSS class에서 추출)
        impact_value = await parse_utils.extract_impact(row, "td:nth-of-type(1) span")

        # URL: 이벤트 상세 페이지 링크
        source_url = await parse_utils.locator_href(row, "td:nth-of-type(3) a.calendar-event")
        source_url = urljoin("https://tradingeconomics.com/calendar", source_url)

        # UTC/KST 시간 변환
        context_dt = datetime.combine(event_date, time.min)
        dt_utc = parse_utils.parse_time_to_utc(raw_time, context_dt)
        dt_kst = parse_utils.to_kst(dt_utc)

        rows.append(CalendarRow(
            dt_utc=dt_utc,
            dt_kst=dt_kst,
            title=title,
            category=category,
            impact=impact_value,
            country=country,
            raw_time_text=raw_time,
            source_url=source_url,
        ))
```

### 날짜 추출 (`_extract_row_date`)

```python
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

async def _extract_row_date(row: Locator) -> Optional[date]:
    """td 첫 번째 셀의 class 속성에서 ISO 날짜 추출"""
    first_cell = row.locator("td").first
    class_attr = await first_cell.get_attribute("class") or ""
    # 예: class="themark 2025-12-23 calendar-date-3"
    
    match = _DATE_PATTERN.search(class_attr)
    if not match:
        return None
    # "2025-12-23" → date(2025, 12, 23)
    return datetime.strptime(match.group(), "%Y-%m-%d").date()
```

### 중요도 추출 (`_extract_impact`)

```python
def _extract_impact(time_span) -> Optional[int]:
    """span 태그의 class에서 중요도 숫자 추출"""
    class_tokens = time_span.get("class", [])
    # 예: ["calendar-date-3", "importance-3"]
    
    for token in class_tokens:
        if token.startswith("calendar-date-"):
            suffix = token.split("-")[-1]  # "3"
            if suffix.isdigit():
                return int(suffix)  # 3
        if token.startswith("importance-"):
            suffix = token.split("-")[-1]
            if suffix.isdigit():
                return int(suffix)
    return None
```

반환되는 각 캘린더 항목 구조:

```python
@dataclass(slots=True)
class CalendarRow:
    dt_utc: Optional[datetime]      # 2025-12-23T13:30:00+00:00
    dt_kst: Optional[datetime]      # 2025-12-23T22:30:00+09:00
    title: str                      # "CPI YoY"
    category: Optional[str]         # "Inflation"
    impact: Optional[int]           # 3
    country: Optional[str]          # "United States"
    raw_time_text: Optional[str]    # "08:30 AM"
    source_url: Optional[str]       # "https://tradingeconomics.com/united-states/inflation-cpi"
```

---

## 외부 사이트 크롤링: TradingEconomics Indicators

### CloudFront CDN API (`scraper/indicators_dom.py`)

TradingEconomics의 내부 API를 **리버스 엔지니어링**하여 거시경제 지표를 수집합니다.

- 대상 URL: `https://d3ii0wo49og5mi.cloudfront.net/economics/<symbol>`
- 인증 토큰: `key=20240229:nazare`
- 응답 형식: **Base64 인코딩 → XOR 난독화 → Deflate 압축 → JSON**

### 페이로드 디코딩 알고리즘 (`_decode_payload`)

```python
def _decode_payload(text: str) -> Optional[dict]:
    """TradingEconomics series 페이로드 디코딩"""
    
    # Step 1: Base64 디코드
    raw = base64.b64decode(text)
    
    # Step 2: XOR 복호화
    # 키: "tradingeconomics-charts-core-api-key" (35바이트)
    key_bytes = "tradingeconomics-charts-core-api-key".encode()
    xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(raw))
    
    # Step 3: Deflate 압축 해제 (wbits=31 for gzip)
    inflated = zlib.decompress(xored, 31).decode("utf-8")
    
    # Step 4: JSON 파싱
    return json.loads(inflated)
```

### API 호출 (`_fetch_series`)

```python
def _fetch_series(symbol: str, params: Optional[Dict[str, str]] = None):
    """CloudFront CDN에서 지표 데이터 가져오기"""
    
    # 기본 파라미터
    base_params = {
        "n": "12",                    # 최근 12개 데이터 포인트
        "key": "20240229:nazare",     # 인증 토큰
    }
    
    # 심볼 URL 인코딩 (콜론 유지)
    # "usgg10yr:ind" → "usgg10yr%3Aind"
    encoded_symbol = quote(symbol.lower(), safe=":")
    
    # API URL 구성
    url = f"https://d3ii0wo49og5mi.cloudfront.net/economics/{encoded_symbol}"
    # 예: https://d3ii0wo49og5mi.cloudfront.net/economics/usgg10yr%3Aind?n=12&key=20240229:nazare
    
    resp = requests.get(url, params=base_params, headers={"User-Agent": ...}, timeout=30)
    resp.raise_for_status()
    
    # 응답 디코딩
    decoded = _decode_payload(resp.text)
    # 결과 구조: [{"series": [{"serie": {"data": [[value, ?, ?, date], ...], "unit": "percent", ...}}]}]
    
    serie = decoded[0]["series"][0]["serie"]
    return serie, None
```

### 최신 값 추출 (`_extract_latest_row`)

```python
def _extract_latest_row(target: IndicatorTarget) -> IndicatorRow:
    serie, error = _fetch_series(target.symbol, target.params)
    
    if not serie or error:
        # 실패 시 에러 메시지와 함께 빈 IndicatorRow 반환
        return IndicatorRow(
            indicator_bucket=target.bucket,
            indicator_name=target.name,
            latest_value=None,
            raw_source_note=f"symbol={target.symbol}; {error}",
            ...
        )

    # 데이터 배열에서 최신 값 추출
    data = serie.get("data") or []  # [[4.08, ?, ?, "2025-12-23"], ...]
    if data:
        last_entry = data[-1]       # [4.08, ?, ?, "2025-12-23"]
        latest_value = _format_value(last_entry[0])  # "4.08"
        obs_date = last_entry[3] if len(last_entry) >= 4 else None  # "2025-12-23"

    # 일간 변화 계산 (daily frequency인 경우)
    day_change = _compute_day_change(serie)

    return IndicatorRow(
        indicator_bucket=target.bucket,     # "UST"
        indicator_name=target.name,         # "US 10Y Yield"
        latest_value=latest_value,          # "4.08"
        unit=serie.get("unit"),             # "percent"
        day_change=day_change,              # "0.02"
        obs_date=obs_date,                  # "2025-12-23"
        source_url=target.source_url,
        raw_source_note=f"symbol={target.symbol}; points={len(data)}; frequency={serie.get('frequency')}",
    )
```

### 수집 대상 지표 설정 (`IndicatorTarget`)

```python
@dataclass(frozen=True)
class IndicatorTarget:
    bucket: str      # 버킷 그룹명: "CPI", "UST", "ISM", "EIA"
    name: str        # 지표 표시명: "US 10Y Yield"
    symbol: str      # API 심볼: "usgg10yr:ind"
    source_url: str  # 출처 URL
    params: Optional[Dict[str, str]] = None

# 모든 지표 목록 (16개)
ALL_INDICATOR_TARGETS: Sequence[IndicatorTarget] = (
    # CPI (4개)
    IndicatorTarget(bucket="CPI", name="CPI YoY", symbol="cpi yoy", source_url="https://tradingeconomics.com/united-states/inflation-cpi"),
    IndicatorTarget(bucket="CPI", name="CPI MoM", symbol="unitedstainfratmom", source_url="..."),
    IndicatorTarget(bucket="CPI", name="Core CPI YoY", symbol="usacorecpirate", source_url="..."),
    IndicatorTarget(bucket="CPI", name="Core CPI MoM", symbol="usacirm", source_url="..."),
    
    # EIA (4개)
    IndicatorTarget(bucket="EIA", name="Crude Oil Inventories", symbol="unitedstacruoilstoch", source_url="..."),
    IndicatorTarget(bucket="EIA", name="Gasoline Inventories", symbol="unitedstagasstocha", source_url="..."),
    IndicatorTarget(bucket="EIA", name="Distillate Inventories", symbol="unitedstadissto", source_url="..."),
    IndicatorTarget(bucket="EIA", name="Natural Gas Storage", symbol="unitedstanatgasstoch", source_url="..."),
    
    # UST (5개)
    IndicatorTarget(bucket="UST", name="US 3M Yield", symbol="usgg3m:ind", source_url="..."),
    IndicatorTarget(bucket="UST", name="US 2Y Yield", symbol="usgg2yr:ind", source_url="..."),
    IndicatorTarget(bucket="UST", name="US 5Y Yield", symbol="usgg5yr:ind", source_url="..."),
    IndicatorTarget(bucket="UST", name="US 10Y Yield", symbol="usgg10yr:ind", source_url="..."),
    IndicatorTarget(bucket="UST", name="US 30Y Yield", symbol="usgg30y:ind", source_url="..."),
    
    # ISM (3개)
    IndicatorTarget(bucket="ISM", name="ISM Manufacturing PMI", symbol="unitedstamanpmi", source_url="..."),
    IndicatorTarget(bucket="ISM", name="ISM Services PMI", symbol="unitedstaserpmi", source_url="..."),
    IndicatorTarget(bucket="ISM", name="ISM Composite PMI", symbol="unitedstacompmi", source_url="..."),
)
```

반환되는 각 지표 항목 구조:

```python
@dataclass(slots=True)
class IndicatorRow:
    indicator_bucket: str           # "UST"
    indicator_name: str             # "US 10Y Yield"
    latest_value: Optional[str]     # "4.08"
    unit: Optional[str]             # "percent"
    day_change: Optional[str]       # "0.02"
    month_change: Optional[str]     # None (미구현)
    year_change: Optional[str]      # None (미구현)
    obs_date: Optional[str]         # "2025-12-23"
    source_url: Optional[str]       # "https://tradingeconomics.com/united-states/government-bond-yield"
    raw_source_note: Optional[str]  # "symbol=usgg10yr:ind; points=12; frequency=Daily"
```

---

## 외부 사이트 크롤링: Federal Reserve FOMC

### FOMC 캘린더 스크래핑 (`scraper/fomc_scraper.py`)

- 대상 URL: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- HTTP 클라이언트: `requests` + `BeautifulSoup`
- 수집 대상: **Press Conference Transcript PDF (최근 10개)**

### 메인 흐름 (`scrape_fomc_calendar`)

```python
def scrape_fomc_calendar() -> list[TranscriptMaterial]:
    """FOMC 캘린더에서 최근 기자회견 transcript 수집"""
    
    # 1. 캘린더 페이지 가져오기
    calendar_html = fetch_calendar_html()
    # GET https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
    
    # 2. 회의 목록 파싱 (Press Conference 링크가 있는 회의만)
    meetings = parse_calendar_for_meetings(calendar_html)
    # 예: [TranscriptMaterial(year=2024, month="December", dates="17-18", meeting_page_url="..."), ...]
    
    # 3. 각 회의 페이지에서 PDF URL 추출
    for meeting in meetings:
        extract_transcript_from_meeting_page(meeting)
    
    # 4. PDF가 있는 회의만 필터
    meetings_with_pdf = [m for m in meetings if m.press_conference_pdf_url]
    
    # 5. release_date 기준 정렬 후 최근 10개만
    meetings_with_pdf.sort(key=lambda m: m.release_date, reverse=True)
    recent_transcripts = meetings_with_pdf[:10]
    
    return recent_transcripts
```

### 캘린더 파싱 (`parse_calendar_for_meetings`)

```python
def parse_calendar_for_meetings(calendar_html: str) -> list[TranscriptMaterial]:
    """캘린더 HTML에서 회의 목록 추출"""
    soup = BeautifulSoup(calendar_html, "html.parser")
    
    # 월 패턴
    month_pattern = re.compile(
        r"\b(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\b", re.I
    )
    
    # 연도 패턴: "2024 FOMC Meetings"
    year_pattern = re.compile(r"\b(202[0-7])\s+FOMC\s+Meetings", re.I)
    
    for container in soup.find_all(["tr", "li", "div", "p"]):
        text = container.get_text()
        
        # 연도 헤더 확인
        year_match = year_pattern.search(text)
        if year_match:
            current_year = int(year_match.group(1))  # 2024
            continue
        
        # 월 추출: "December"
        month_match = month_pattern.search(text)
        if not month_match:
            continue
        month = month_match.group(1)  # "December"
        
        # 날짜 추출: "17-18" 또는 "22"
        date_pattern = re.compile(r"\b(\d{1,2}(?:-\d{1,2})?)\b")
        date_match = date_pattern.search(text, month_match.end())
        dates = date_match.group(1)  # "17-18"
        
        # "Press Conference" 링크 찾기
        for link in container.find_all("a", href=True):
            link_text = link.get_text().strip().lower()
            if "press conference" in link_text:
                press_conf_link = urljoin(FOMC_BASE_URL, link.get("href"))
                break
        
        meetings.append(TranscriptMaterial(
            year=current_year,          # 2024
            month=month,                # "December"
            dates=dates,                # "17-18"
            meeting_page_url=press_conf_link,
        ))
```

### PDF URL 추출 (`extract_transcript_from_meeting_page`)

```python
def extract_transcript_from_meeting_page(material: TranscriptMaterial) -> TranscriptMaterial:
    """회의 페이지에서 Press Conference Transcript PDF URL 추출"""
    
    response = requests.get(material.meeting_page_url, headers={"User-Agent": ...})
    soup = BeautifulSoup(response.text, "html.parser")
    
    # 전략 1: "Press Conference Transcript" 링크 찾기
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        link_text = link.get_text().strip().lower()
        
        if ".pdf" in href.lower():
            if "press conference" in link_text or "transcript" in link_text:
                material.press_conference_pdf_url = urljoin(FOMC_BASE_URL, href)
                # 예: "https://www.federalreserve.gov/.../FOMC20241218presconf.pdf"
                break
    
    # 전략 2: 폴백 - 페이지의 첫 번째 PDF 링크
    if not material.press_conference_pdf_url:
        for link in soup.find_all("a", href=True):
            if ".pdf" in link.get("href", "").lower():
                material.press_conference_pdf_url = urljoin(FOMC_BASE_URL, link.get("href"))
                break
    
    # release_date 추출: "Released January 29, 2025 at 2:00 p.m."
    material.release_date = parse_release_date(soup.get_text())
    
    return material
```

### PDF 다운로드 (`download_recent_transcripts`)

```python
def download_recent_transcripts(transcripts: list[TranscriptMaterial]) -> dict[str, int]:
    """PDF 다운로드 (이미 존재하면 스킵)"""
    
    for transcript in transcripts:
        # 파일명 생성
        month_abbrev = {'January': 'jan', 'February': 'feb', ..., 'December': 'dec'}
        month_abbr = month_abbrev.get(transcript.month, transcript.month[:3].lower())
        filename = f"{transcript.year}_{month_abbr}_{transcript.dates}_press_conference.pdf"
        # 예: "2024_dec_17-18_press_conference.pdf"
        
        # 파일 존재 확인
        existing_file = config.FOMC_DOWNLOADS_DIR / filename
        if existing_file.exists():
            stats["skipped"] += 1
            continue
        
        # 다운로드
        result = download_material(transcript.press_conference_pdf_url, config.FOMC_DOWNLOADS_DIR, filename)
        
        if result and result.exists() and result.stat().st_size > 0:
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1
    
    return {"downloaded": N, "skipped": M, "failed": K}
```

반환되는 FOMC 자료 구조:

```python
@dataclass
class TranscriptMaterial:
    year: int                                    # 2024
    month: str                                   # "December"
    dates: str                                   # "17-18"
    press_conference_pdf_url: Optional[str]      # "https://www.federalreserve.gov/.../FOMC20241218presconf.pdf"
    meeting_page_url: Optional[str]              # "https://www.federalreserve.gov/monetarypolicy/fomcpresconf20241218.htm"
    release_date: Optional[datetime]             # datetime(2025, 1, 29)
```

---

## CSV 스키마 구조

### Calendar CSV

`io/save_csv.py`의 `save_calendar_csv()`에서 저장:

| 필드명 | 타입 | 설명 | 예시 값 |
| --- | --- | --- | --- |
| `datetime_utc` | String | UTC ISO8601 시간 | `2025-12-23T13:30:00+00:00` |
| `datetime_kst` | String | KST ISO8601 시간 | `2025-12-23T22:30:00+09:00` |
| `title` | String | 이벤트 제목 | `CPI YoY` |
| `category` | String | 카테고리 | `Inflation`, `Interest Rate` |
| `impact` | Integer | 중요도 (1-3) | `3` |
| `country` | String | 국가 | `United States` |
| `raw_time_text` | String | 원본 시간 텍스트 | `08:30 AM` |
| `source_url` | String | TradingEconomics URL | `https://tradingeconomics.com/united-states/inflation-cpi` |

- **파일명 형식**: `calendar_US_{start_date}_{end_date}.csv`
- **예**: `calendar_US_20251221_20260104.csv`
- **중복 제거 키**: `(datetime_kst, title, source_url)`

### 저장 흐름 (`save_calendar_csv`)

```python
def save_calendar_csv(rows: Iterable[dict], start_date, end_date) -> Path:
    # 1. 중복 제거 (키 기반)
    unique_rows = dedupe.dedupe_by_key(rows, keys=("datetime_kst", "title", "source_url"))
    
    # 2. ISO 포맷 변환
    prepared_rows = prepare_rows_for_csv(unique_rows)
    
    # 3. DataFrame 생성 및 정렬
    df = pd.DataFrame(prepared_rows)
    df.sort_values(by=["datetime_kst", "title"], inplace=True, ignore_index=True)
    
    # 4. 파일 저장
    file_name = f"calendar_US_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    # 예: "calendar_US_20251221_20260104.csv"
    
    output_path = config.CALENDAR_OUTPUT_DIR / file_name
    # output/calendar/calendar_US_20251221_20260104.csv
    
    df.to_csv(output_path, index=False)
    return output_path
```

### 중복 제거 (`io/dedupe.py`)

```python
def dedupe_by_key(rows: Iterable[dict], keys: Sequence[str]) -> List[dict]:
    """복합 키 기준으로 중복 제거"""
    seen: set[Tuple] = set()
    unique_rows: List[dict] = []
    
    for row in rows:
        # 키 생성: (datetime_kst, title, source_url)
        key = tuple(row.get(k) for k in keys)
        
        if key in seen:
            continue  # 이미 본 행은 스킵
        
        seen.add(key)
        unique_rows.append(row)
    
    return unique_rows
```

---

### Indicators CSV

`io/save_csv.py`의 `save_indicators_csv()`에서 저장:

| 필드명 | 타입 | 설명 | 예시 값 |
| --- | --- | --- | --- |
| `indicator_bucket` | String | 지표 버킷 | `CPI`, `UST`, `ISM`, `EIA` |
| `indicator_name` | String | 지표명 | `US 10Y Yield` |
| `latest_value` | String | 최신 값 | `4.08` |
| `unit` | String | 단위 | `percent`, `points` |
| `day_change` | String | 일간 변화 | `0.02` |
| `month_change` | String | 월간 변화 | (현재 빈 문자열) |
| `year_change` | String | 연간 변화 | (현재 빈 문자열) |
| `obs_date` | String | 관측 날짜 | `2025-12-23` |
| `source_url` | String | TradingEconomics URL | `https://tradingeconomics.com/...` |
| `raw_source_note` | String | 디버그 정보 | `symbol=usgg10yr:ind; points=12; frequency=Daily` |

- **파일명 형식**: `indicators_US_{date}.csv`
- **예**: `indicators_US_20251228.csv`
- **정렬 기준**: `(indicator_bucket, indicator_name)`

---

## 파일 출력 구조

```
te_calendar_scraper/output/
├── calendar/
│   ├── calendar_US_20251221_20260104.csv   # 163 rows
│   └── calendar_US_20251214_20251228.csv
│
├── indicators/
│   ├── indicators_US_20251228.csv          # 16 rows (CPI×4 + EIA×4 + UST×5 + ISM×3)
│   └── indicators_US_20251227.csv
│
├── fomc_press_conferences/
│   ├── 2024_dec_17-18_press_conference.pdf
│   ├── 2024_nov_6-7_press_conference.pdf
│   ├── 2024_sep_17-18_press_conference.pdf
│   └── ... (최근 10개)
│
└── speeches_transcripts/
    ├── 2025_01_15_Governor_Bowman_Economic_Outlook.html
    └── ...
```

---

## 에러 처리 및 멱등성

### 멱등성 보장

- **Calendar CSV 저장 시**
    - `dedupe.dedupe_by_key(rows, keys=("datetime_kst", "title", "source_url"))` 호출
    - 동일한 (시간, 제목, URL) 조합은 한 번만 저장

- **PDF/HTML 다운로드 시**
    - `output_path.exists()` 체크로 이미 존재하는 파일은 스킵
    - 결과에 `skipped` 카운트로 표시

### 실패 처리

- **Indicators API 실패**
    - `_fetch_series()` 반환값: `(None, "request-error: ...")`
    - `IndicatorRow.raw_source_note`에 에러 메시지 기록
    - 다음 지표로 진행 (전체 프로세스 중단하지 않음)

- **FOMC 다운로드 실패**
    - `download_material()` 반환값: `None`
    - 결과에 `failed` 카운트로 표시
    - 다음 transcript로 진행

```python
# indicators_dom.py
def _fetch_series(symbol: str, ...) -> tuple[Optional[dict], Optional[str]]:
    try:
        resp = requests.get(url, ...)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Request error for %s: %s", symbol, exc)
        return None, f"request-error: {exc}"  # 에러 반환, 다음 항목 진행

# fomc_scraper.py
def download_material(url: str, output_dir: Path, filename: str) -> Optional[Path]:
    try:
        response = requests.get(url, ...)
        output_path.write_bytes(response.content)
        return output_path
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None  # 실패 시 None 반환
```

---

## 요약

- 이 스크래퍼는 **TradingEconomics**와 **Federal Reserve** 웹사이트에서 다음 데이터를 수집합니다:
    - **경제 캘린더**: 미국 경제 이벤트 (CPI, FOMC, 고용지표 등)
        - 출처: `https://tradingeconomics.com/calendar`
        - 필터: 쿠키 기반 (`calendar-countries`, `calendar-importance`, `cal-custom-range`)
    - **거시경제 지표**: CPI, PMI, 국채 금리 등 (16개 지표)
        - 출처: `https://d3ii0wo49og5mi.cloudfront.net/economics/<symbol>`
        - 디코딩: Base64 → XOR (키: `tradingeconomics-charts-core-api-key`) → Deflate
    - **FOMC 기자회견**: Press Conference Transcript PDF (최근 10개)
        - 출처: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
    - **연준 연설문**: Speech Transcript HTML

- 출력 형식:
    - **Calendar**: `output/calendar/calendar_US_{start}_{end}.csv`
    - **Indicators**: `output/indicators/indicators_US_{date}.csv`
    - **FOMC**: `output/fomc_press_conferences/{year}_{month}_{dates}_press_conference.pdf`

- 날짜 범위: 현재 날짜(KST) 기준 **±7일**

- 중복 방지:
    - Calendar: `(datetime_kst, title, source_url)` 키 기반 dedupe
    - 파일 다운로드: `exists()` 체크로 스킵
