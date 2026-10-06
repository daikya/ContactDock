"""Comparison-only normalization; never change stored contact data."""
import re
import unicodedata

# Hyphen/dash/minus variants, whitespace, and parentheses; not Japanese long vowel mark.
_PHONE_SEPARATORS = re.compile(r'[\s()\-\u2010-\u2015\u2212]+')


def normalize_text(value):
    # Normalize only width variants, avoiding unrelated NFKC conversions such as circled digits.
    pieces = []
    halfwidth = []

    def flush():
        if halfwidth:
            pieces.append(unicodedata.normalize('NFKC', ''.join(halfwidth)))
            halfwidth.clear()

    for char in value:
        code = ord(char)
        if 0xFF61 <= code <= 0xFF9F:
            halfwidth.append(char)
        else:
            flush()
            if 0xFF01 <= code <= 0xFF5E:
                pieces.append(chr(code - 0xFEE0))
            elif char == '\u3000':
                pieces.append(' ')
            else:
                pieces.append(char)
    flush()
    return unicodedata.normalize('NFC', ''.join(pieces)).casefold()


def contains_text(value, query):
    needle = normalize_text(query)
    if not needle:
        return 0
    # A query cannot join words across a newline, even if it contains a newline itself.
    return int(any(needle in line for line in normalize_text(value or '').splitlines()))


def contains_phone(value, query):
    if contains_text(value, query):
        return 1
    needle = _PHONE_SEPARATORS.sub('', normalize_text(query))
    # Additional phone matching is numeric only; never match every number for punctuation-only input.
    if not re.fullmatch(r'\+?[0-9]+', needle):
        return 0
    number = _PHONE_SEPARATORS.sub('', normalize_text(value or ''))
    return int(needle in number)
