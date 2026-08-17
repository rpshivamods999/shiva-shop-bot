_BOLD_SANS_UPPER_START = 0x1D5D4  # Mathematical Sans-Serif Bold Capital A
_BOLD_SANS_LOWER_START = 0x1D5EE  # Mathematical Sans-Serif Bold Small a
_BOLD_SANS_DIGIT_START = 0x1D7EC  # Mathematical Sans-Serif Bold Digit Zero

import re

_TG_EMOJI_TAG_RE = re.compile(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', re.IGNORECASE | re.DOTALL)


def strip_emoji_tags(text: str) -> str:
    """Product/category/duration names (and other plain button labels) are
    rendered as raw InlineKeyboardButton text, which Telegram does NOT parse
    as HTML. If someone pastes the <tg-emoji emoji-id="...">X</tg-emoji> tag
    (meant for HTML-parsed message text, not buttons) into one of these
    plain-text fields, it would otherwise show up literally on the button.
    This strips the tag and keeps just the visible fallback emoji/text
    inside it, so a mistaken paste degrades gracefully instead of showing
    raw markup."""
    return _TG_EMOJI_TAG_RE.sub(r'\1', text).strip()


def stylize(text: str) -> str:
    """Converts plain Latin letters/digits into bold sans-serif unicode
    for a premium, aesthetic look — works in any Telegram client, no
    HTML parsing required. Emojis, punctuation, and spacing are untouched."""
    out = []
    for ch in text:
        if 'A' <= ch <= 'Z':
            out.append(chr(_BOLD_SANS_UPPER_START + (ord(ch) - ord('A'))))
        elif 'a' <= ch <= 'z':
            out.append(chr(_BOLD_SANS_LOWER_START + (ord(ch) - ord('a'))))
        elif '0' <= ch <= '9':
            out.append(chr(_BOLD_SANS_DIGIT_START + (ord(ch) - ord('0'))))
        else:
            out.append(ch)
    return "".join(out)
