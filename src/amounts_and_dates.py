"""Reading and printing the numbers that four countries write four ways.

"1.234,56" and "1,234.56" are the same amount. "03/04/2026" is two
different days depending on who printed it. Nothing here guesses: the
caller states which convention the page uses, because a date read with
the wrong order is not an error the program can detect later.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

COMMA_DECIMAL = "comma"
DOT_DECIMAL = "dot"

DAY_FIRST = "day_first"
MONTH_FIRST = "month_first"
ISO = "iso"

_NOT_A_NUMBER = re.compile(r"[^0-9,.\-]")


def parse_amount(text: str, decimal_mark: str) -> Decimal:
    """Turn a printed amount into an exact Decimal.

    `decimal_mark` says which character separates the cents, because the
    other one is then a thousands separator and must be thrown away.
    """
    if text is None:
        raise ValueError("no amount to parse")
    cleaned = _NOT_A_NUMBER.sub("", text).strip()
    if not cleaned:
        raise ValueError(f"no digits in {text!r}")
    if decimal_mark == COMMA_DECIMAL:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif decimal_mark == DOT_DECIMAL:
        cleaned = cleaned.replace(",", "")
    else:
        raise ValueError(f"unknown decimal mark {decimal_mark!r}")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"cannot read an amount from {text!r}")


def format_amount(value: Decimal, decimal_mark: str) -> str:
    """Print an amount the way the issuer would print it."""
    plain = f"{value:,.2f}"
    if decimal_mark == DOT_DECIMAL:
        return plain
    if decimal_mark == COMMA_DECIMAL:
        swapped = plain.replace(",", "\x00").replace(".", ",")
        return swapped.replace("\x00", ".")
    raise ValueError(f"unknown decimal mark {decimal_mark!r}")


def parse_date(text: str, order: str) -> date:
    """Turn a printed date into a real one."""
    if text is None:
        raise ValueError("no date to parse")
    parts = re.split(r"[/\-.]", text.strip())
    if len(parts) != 3:
        raise ValueError(f"cannot read a date from {text!r}")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"cannot read a date from {text!r}")
    if order == ISO:
        year, month, day = numbers
    elif order == DAY_FIRST:
        day, month, year = numbers
    elif order == MONTH_FIRST:
        month, day, year = numbers
    else:
        raise ValueError(f"unknown date order {order!r}")
    return date(year, month, day)


def format_date(value: date, order: str) -> str:
    """Print a date the way the issuer would print it."""
    if order == ISO:
        return value.strftime("%Y-%m-%d")
    if order == DAY_FIRST:
        return value.strftime("%d/%m/%Y")
    if order == MONTH_FIRST:
        return value.strftime("%m/%d/%Y")
    raise ValueError(f"unknown date order {order!r}")
