"""
Configuration management for Elfsight webhook service.
Loads environment variables and provides configuration constants.
"""

import os
from typing import Optional


class Config:
    """Application configuration"""

    # HCP API Configuration
    HCP_API_KEY: str = os.getenv("HCP_API_KEY", "")
    HCP_BASE_URL: str = os.getenv("HCP_BASE_URL", "https://api.housecallpro.com")

    # Lead Source Configuration
    # NOTE: Lead source must exist in HCP before using.
    HCP_LEAD_SOURCE: str = os.getenv("HCP_LEAD_SOURCE", "Website")
    # Tags removed per user request - not adding any tags to leads or customers
    HCP_LEAD_TAG: str = os.getenv("HCP_LEAD_TAG", "")
    HCP_WEBSITE_TAG: str = os.getenv("HCP_WEBSITE_TAG", "")

    # Assigned Employee for Website Leads
    HCP_ASSIGNED_EMPLOYEE_ID: str = os.getenv("HCP_ASSIGNED_EMPLOYEE_ID", "pro_dabb388b3e684c618867cd4ec0d12930")

    # Default Values
    DEFAULT_AREA_CODE: str = os.getenv("DEFAULT_AREA_CODE", "415")
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/Los_Angeles")
    DEFAULT_STATE: str = os.getenv("DEFAULT_STATE", "CA")  # Default state for addresses

    # Rate Limiting
    API_RATE_LIMIT_DELAY: float = float(os.getenv("API_RATE_LIMIT_DELAY", "2.0"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Service Configuration
    PORT: int = int(os.getenv("PORT", "8080"))

    # Customer Matching Configuration
    MATCH_CONFIDENCE_THRESHOLD: float = float(os.getenv("MATCH_CONFIDENCE_THRESHOLD", "0.8"))

    # Field Names (customizable based on Elfsight form)
    FORM_FIELD_NAME: str = os.getenv("FORM_FIELD_NAME", "name")
    FORM_FIELD_EMAIL: str = os.getenv("FORM_FIELD_EMAIL", "email")
    FORM_FIELD_PHONE: str = os.getenv("FORM_FIELD_PHONE", "phone")
    FORM_FIELD_ADDRESS: str = os.getenv("FORM_FIELD_ADDRESS", "address")
    FORM_FIELD_MESSAGE: str = os.getenv("FORM_FIELD_MESSAGE", "message")
    FORM_FIELD_CUSTOMER_TYPE: str = os.getenv("FORM_FIELD_CUSTOMER_TYPE", "customer_type")

    # Service Detail to HCP Service Name Mapping
    SERVICE_DETAIL_MAPPING: dict[str, str] = {
        "Toilets or Bidets": "Toilet Repair & Replacement",
        "Garbage Disposal": "Garbage Disposal Service",
        "Plumbing Fixtures": "Faucet & Fixture Service",
        "Water Heater": "Water Heater Service",
        "Boilers / Combi-Boilers": "Boiler & Hydronics Service",
        "Steam / Sauna": "Steam & Sauna Service",
        "Other Plumbing": "Other Plumbing Service",
        "Other Heating & HVAC": "Other Heating Service"
    }

    # Service Needed to HCP Job Type Mapping
    JOB_TYPE_MAPPING: dict[str, str] = {
        "New Installation": "Plumbing Installation",
        "Service or Repair": "Plumbing Demand Maintenance",
        "Renovation or Remodel": "Plumbing Estimate"
    }

    @classmethod
    def validate(cls) -> tuple[bool, Optional[str]]:
        """
        Validate required configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not cls.HCP_API_KEY:
            return False, "HCP_API_KEY is required"

        if not cls.HCP_BASE_URL:
            return False, "HCP_BASE_URL is required"

        return True, None

    @classmethod
    def get_hcp_headers(cls) -> dict[str, str]:
        """Get headers for HCP API requests"""
        return {
            "Authorization": f"Bearer {cls.HCP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    @classmethod
    def get_api_url(cls, endpoint: str) -> str:
        """
        Construct full API URL.

        Args:
            endpoint: API endpoint path (e.g., "/customers")

        Returns:
            Full API URL
        """
        base = cls.HCP_BASE_URL.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base}/{endpoint}"


# Validate configuration on import
is_valid, error = Config.validate()
if not is_valid:
    import sys
    print(f"Configuration error: {error}", file=sys.stderr)
    # Don't exit in case we're running tests or in development
