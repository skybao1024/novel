"""Deterministic manuscript headings for newly created Chapters."""

from __future__ import annotations


def chapter_heading(*, language: str, chapter_number: int, title: str) -> str:
    """Return the exact first line required for a new Chapter's first Scene."""

    if chapter_number < 1:
        raise ValueError("chapter_number must be positive")
    if not title:
        raise ValueError("Chapter title must not be empty")
    if language.lower().startswith("zh"):
        number = _chinese_chapter_number(chapter_number)
        return f"# 第{number}章　{title}"
    return f"# Chapter {chapter_number}: {title}"


def _chinese_chapter_number(value: int) -> str:
    if value > 9999:
        return str(value)
    digits = "零一二三四五六七八九"
    result: list[str] = []
    remainder = value
    zero_pending = False
    for divisor, unit in ((1000, "千"), (100, "百"), (10, "十")):
        digit, remainder = divmod(remainder, divisor)
        if digit:
            if zero_pending:
                result.append("零")
            result.extend((digits[digit], unit))
            zero_pending = False
        elif result and remainder:
            zero_pending = True
    if remainder:
        if zero_pending:
            result.append("零")
        result.append(digits[remainder])
    rendered = "".join(result)
    if 10 <= value < 20:
        return rendered.removeprefix("一")
    return rendered
