# FOMC Scraper Bug Fixes - Summary

## Issues Fixed

### 1. Duplicate Meetings in Output
**Problem**: The same FOMC meeting appeared multiple times in the results (e.g., "2025 August 22" appeared 5 times, "2025 August 27" appeared 3 times).

**Root Cause**: 
- The FOMC calendar page contains multiple header elements for the same year (e.g., multiple "2024 FOMC Meetings" headers)
- The parser was adding all of these to `year_headers` without deduplication
- Each year header was processed separately, and the `seen_meetings` set was local to each iteration
- This caused the same meeting to be created multiple times - once per year header

**Fix Applied**:
1. **Deduplicate year headers** (lines 116-143):
   - Added `seen_years` set to track which years have already been processed
   - Only add the first occurrence of each year to `year_headers`
   - This ensures each year is processed exactly once

2. **Global meeting deduplication** (lines 150-152, 325-329):
   - Changed `seen_meetings` from a local variable to `seen_meetings_global` at the function scope
   - This set persists across all year header iterations
   - Each `(year, month, dates)` tuple is checked against this global set before creating a `MeetingMaterial`
   - Prevents duplicate meetings even if multiple year headers somehow slip through

### 2. Noisy "No Meetings" Warnings
**Problem**: Logs showed repeated warnings like:
```
Year 2024: Found 150 content elements but no meetings. Month/date parsing may be failing.
Year 2024: Found 109 content elements but no meetings. Month/date parsing may be failing.
Year 2024: Found 163 content elements but no meetings. Month/date parsing may be failing.
```

**Root Cause**:
- Same as above - multiple year headers for the same year
- Each header instance covered a different DOM range
- Some ranges contained no actual meeting data, triggering the warning
- The warning fired multiple times for the same year, even though meetings were found in other header instances

**Fix Applied**:
- With year header deduplication, each year is now processed only once
- The warning still fires if needed, but only once per year
- Added clarifying comment (line 508-511) explaining that the warning is now accurate

### 3. Redundant Download Attempts
**Problem**: The downloader attempted to download the same meeting multiple times, resulting in many "Skipped (exists)" messages.

**Root Cause**:
- Duplicate `MeetingMaterial` objects in the list
- The "10 most recent meetings" filter was dominated by repeated dates

**Fix Applied**:
- With both deduplication fixes above, the `meetings` list now contains unique entries
- Each meeting appears at most once
- The "10 most recent meetings" will be 10 distinct meetings, not multiple copies of the same few meetings
- Downloads happen once per meeting

## Code Changes

### File: `scraper/fomc_scraper.py`

**Change 1** (lines 116-118):
```python
# FIX: Deduplicate years to prevent processing the same year multiple times
year_headers = []  # List of (year, header_element) tuples in DOM order
seen_years = set()  # Track which years we've already added
```

**Change 2** (lines 126-130):
```python
# FIX: Only add each year once (first occurrence in DOM order)
if 2020 <= found_year <= 2027 and found_year not in seen_years:
    year_headers.append((found_year, elem))
    seen_years.add(found_year)
    logger.info(f"Found year header for {found_year} at DOM position {len(year_headers)}: {elem_text[:50]}")
```

**Change 3** (lines 139-143):
```python
# FIX: Check seen_years set instead of scanning year_headers list
if 2020 <= found_year <= 2027 and found_year not in seen_years:
    if len(elem_text) < 30 and "|" not in elem_text:
        year_headers.append((found_year, elem))
        seen_years.add(found_year)
```

**Change 4** (lines 150-152):
```python
# FIX: Global deduplication set to prevent duplicate meetings across all year headers
# This ensures each (year, month, dates) combination appears only once in the final list
seen_meetings_global: set[tuple[int, str, str]] = set()
```

**Change 5** (line 185):
```python
# NOTE: seen_meetings is now global (seen_meetings_global) to prevent duplicates across headers
```

**Change 6** (lines 325-329):
```python
# FIX: Check global deduplication set to prevent duplicate meetings
meeting_key = (year, month, dates)
if meeting_key in seen_meetings_global:
    continue
seen_meetings_global.add(meeting_key)
```

**Change 7** (line 508):
```python
# FIX: Only log per-year summary once, after processing all content for this year
```

## Expected Behavior After Fix

### Before:
```
Found 47 FOMC meetings
Limiting to 10 most recent meetings:
  2025 November 19 (date: 2025-11-19)
  2025 August 27 (date: 2025-08-27)
  2025 August 27 (date: 2025-08-27)  # DUPLICATE
  2025 August 27 (date: 2025-08-27)  # DUPLICATE
  2025 August 22 (date: 2025-08-22)
  2025 August 22 (date: 2025-08-22)  # DUPLICATE
  2025 August 22 (date: 2025-08-22)  # DUPLICATE
  2025 August 22 (date: 2025-08-22)  # DUPLICATE
  2025 August 22 (date: 2025-08-22)  # DUPLICATE
  2025 March 31 (date: 2025-03-31)
```

### After:
```
Found ~8-12 FOMC meetings (deduplicated)
Limiting to 10 most recent meetings:
  2025 November 19 (date: 2025-11-19)
  2025 October 28-29 (date: 2025-10-28)
  2025 August 27 (date: 2025-08-27)
  2025 August 22 (date: 2025-08-22)
  2025 March 31 (date: 2025-03-31)
  2025 January 28-29 (date: 2025-01-28)
  2024 December 17-18 (date: 2024-12-17)
  2024 November 6-7 (date: 2024-11-06)
  2024 September 17-18 (date: 2024-09-17)
  2024 July 30-31 (date: 2024-07-30)
```

Each meeting appears exactly once, with distinct dates.

### Warnings:
- Significantly reduced noise
- Each year appears in logs only once
- Warnings are now meaningful (only fire when there's a real parsing issue)

## Testing Recommendations

1. **Run the scraper** and verify:
   - No duplicate meetings in the output
   - Each date appears at most once in the "10 most recent meetings" list
   - Fewer "no meetings" warnings (ideally none, or only for years with actual issues)

2. **Check downloads**:
   - Each meeting should be downloaded exactly once
   - No repeated "Skipped (exists)" messages for the same meeting

3. **Verify meeting count**:
   - Total meetings should be ~8-12 (realistic number for recent FOMC meetings)
   - Not 47 as before (which included duplicates)

## Notes

- **No external interface changes**: The `scrape_fomc_calendar()` function signature and `MeetingMaterial` dataclass remain unchanged
- **Backward compatible**: Existing code calling this module will work without modification
- **Performance**: Slightly faster due to reduced duplicate processing
- **Logging**: More accurate and less noisy

## Files Modified

- `scraper/fomc_scraper.py` - Fixed duplicate meeting creation and year header processing

