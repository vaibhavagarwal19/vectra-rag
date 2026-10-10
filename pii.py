"""Mask personal data (emails, phone numbers) before it is logged or sent to the LLM.

Vectra's brief calls this out explicitly via Anand's question, which includes his
email and phone number inline. We mask on the way in (so OpenAI never sees the raw
values) and again on the way out (so nothing echoes it back to the employee).
"""
import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Matches +91 98765 43210, 9876543210, +91-9876543210, etc.
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\d{10}\b")


def mask_pii(text: str) -> str:
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text
