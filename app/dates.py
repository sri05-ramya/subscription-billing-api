import calendar
from datetime import datetime


def add_one_month(start: datetime) -> datetime:
    """Same day next month; if that day doesn't exist, use the last day of the month.

    Examples:
        Nov 4  -> Dec 4
        Jan 31 -> Feb 28 (or Feb 29 in a leap year)
        Dec 15 -> Jan 15 next year
    """
    year = start.year + (start.month // 12)
    month = start.month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(start.day, last_day)
    return start.replace(year=year, month=month, day=day)