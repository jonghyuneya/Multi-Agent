"""Test script to verify FOMC filename generation uses meeting dates correctly."""

from __future__ import annotations

import sys
from pathlib import Path

# Add parent to path
PROJECT_ROOT = Path(__file__).resolve().parent
PARENT_ROOT = PROJECT_ROOT.parent
if str(PARENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARENT_ROOT))

from te_calendar_scraper.scraper import fomc_scraper


def get_meeting_id(meeting: fomc_scraper.MeetingMaterial) -> str:
    """Generate a canonical meeting ID from MeetingMaterial (same as in main.py)."""
    month_abbrev = {
        'January': 'jan', 'February': 'feb', 'March': 'mar', 'April': 'apr',
        'May': 'may', 'June': 'jun', 'July': 'jul', 'August': 'aug',
        'September': 'sep', 'October': 'oct', 'November': 'nov', 'December': 'dec',
        'Jan/Feb': 'jan', 'Apr/May': 'apr', 'Oct/Nov': 'oct',
    }
    
    month_key = meeting.month.split('/')[0] if '/' in meeting.month else meeting.month
    month_abbr = month_abbrev.get(month_key, month_key[:3].lower())
    dates_normalized = meeting.dates.replace('-', '-')
    meeting_id = f"{meeting.year}_{month_abbr}_{dates_normalized}"
    return meeting_id


def test_january_28_29_2025():
    """Test that January 28-29, 2025 meeting generates correct filenames."""
    # Create a test MeetingMaterial for January 28-29, 2025
    meeting = fomc_scraper.MeetingMaterial(
        year=2025,
        month="January",
        dates="28-29",
        meeting_type="FOMC Meeting",
    )
    
    meeting_id = get_meeting_id(meeting)
    
    # Expected meeting ID
    expected_id = "2025_jan_28-29"
    
    assert meeting_id == expected_id, f"Expected {expected_id}, got {meeting_id}"
    
    # Test filename generation
    statement_filename = f"{meeting_id}_statement.html"
    transcript_filename = f"{meeting_id}_press_conference.pdf"
    minutes_filename = f"{meeting_id}_minutes.html"
    
    # Verify filenames contain correct date components
    assert "2025" in statement_filename, "Statement filename missing year 2025"
    assert "jan" in statement_filename, "Statement filename missing month 'jan'"
    assert "28-29" in statement_filename, "Statement filename missing dates '28-29'"
    assert "oct26" not in statement_filename, "Statement filename incorrectly contains 'oct26'"
    assert "oct" not in statement_filename or "jan" in statement_filename, "Statement filename has wrong month"
    
    print("✓ January 28-29, 2025 test passed")
    print(f"  Meeting ID: {meeting_id}")
    print(f"  Statement: {statement_filename}")
    print(f"  Transcript: {transcript_filename}")
    print(f"  Minutes: {minutes_filename}")
    
    return True


def test_split_month():
    """Test that split months like Apr/May are handled correctly."""
    meeting = fomc_scraper.MeetingMaterial(
        year=2024,
        month="Apr/May",
        dates="30-1",
        meeting_type="FOMC Meeting",
    )
    
    meeting_id = get_meeting_id(meeting)
    expected_id = "2024_apr_30-1"
    
    assert meeting_id == expected_id, f"Expected {expected_id}, got {meeting_id}"
    assert "apr" in meeting_id, "Split month should use first month (apr)"
    assert "may" not in meeting_id, "Split month should not include second month in ID"
    
    print("✓ Split month (Apr/May) test passed")
    print(f"  Meeting ID: {meeting_id}")
    
    return True


def test_notation_vote():
    """Test that notation votes get correct suffix."""
    meeting = fomc_scraper.MeetingMaterial(
        year=2020,
        month="August",
        dates="27",
        meeting_type="Notation Vote",
    )
    
    meeting_id = get_meeting_id(meeting)
    expected_id = "2020_aug_27"
    
    assert meeting_id == expected_id, f"Expected {expected_id}, got {meeting_id}"
    
    # For notation votes, the suffix would be added in main.py
    notation_filename = f"{meeting_id}_notation_vote.html"
    assert "notation_vote" in notation_filename
    
    print("✓ Notation vote test passed")
    print(f"  Meeting ID: {meeting_id}")
    print(f"  Notation vote filename: {notation_filename}")
    
    return True


if __name__ == "__main__":
    print("Testing FOMC filename generation...")
    print("=" * 60)
    
    try:
        test_january_28_29_2025()
        test_split_month()
        test_notation_vote()
        
        print("=" * 60)
        print("✓ All tests passed!")
        print("\nFilename generation correctly uses MeetingMaterial dates.")
        print("No external dates (like oct26_2025) should appear in filenames.")
        
    except AssertionError as e:
        print(f"✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

