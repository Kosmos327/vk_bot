import re
from typing import Optional

PARTNER_PATTERN = re.compile(r"^\s*партн[её]р\s+(\d+)\s*$", re.IGNORECASE)
SERVICE_PATTERN = re.compile(r"^\s*услуга\s+(\d+)\s*$", re.IGNORECASE)
CODE_PATTERN = re.compile(r"^\s*код\s+(\d+)\s*$", re.IGNORECASE)


def parse_partner_command(text: str) -> Optional[int]:
    m = PARTNER_PATTERN.match(text or "")
    return int(m.group(1)) if m else None


def parse_service_command(text: str) -> Optional[int]:
    m = SERVICE_PATTERN.match(text or "")
    return int(m.group(1)) if m else None


def parse_code_command(text: str) -> Optional[int]:
    m = CODE_PATTERN.match(text or "")
    return int(m.group(1)) if m else None
