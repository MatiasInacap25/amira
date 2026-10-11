"""Heuristic detection of contact details in chat messages.

Participants must not move the conversation off the platform, so messages carrying an email, a link,
a phone-like number or a social handle are rejected. The check is a heuristic: spelling digits out or
splitting a handle can evade it. It is a deterrent, not a guarantee.
"""

import re
from typing import Literal

ContactKind = Literal["email", "link", "phone", "social"]

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(
    r"https?://|www\.|\b[\w-]+\.(?:com|cl|net|org|io|app|me|co|info|xyz|link|site)\b",
    re.IGNORECASE,
)
# Nine or more digits, optionally separated by spaces, dots, dashes or brackets. Dates and short numbers do not match.
_PHONE = re.compile(r"(?<!\d)\+?(?:\d[\s.\-()]*){8,}\d(?!\d)")
_SOCIAL = re.compile(
    r"(?<![\w@])@[A-Za-z0-9_.]{3,}|\b(?:instagram|whatsapp|wsp|telegram|facebook|tiktok)\b",
    re.IGNORECASE,
)

_PATTERNS: tuple[tuple[ContactKind, re.Pattern[str]], ...] = (
    ("email", _EMAIL),
    ("link", _LINK),
    ("phone", _PHONE),
    ("social", _SOCIAL),
)

CONTACT_KIND_LABELS: dict[ContactKind, str] = {
    "email": "un correo electrónico",
    "link": "enlaces",
    "phone": "un número de teléfono",
    "social": "usuarios de redes sociales o mensajería",
}


def find_contact_detail(content: str) -> ContactKind | None:
    """The first kind of contact detail found in the content, or None when the content is clean."""
    for kind, pattern in _PATTERNS:
        if pattern.search(content):
            return kind
    return None
