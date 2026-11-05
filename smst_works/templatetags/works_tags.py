"""Small template helpers for SmSt Works."""

from django import template

register = template.Library()


@register.filter
def duration(value):
    """Turn seconds into a short, readable duration."""
    try:
        seconds = int(float(value or 0))
    except (TypeError, ValueError):
        return "—"
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


@register.filter
def short_date(value):
    """A date without the year when it is this year."""
    if not value:
        return "—"
    return value.strftime("%d %b")
