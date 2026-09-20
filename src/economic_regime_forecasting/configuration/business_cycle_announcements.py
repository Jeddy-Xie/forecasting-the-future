"""When the National Bureau of Economic Research announced each turning point.

A recession month is not knowable on a fixed schedule. NBER announces turning points,
not months, and a month is known to be contraction or expansion only once the turning
point that ends its phase has been announced. Debt D14 is what a constant lag costs:
every peak since 1990 was announced within 400 days (128 to 366), and every trough after
them (474 to 662), so a 400-day rule reads the months just after each trough before
anyone knew the recession had ended.

Every date below was checked at nber.org on 2026-09-15 and is recorded in
docs/TECHNICAL_DEBT.md D14. Announcements before 1990 are not listed: the scored
backtest begins in 1994-03, and by then the 1991 trough had been announced.
"""

from __future__ import annotations

from datetime import date

RECESSION_SERIES_NAME = "recession_indicator"
"""The registry name whose availability these announcements govern."""

RECESSION_SERIES_ID = "USREC"
"""The same series as the data layer knows it, which is what the audit reads."""

TURNING_POINT_ANNOUNCEMENTS: tuple[tuple[date, date], ...] = (
    # (the month the turning point falls in, the date it was announced)
    (date(1990, 7, 1), date(1991, 4, 25)),
    (date(1991, 3, 1), date(1992, 12, 22)),
    (date(2001, 3, 1), date(2001, 11, 26)),
    (date(2001, 11, 1), date(2003, 7, 17)),
    (date(2007, 12, 1), date(2008, 12, 1)),
    (date(2009, 6, 1), date(2010, 9, 20)),
    (date(2020, 2, 1), date(2020, 6, 8)),
    (date(2020, 4, 1), date(2021, 7, 19)),
)
"""Turning points since 1990 and the date each was announced, oldest first."""


def announced_by(month: date) -> date | None:
    """The date this month's recession coding became knowable, or None if this table cannot say.

    A month's phase is settled by the MOST RECENT turning point at or before it: that
    announcement is what tells you which side of the boundary the month falls on. Nothing
    later is needed. A month just after a trough is expansion the moment that trough is
    announced, whether or not the next peak has happened, and a month inside a recession
    is known as such once its opening peak is announced.

    The months this exists for are the ones just after a trough. Their opening boundary is
    announced 474 to 662 days after the fact, while a 400-day constant lag calls them known
    far sooner, which is debt D14.

    One month per trough is withheld here for longer than it strictly needs to be: the
    trough month itself. Its coding was inferable before its own announcement, because
    with the recession believed still running every month up to the present was coded 1,
    and the trough month does turn out to be 1. This rule dates it by the trough call
    anyway, 474 to 662 days later. That is deliberate. Being late is never a leak, and
    the alternative is a second rule about which side of a boundary a month falls on,
    bought for four months since 1990. It is why this marks 23 labels as read early by a
    400-day lag where D14's table, which excludes the four trough months, counts 19.

    A month earlier than every listed turning point has no opening boundary here, so this
    returns None and the caller falls back to the registry's constant lag.
    """
    return max(
        (
            announcement
            for turning_point, announcement in TURNING_POINT_ANNOUNCEMENTS
            if turning_point <= month
        ),
        default=None,
    )
