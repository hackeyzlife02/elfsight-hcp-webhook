"""
Utility functions for data normalization and parsing.
"""

import re
import logging
from typing import Optional, Dict, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def normalize_phone(phone: str, default_area_code: str = "415") -> Optional[str]:
    """
    Normalize phone number to E.164 format (+1XXXXXXXXXX).

    Based on pattern from hcp_customer_import_final.py.

    Args:
        phone: Raw phone number string
        default_area_code: Area code to add if missing (default: 415)

    Returns:
        Normalized phone number or None if invalid

    Examples:
        >>> normalize_phone("(415) 555-1234")
        '+14155551234'
        >>> normalize_phone("555-1234", "415")
        '+14155551234'
        >>> normalize_phone("14155551234")
        '+14155551234'
    """
    if not phone:
        return None

    # Remove all non-digit characters
    digits = re.sub(r'\D', '', str(phone))

    # Handle different formats
    if len(digits) == 10:
        # 10 digits: add country code
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # 11 digits starting with 1: add + prefix
        return f"+{digits}"
    elif len(digits) == 7:
        # 7 digits: add area code and country code
        return f"+1{default_area_code}{digits}"
    elif len(digits) > 11:
        # Too many digits, try to extract last 10
        last_10 = digits[-10:]
        logger.warning(f"Phone number too long ({len(digits)} digits), using last 10: {last_10}")
        return f"+1{last_10}"
    else:
        logger.warning(f"Invalid phone number format: {phone} ({len(digits)} digits)")
        return None


def parse_name(full_name: str) -> Tuple[str, str]:
    """
    Parse full name into first and last name.

    Args:
        full_name: Full name string

    Returns:
        Tuple of (first_name, last_name)

    Examples:
        >>> parse_name("John Smith")
        ('John', 'Smith')
        >>> parse_name("Mary Jane Watson")
        ('Mary Jane', 'Watson')
        >>> parse_name("Prince")
        ('Prince', '')
    """
    if not full_name:
        return "", ""

    parts = full_name.strip().split()

    if len(parts) == 0:
        return "", ""
    elif len(parts) == 1:
        return parts[0], ""
    elif len(parts) == 2:
        return parts[0], parts[1]
    else:
        # More than 2 parts: first word is first name, rest is last name
        # OR: all but last is first name, last is last name
        # Let's go with: all but last is first name
        return " ".join(parts[:-1]), parts[-1]


def parse_address(address_string: str) -> Dict[str, Optional[str]]:
    """
    Parse address string into components.

    Args:
        address_string: Full address string

    Returns:
        Dictionary with keys: street, city, state, zip

    Examples:
        >>> parse_address("123 Main St, San Francisco, CA 94102")
        {'street': '123 Main St', 'city': 'San Francisco', 'state': 'CA', 'zip': '94102'}
        >>> parse_address("456 Oak Ave, Oakland CA 94601")
        {'street': '456 Oak Ave', 'city': 'Oakland', 'state': 'CA', 'zip': '94601'}
    """
    result: Dict[str, Optional[str]] = {
        "street": None,
        "city": None,
        "state": None,
        "zip": None
    }

    if not address_string:
        return result

    address_string = address_string.strip()

    # Pattern 1: Street, City, State Zip
    # Example: "123 Main St, San Francisco, CA 94102"
    pattern1 = r'^(.+?),\s*(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$'
    match = re.match(pattern1, address_string)
    if match:
        result["street"] = match.group(1).strip()
        result["city"] = match.group(2).strip()
        result["state"] = match.group(3).strip()
        result["zip"] = match.group(4).strip()
        return result

    # Pattern 2: Street, City State Zip (no comma before state)
    # Example: "123 Main St, San Francisco CA 94102"
    pattern2 = r'^(.+?),\s*(.+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$'
    match = re.match(pattern2, address_string)
    if match:
        result["street"] = match.group(1).strip()
        result["city"] = match.group(2).strip()
        result["state"] = match.group(3).strip()
        result["zip"] = match.group(4).strip()
        return result

    # Pattern 3: Try to extract zip code and work backwards
    zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', address_string)
    if zip_match:
        result["zip"] = zip_match.group(1)
        before_zip = address_string[:zip_match.start()].strip()

        # Try to find state (2 capital letters before zip)
        state_match = re.search(r'\b([A-Z]{2})\s*$', before_zip)
        if state_match:
            result["state"] = state_match.group(1)
            before_state = before_zip[:state_match.start()].strip()

            # Split remaining by comma
            parts = [p.strip() for p in before_state.split(',')]
            if len(parts) >= 2:
                result["street"] = parts[0]
                result["city"] = parts[1]
            elif len(parts) == 1:
                # Ambiguous: could be street or city
                result["street"] = parts[0]

    # If we couldn't parse it, put everything in street
    if not any(result.values()):
        result["street"] = address_string

    return result


