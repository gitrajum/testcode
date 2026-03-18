"""
Phone Number Normalization Utility.

Normalizes phone numbers from any source (invoices, Databricks, employee CSV)
into E.164 international format: +{country_code}{national_number}, no spaces
or separators of any kind.

The `phonenumbers` library handles all country code lengths correctly — from
+1 (US/CA) to +49 (Germany) to +55 (Brazil) to +968 (Oman), etc.

Examples by country:
    US       "201-213-0635"        → "+12012130635"
    US       "(212) 555-0123"      → "+12125550123"
    Germany  "+49 30 12345678"     → "+493012345678"
    Germany  "030 12345678"        (default_region="DE") → "+493012345678"
    Brazil   "+55 11 91234 5678"   → "+5511912345678"
    Brazil   "11912345678"         (default_region="BR") → "+5511912345678"
    Poland   "+48 22 123 45 67"    → "+48221234567"
    Poland   "221234567"           (default_region="PL") → "+48221234567"

Both invoice phone columns and employee phone columns are normalized to this
format before matching, so the comparison is always country-code-aware.
"""

import logging
import re
from typing import Optional

import phonenumbers
from phonenumbers import PhoneNumberFormat

logger = logging.getLogger(__name__)

# Default region assumed when a number has no leading '+' country code.
# ISO-3166-1 alpha-2 code.  Override per-call via `default_region` arg.
DEFAULT_REGION = "US"

# ── Convenience map: ISO country name / common alias → ISO-3166-1 alpha-2 ──
# Used so callers can pass a human-readable country name (as stored in agent
# config or invoice metadata) and receive the two-letter region code that the
# `phonenumbers` library requires.  Extend this dict when adding support for
# a new carrier country; the calling code itself is looked up by the library.
COUNTRY_NAME_TO_REGION: dict = {
    # United States
    "united states": "US",
    "us":            "US",
    "usa":           "US",
    # Brazil
    "brazil":        "BR",
    "brasil":        "BR",
    "br":            "BR",
    # Germany
    "germany":       "DE",
    "deutschland":   "DE",
    "de":            "DE",
    # Poland
    "poland":        "PL",
    "polska":        "PL",
    "pl":            "PL",
}


def country_to_region(country: str) -> Optional[str]:
    """
    Convert a human-readable country name or ISO code to an ISO-3166-1 alpha-2
    region code understood by the `phonenumbers` library.

    Args:
        country: e.g. "Brazil", "BR", "United States", "DE"

    Returns:
        ISO-3166-1 alpha-2 code (e.g. "BR"), or None if unrecognised.
    """
    if not country:
        return None
    return COUNTRY_NAME_TO_REGION.get(country.strip().lower())


def normalize_phone(raw: str, default_region: str = DEFAULT_REGION) -> Optional[str]:
    """
    Normalize a single phone number to E.164 international format.

    E.164: +{country_code}{national_number}   — no spaces, dashes, parens, or dots.

    Examples:
        normalize_phone("201-213-0635")               → "+12012130635"  (US default)
        normalize_phone("030 12345678", "DE")         → "+493012345678"  (Germany)
        normalize_phone("+55 11 91234 5678")          → "+5511912345678" (Brazil)
        normalize_phone("+491715511656")              → "+491715511656"  (Germany)

    Steps:
      1. Strip whitespace and validate input is non-empty.
      2. Parse with `phonenumbers` using `default_region` as fallback country.
      3. If valid/possible, return formatted E.164 string.
      4. If phonenumbers fails, fall back to a digit-strip heuristic that
         prepends the calling code for `default_region`.

    Args:
        raw:            Raw phone string in any format.
        default_region: ISO-3166-1 alpha-2 code assumed when no '+' prefix.
                        Pass e.g. "DE" for German invoices, "BR" for Brazilian,
                        "US" (default) for North American.

    Returns:
        E.164 string starting with '+' (e.g. "+12012130635"),
        or None if the input is empty / too short / completely unparseable.
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned or cleaned.lower() in ("nan", "none", "null", "--", ""):
        return None

    # ------------------------------------------------------------------ #
    # Attempt 1 – phonenumbers library (robust, handles all country codes)
    # ------------------------------------------------------------------ #
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
        if phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass

    # ------------------------------------------------------------------ #
    # Attempt 2 – digit-strip heuristic fallback
    #
    # Strip all non-digit characters, then prepend the calling code for
    # default_region to produce a best-effort E.164 string.
    # ------------------------------------------------------------------ #
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) < 7:
        return None  # Too short to be a real phone number

    # Get calling code for default_region (e.g. US→1, DE→49, BR→55)
    calling_code = phonenumbers.country_code_for_region(default_region)
    if calling_code:
        cc_str = str(calling_code)
        # Avoid double-prepending: if digits already start with this calling code
        if digits.startswith(cc_str) and len(digits) > len(cc_str):
            e164 = f"+{digits}"
        else:
            e164 = f"+{cc_str}{digits}"
        # One final parse attempt with the reconstructed number
        try:
            parsed = phonenumbers.parse(e164, None)
            if phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed):
                return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            pass
        return e164  # Return best-effort even if phonenumbers can't validate

    # Absolute last resort: prefix '+' and return raw digits
    return f"+{digits}"


def normalize_phone_column(series, default_region: str = DEFAULT_REGION):
    """
    Normalize an entire pandas Series of phone numbers to E.164 format.

    This is the primary entry point for batch normalization used when aligning
    two data sources (e.g. invoice phone numbers vs Databricks employee phones).
    Both columns must be normalized with a matching default_region so that numbers
    without an explicit country-code prefix are resolved to the same country.

    Callers processing non-US invoices should pass the appropriate region code:
        - German  Telekom invoices  → default_region="DE"
        - Brazilian Vivo invoices   → default_region="BR"
        - Polish   invoices         → default_region="PL"
    Employee records from Databricks that already carry a '+' prefix are parsed
    correctly regardless of default_region (the library uses the embedded country
    code), so the same region code can be passed for both sides of the join.

    Args:
        series:         pandas Series of raw phone strings.
        default_region: ISO-3166-1 alpha-2 default region code.

    Returns:
        pandas Series of E.164 strings (pd.NA where unparseable).
    """
    # pandas is imported lazily here to keep phone_normalizer importable in
    # environments where pandas is not installed (e.g. lightweight CLI scripts).
    import pandas as pd

    normalized = series.astype(str).apply(
        lambda x: normalize_phone(x, default_region)
    )
    return normalized.where(normalized.notna(), other=pd.NA)
