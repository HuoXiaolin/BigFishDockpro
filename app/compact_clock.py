"""Measured two-line clocks for the Dock and folded capsule."""
from datetime import datetime
from functools import lru_cache
from math import ceil

from PyQt5.QtGui import QFont, QFontMetricsF
from compact_text import draw_stacked_text, line_heights
from resource_options import compact_text_height


CALENDAR_OPTIONS = {'weekday':'星期', 'lunar':'农历', 'festival':'节日'}
ROTATE_SECONDS = 6


@lru_cache(maxsize=48)
def date_lines(day, pattern, weekday, lunar, festival):
    short_date = day.strftime('%m/%d')
    week = '周' + '一二三四五六日'[day.weekday()]
    base = day.strftime(pattern)
    if weekday and pattern == '%Y-%m-%d':
        lines = [base, short_date + ' ' + week]
    else:
        lines = [base + ' ' + week if weekday else base]
    if lunar or festival:
        from calendar_details import civil_festivals, lunar_details
        _, lunar_date, lunar_festival = lunar_details(day)
        if lunar and lunar_date:
            lines.append(lunar_date)
        if festival:
            from calendar_almanac import term_dates
            names = [*civil_festivals(day), lunar_festival]
            if day.month == 4 and (day,'清明') in term_dates(day.year):
                names.append('清明节')
            lines.extend(name for name in names if name)
    return tuple(dict.fromkeys(lines))


def headers(cfg, prefix, formats, day):
    return date_lines(day, formats[0], *(cfg[prefix + key] for key in CALENDAR_OPTIONS))


def capsule_headers(cfg, formats):
    return headers(cfg, 'resource_clock_', formats, datetime.now().date())


def lines_at(now, upper, lower_format, page=None):
    if page is None:
        page = (now.hour * 3600 + now.minute * 60 + now.second) // ROTATE_SECONDS
    return upper[page % len(upper)], now.strftime(lower_format)


def clock_text_height(height, dock):
    # The Dock provides the whole button slot; the capsule supplies its text band.
    return min(height,round(height*.66)+2) if dock else height


@lru_cache(maxsize=64)
def clock_fonts(height, dock):
    upper, lower = line_heights(clock_text_height(height,dock),'clock')
    caption = QFont('Segoe UI')
    caption.setWeight(QFont.Bold)
    value = QFont(caption)
    caption.setPixelSize(max(1,round(upper*1.10)))
    value.setPixelSize(max(1,round(lower*1.13)))
    return caption, value


@lru_cache(maxsize=128)
def clock_width(upper, lower_format, height, dock=False):
    caption, primary = clock_fonts(height, dock)
    fm = QFontMetricsF(caption)
    sample = {'%H:%M:%S':'88:88:88', '%H:%M':'88:88', '%m/%d':'88/88'}[lower_format]
    return ceil(max(QFontMetricsF(primary).horizontalAdvance(sample),
                    *(fm.horizontalAdvance(line) for line in upper))) + (12 if dock else 4)


def capsule_clock_width(cfg, formats, height):
    return clock_width(capsule_headers(cfg, formats), formats[1], compact_text_height(cfg,height))


def draw_clock(p, rect, rows, caption_color, time_color, dock=False):
    inset = 6 if dock else 2
    height = round(rect.height())
    top = (rect.height()-clock_text_height(height,dock))/2
    draw_stacked_text(p,rect.adjusted(inset,top,-inset,-top),rows,(caption_color,time_color),'clock',clock_fonts(height,dock))