def compare_addresses(addr1: Dict[str, Optional[str]], addr2: Dict[str, Optional[str]]) -> float:
    """
    Compare two parsed addresses and return similarity score.

    Args:
        addr1: First address dictionary
        addr2: Second address dictionary

    Returns:
        Similarity score between 0 and 1
    """
    if not addr1 or not addr2:
        return 0.0

    scores = []

    # Compare each field
    for field in ["street", "city", "state", "zip"]:
        val1 = (addr1.get(field) or "").lower().strip()
        val2 = (addr2.get(field) or "").lower().strip()

        if not val1 or not val2:
            continue

        if val1 == val2:
            scores.append(1.0)
        else:
            # Use sequence matcher for fuzzy comparison
            similarity = SequenceMatcher(None, val1, val2).ratio()
            scores.append(similarity)

    if not scores:
        return 0.0

    # Weighted average: zip is most important, then street
    weights = {
        "zip": 0.4,
        "street": 0.3,
        "city": 0.2,
        "state": 0.1
    }

    weighted_scores = []
    field_index = 0
    for field in ["street", "city", "state", "zip"]:
        val1 = (addr1.get(field) or "").lower().strip()
        val2 = (addr2.get(field) or "").lower().strip()
        if val1 and val2:
            similarity = SequenceMatcher(None, val1, val2).ratio()
            weighted_scores.append(similarity * weights[field])
            field_index += 1

    if not weighted_scores:
        return 0.0

    return sum(weighted_scores) / sum(weights.values())


def sanitize_string(s: Optional[str]) -> str:
    """
    Sanitize string for safe storage and comparison.

    Args:
        s: Input string

    Returns:
        Sanitized string
    """
    if not s:
        return ""

    # Remove extra whitespace
    s = " ".join(s.split())

    # Remove potentially problematic characters
    s = s.strip()

    return s


def format_note(form_data: dict, match_info: Optional[dict] = None) -> str:
    """
    Format form submission data into a note for HCP.

    Args:
        form_data: Form submission data
        match_info: Optional customer match information

    Returns:
        Formatted note string
    """
    lines = ["=== Website Form Submission ===", ""]

    # Add form data
    for key, value in form_data.items():
        if value:
            # Format key nicely
            key_formatted = key.replace("_", " ").title()
            lines.append(f"{key_formatted}: {value}")

    # Add match information if provided
    if match_info:
        lines.append("")
        lines.append("=== Customer Match Info ===")
        lines.append(f"Match Type: {match_info.get('match_type', 'unknown')}")
        lines.append(f"Confidence: {match_info.get('confidence', 0):.0%}")

        if match_info.get('warnings'):
            lines.append("")
            lines.append("⚠️  WARNINGS:")
            for warning in match_info['warnings']:
                lines.append(f"  • {warning}")

    return "\n".join(lines)


def format_lead_note(form_data: dict, match_info: Optional[dict] = None) -> str:
    """
    Format lead form submission data into a structured note for HCP.

    Args:
        form_data: Parsed form submission data
        match_info: Optional customer match information

    Returns:
        Formatted note string with sections for customer type, services, etc.
    """
    lines = ["=== Website Form Submission ===", ""]

    # Customer Type Section
    if form_data.get("customer_type"):
        lines.append(f"Customer Type: {form_data['customer_type']}")

    # Preferred Contact
    if form_data.get("preferred_contact"):
        lines.append(f"Preferred Contact: {form_data['preferred_contact']}")

    # SMS Consent
    if form_data.get("sms_consent") is not None:
        consent_text = "Yes" if form_data["sms_consent"] else "No"
        lines.append(f"SMS Consent: {consent_text}")

    # Service Needed Section
    if form_data.get("service_needed"):
        lines.append("")
        lines.append(f"Service Needed: {form_data['service_needed']}")

    # Service Details Section (multi-select)
    if form_data.get("service_details"):
        lines.append("")
        lines.append("Service Details:")
        service_details = form_data["service_details"]
        if isinstance(service_details, list):
            for service in service_details:
                lines.append(f"  • {service}")
        else:
            lines.append(f"  • {service_details}")

    # Request Details
    if form_data.get("service_request_details"):
        lines.append("")
        lines.append("Request Details:")
        lines.append(form_data["service_request_details"])

    # File Attachments
    if form_data.get("file_attachments"):
        lines.append("")
        lines.append("Attachments:")
        attachments = form_data["file_attachments"]
        if isinstance(attachments, list):
            for attachment in attachments:
                lines.append(f"  • {attachment}")
        else:
            lines.append(f"  • {attachments}")

    # Customer Match Info
    if match_info:
        lines.append("")
        lines.append("=== Customer Match Info ===")
        match_type = match_info.get('match_type', 'unknown')
        if match_type == 'exact':
            lines.append("✓ Exact match found (phone and email)")
        elif match_type == 'partial':
            lines.append("⚠️  Partial match found")
        else:
            lines.append("New customer (no existing record found)")

        if match_info.get('confidence'):
            lines.append(f"Confidence: {match_info['confidence']:.0%}")

        if match_info.get('warnings'):
            lines.append("")
            for warning in match_info['warnings']:
                lines.append(f"⚠️  {warning}")

    return "\n".join(lines)
