"""How each issuer prints a number and a date.

The same amount is written four ways around the world. A reader that only
knows one of them will quietly get the wrong answer, which is the point.
"""

MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def format_amount(value, decimal_mark='dot'):
    grouped = f'{value:,.2f}'
    if decimal_mark == 'comma':
        return grouped.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
    return grouped


def format_price(value, decimal_mark='dot'):
    """A unit price keeps the decimals it was quoted with, up to four."""
    places = max(2, min(4, -value.as_tuple().exponent))
    grouped = f'{value:,.{places}f}'
    if decimal_mark == 'comma':
        return grouped.replace(',', '\x00').replace('.', ',').replace('\x00', '.')
    return grouped


def format_quantity(value, decimal_mark='dot'):
    whole = f'{int(value):,}'
    return whole.replace(',', '.') if decimal_mark == 'comma' else whole


def format_date(day, date_order='iso'):
    if date_order == 'iso':
        return day.isoformat()
    if date_order == 'day_first':
        return f'{day.day:02d}/{day.month:02d}/{day.year}'
    if date_order == 'month_first':
        return f'{day.month:02d}/{day.day:02d}/{day.year}'
    return f'{day.day:02d} {MONTHS[day.month - 1]} {day.year}'


