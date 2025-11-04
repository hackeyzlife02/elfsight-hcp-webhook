"""
Lead creation orchestration.

Handles the complete workflow of creating leads/jobs from Elfsight form submissions.
"""

import logging
from typing import Dict, Any, Optional, List
from hcp_client import HCPClient
from customer_matcher import CustomerMatcher, MatchResult
from utils import normalize_phone, parse_name, parse_address, format_note, sanitize_string
from config import Config

logger = logging.getLogger(__name__)


class LeadCreationResult:
    """Result of lead creation operation"""

    def __init__(
        self,
        success: bool,
        customer_id: Optional[str] = None,
        job_id: Optional[str] = None,
        message: str = "",
        warnings: Optional[list] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.customer_id = customer_id
        self.job_id = job_id
        self.message = message
        self.warnings = warnings or []
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "customer_id": self.customer_id,
            "job_id": self.job_id,
            "message": self.message,
            "warnings": self.warnings,
            "error": self.error
        }


class LeadCreator:
    """Handles lead creation from form submissions"""

    def __init__(self, hcp_client: Optional[HCPClient] = None):
        """
        Initialize lead creator.

        Args:
            hcp_client: HCPClient instance (creates new one if not provided)
        """
        self.hcp_client = hcp_client or HCPClient()
        self.matcher = CustomerMatcher(self.hcp_client)

    def parse_elfsight_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Elfsight webhook payload into structured form data.

        Expected Elfsight payload structure:
        [
            {"id": "field1", "name": "First Name", "value": "Sarah", "type": "short_text"},
            {"id": "field2", "name": "Email Address", "value": "sarah@test.com", "type": "email"},
            ...
        ]

        Args:
            payload: Raw Elfsight webhook payload

        Returns:
            Parsed form data dictionary
        """
        form_data = {}

        # If payload is a list (Elfsight format)
        if isinstance(payload, list):
            for field in payload:
                field_name = field.get("name", "").lower().strip()
                field_value = field.get("value", "")
                field_type = field.get("type", "")

                # Map field names to our standard keys
                if "first name" in field_name or field_name == "first_name":
                    form_data["first_name"] = field_value
                elif "last name" in field_name or field_name == "last_name":
                    form_data["last_name"] = field_value
                elif "email" in field_name:
                    form_data["email"] = field_value
                elif "phone" in field_name:
                    form_data["phone"] = field_value
                elif "street address line 2" in field_name:
                    form_data["street_line_2"] = field_value
                elif "street address" in field_name:
                    form_data["street"] = field_value
                elif "city" in field_name:
                    form_data["city"] = field_value
                elif "state" in field_name and "service" not in field_name:
                    # Capture state field (but not "service_request_details")
                    form_data["state"] = field_value
                elif "postal" in field_name or "zip" in field_name:
                    form_data["zip"] = field_value
                elif "new or existing" in field_name or "are you" in field_name:
                    form_data["customer_type"] = field_value
                elif "preferred method" in field_name or "contact method" in field_name:
                    form_data["preferred_contact"] = field_value
                elif "sms" in field_name and "consent" in field_name:
                    # Consent checkbox - value is boolean or string "true"/"false"
                    form_data["sms_consent"] = field_value in [True, "true", "True", "yes", "Yes"]
                elif "service needed" in field_name:
                    form_data["service_needed"] = field_value
                elif "service details" in field_name:
                    # Multi-select field - value might be array or comma-separated string
                    if isinstance(field_value, list):
                        form_data["service_details"] = field_value
                    elif field_value:
                        form_data["service_details"] = [v.strip() for v in field_value.split(",")]
                elif "service request details" in field_name or "request details" in field_name:
                    form_data["service_request_details"] = field_value
                elif "images" in field_name or "plans" in field_name or "specs" in field_name or field_type == "file":
                    # File attachments - value might be array of URLs or single URL
                    if isinstance(field_value, list):
                        form_data["file_attachments"] = field_value
                    elif field_value:
                        form_data["file_attachments"] = [field_value]
                else:
                    # Store other fields with their original name (cleaned)
                    clean_key = field_name.replace(" ", "_")
                    form_data[clean_key] = field_value

        # If payload is a dict (alternative format for testing)
        elif isinstance(payload, dict):
            form_data = payload

        # Combine first_name and last_name into full name if needed
        if "first_name" in form_data and "last_name" in form_data:
            form_data["name"] = f"{form_data['first_name']} {form_data['last_name']}".strip()
        elif "name" not in form_data and "first_name" in form_data:
            form_data["name"] = form_data["first_name"]

        # Combine address fields if we have street, city, zip
        if "street" in form_data or "city" in form_data or "zip" in form_data:
            address_parts = []
            if form_data.get("street"):
                address_parts.append(form_data["street"])
            if form_data.get("city"):
                address_parts.append(form_data["city"])
            if form_data.get("zip"):
                address_parts.append(form_data["zip"])
            if address_parts:
                form_data["address"] = ", ".join(address_parts)

        logger.info(f"Parsed form data: {list(form_data.keys())}")
        return form_data

    def create_lead(self, form_data: Dict[str, Any]) -> LeadCreationResult:
        """
        Create lead from form submission.

        Args:
            form_data: Parsed form data

        Returns:
            LeadCreationResult with outcome
        """
        try:
            # Extract and normalize data
            raw_phone = form_data.get("phone", "")
            email = sanitize_string(form_data.get("email", "")).lower()

            # Get name from first_name + last_name or fallback to "name"
            first_name = form_data.get("first_name", "")
            last_name = form_data.get("last_name", "")
            name = form_data.get("name", "")
            if not name and (first_name or last_name):
                name = f"{first_name} {last_name}".strip()
            elif not first_name and name:
                first_name, last_name = parse_name(name)

            # Address and other fields
            raw_address = form_data.get("address", "")
            customer_type = sanitize_string(form_data.get("customer_type", "")).lower()

            # New fields for notifications
            sms_consent = form_data.get("sms_consent", False)

            # Normalize phone
            phone = normalize_phone(raw_phone, Config.DEFAULT_AREA_CODE)
            if not phone:
                logger.warning(f"Could not normalize phone: {raw_phone}")

            # Parse address - check if we have individual fields or combined string
            if form_data.get("street") or form_data.get("city") or form_data.get("zip"):
                # Use individual fields directly (better than parsing)
                parsed_address = {
                    "street": form_data.get("street"),
                    "city": form_data.get("city"),
                    "state": form_data.get("state") or Config.DEFAULT_STATE,  # Default to CA
                    "zip": form_data.get("zip")
                }
            else:
                # Fall back to parsing combined address string
                parsed_address = parse_address(raw_address)

            # Determine if customer indicated they're existing
            is_existing_customer = "existing" in customer_type or "returning" in customer_type

            logger.info(f"Processing lead: {name} ({email}, {phone}), Existing: {is_existing_customer}")

            # Find matching customer
            match_result = self.matcher.find_matching_customer(
                phone=phone,
                email=email,
                name=name,
                address=parsed_address,
                is_existing_customer=is_existing_customer
            )

            logger.info(f"Match result: {match_result.match_type}, confidence: {match_result.confidence:.0%}")

            # Determine customer ID
            customer_id = None
            new_address_id = None  # Track newly created address ID

            if match_result.should_create_new:
                # Create new customer
                logger.info("Creating new customer")
                customer_id = self._create_customer(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    phone=phone,
                    address=parsed_address,
                    sms_consent=sms_consent
                )

                if not customer_id:
                    return LeadCreationResult(
                        success=False,
                        error="Failed to create customer"
                    )

            else:
                # Use existing customer
                customer_id = match_result.customer_id
                logger.info(f"Using existing customer: {customer_id}")

                # Check if we need to add new address and capture the address_id
                if parsed_address and match_result.customer_data:
                    if self.matcher.should_create_new_address(match_result.customer_data, parsed_address):
                        new_address_id = self._add_address_to_customer(customer_id, parsed_address)
                        if new_address_id:
                            logger.info(f"Created new address with ID: {new_address_id}")

            # Build line items before creating lead
            line_items = None
            service_details = form_data.get("service_details", [])
            if service_details:
                logger.info(f"Building {len(service_details)} line items for lead")
                service_request_details = form_data.get("service_request_details", "")
                line_items = self._build_line_items(
                    service_details=service_details,
                    service_request_details=service_request_details
                )

            # Build note text before creating lead
            from utils import format_lead_note
            note_text = format_lead_note(form_data, match_result.to_dict())

            # Determine address_id and address fields for lead
            address_id = None
            address_for_lead = None

            # For NEW customers: use parsed address directly (no address_id)
            if match_result.should_create_new:
                address_for_lead = self._build_address_dict(parsed_address)
                logger.info("Using parsed address for new customer lead")

            # For EXISTING customers: get address_id and fetch full address details
            else:
                # If we just created a new address, use that
                if new_address_id:
                    address_id = new_address_id
                    logger.info(f"Using newly created address_id: {address_id}")
                # Otherwise, try to find matching existing address
                elif customer_id and parsed_address:
                    # Fetch customer's addresses with IDs from API
                    customer_addresses = self.hcp_client.get_customer_addresses(customer_id)
                    if customer_addresses:
                        matched_address = self._find_matching_address_from_list(
                            customer_addresses,
                            parsed_address
                        )
                        if matched_address:
                            address_id = matched_address.get("id")
                            logger.info(f"Using existing address_id: {address_id}")

                # If we have an address_id, fetch the full address details
                if address_id and customer_id:
                    full_address = self.hcp_client.get_address_by_id(customer_id, address_id)
                    if full_address:
                        address_for_lead = self._build_address_dict_from_api(full_address)
                        logger.info("Fetched full address details for lead")

            # Create LEAD with line items, note, and address included
            logger.info(f"Creating lead for customer {customer_id}")
            lead_id = self._create_lead_with_job_type(
                customer_id=customer_id,
                form_data=form_data,
                line_items=line_items,
                note=note_text,
                address_id=address_id,
                address=address_for_lead
            )

            if not lead_id:
                return LeadCreationResult(
                    success=False,
                    customer_id=customer_id,
                    error="Failed to create lead"
                )

            # Success!
            return LeadCreationResult(
                success=True,
                customer_id=customer_id,
                job_id=lead_id,  # Using job_id field for lead_id (backwards compatible)
                message=f"Lead created successfully (match type: {match_result.match_type})",
                warnings=match_result.warnings
            )

        except Exception as e:
            logger.exception(f"Error creating lead: {e}")
            return LeadCreationResult(
                success=False,
                error=str(e)
            )

    def _create_customer(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: Optional[str],
        address: Dict[str, Optional[str]],
        sms_consent: bool = False
    ) -> Optional[str]:
        """
        Create new customer in HCP.

        Args:
            first_name: First name
            last_name: Last name
            email: Email address
            phone: Normalized phone number
            address: Parsed address
            sms_consent: Whether customer consented to SMS notifications

        Returns:
            Customer ID or None on failure
        """
        customer_data = {
            "first_name": first_name or "Unknown",
            "last_name": last_name or "",
            "notifications_enabled": sms_consent  # Set based on SMS consent
        }

        # Add email if provided
        if email:
            customer_data["email"] = email

        # Add phone (HCP uses mobile_number field directly)
        if phone:
            # Keep +1 prefix format for mobile_number
            customer_data["mobile_number"] = phone

        # Only add lead_source if it's configured and not empty
        # (lead source must exist in HCP before it can be used)
        if Config.HCP_LEAD_SOURCE:
            customer_data["lead_source"] = Config.HCP_LEAD_SOURCE

        # Add address if provided (per HCP API docs: street and street_line_2)
        if address and any(address.values()):
            addr = {}
            if address.get("street"):
                addr["street"] = address["street"]
            if address.get("street_line_2"):
                addr["street_line_2"] = address["street_line_2"]
            if address.get("city"):
                addr["city"] = address["city"]
            if address.get("state"):
                addr["state"] = address["state"]
            if address.get("zip"):
                addr["zip"] = address["zip"]
            if address.get("country"):
                addr["country"] = address["country"]
            else:
                addr["country"] = "US"  # Default to US

            customer_data["addresses"] = [addr]

        # Add tags only if configured (not empty strings)
        tags = []
        if Config.HCP_LEAD_TAG and Config.HCP_LEAD_TAG.strip():
            tags.append(Config.HCP_LEAD_TAG)
        if Config.HCP_WEBSITE_TAG and Config.HCP_WEBSITE_TAG.strip():
            tags.append(Config.HCP_WEBSITE_TAG)
        if tags:
            customer_data["tags"] = tags

        result = self.hcp_client.create_customer(customer_data)
        if result:
            return result.get("id")
        return None

    def _build_address_dict(self, parsed_address: Dict[str, Optional[str]]) -> Optional[Dict[str, str]]:
        """
        Build address dict for lead from parsed address.

        Args:
            parsed_address: Parsed address from form

        Returns:
            Address dict for lead API, or None if no address
        """
        if not parsed_address or not any(parsed_address.values()):
            return None

        address = {}
        if parsed_address.get("street"):
            address["street"] = parsed_address["street"]
        if parsed_address.get("street_line_2"):
            address["street_line_2"] = parsed_address["street_line_2"]
        if parsed_address.get("city"):
            address["city"] = parsed_address["city"]
        # Always set state, default to CA if not provided
        address["state"] = parsed_address.get("state") or Config.DEFAULT_STATE
        if parsed_address.get("zip"):
            address["zip"] = parsed_address["zip"]
        if parsed_address.get("country"):
            address["country"] = parsed_address["country"]
        else:
            address["country"] = "US"

        return address if address else None

    def _build_address_dict_from_api(self, api_address: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Build address dict for lead from API address response.

        Args:
            api_address: Address from HCP API (with id, type, etc.)

        Returns:
            Address dict for lead API, or None if no address
        """
        if not api_address:
            return None

        address = {}
        if api_address.get("street"):
            address["street"] = api_address["street"]
        if api_address.get("street_line_2"):
            address["street_line_2"] = api_address["street_line_2"]
        if api_address.get("city"):
            address["city"] = api_address["city"]
        if api_address.get("state"):
            address["state"] = api_address["state"]
        if api_address.get("zip"):
            address["zip"] = api_address["zip"]
        if api_address.get("country"):
            address["country"] = api_address["country"]
        else:
            address["country"] = "US"

        return address if address else None

    def _find_matching_address_from_list(
        self,
        addresses: List[Dict[str, Any]],
        new_address: Dict[str, Optional[str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Find matching address in list of customer addresses.

        Args:
            addresses: List of address dicts from API (with IDs)
            new_address: Parsed address from form

        Returns:
            Matching address dict with 'id' field, or None if no match
        """
        from utils import compare_addresses

        if not addresses:
            return None

        # Compare new address with each existing address
        for existing_addr in addresses:
            # Convert existing address format to match parsed format
            existing_parsed = {
                "street": existing_addr.get("street"),
                "city": existing_addr.get("city"),
                "state": existing_addr.get("state"),
                "zip": existing_addr.get("zip")
            }

            similarity = compare_addresses(existing_parsed, new_address)
            logger.debug(f"Address similarity: {similarity:.2f} for address {existing_addr.get('id')}")

            # If similarity is high (80%+), consider it a match
            if similarity >= 0.8:
                logger.info(f"Found matching address with {similarity:.0%} similarity")
                return existing_addr

        return None

    def _add_address_to_customer(
        self,
        customer_id: str,
        address: Dict[str, Optional[str]]
    ) -> Optional[str]:
        """
        Add address to existing customer.

        Args:
            customer_id: Customer ID
            address: Parsed address

        Returns:
            Address ID if successful, None otherwise
        """
        if not address or not any(address.values()):
            return None

        address_data = {
            "type": "service"
        }

        # Use HCP field names per API docs: street and street_line_2
        if address.get("street"):
            address_data["street"] = address["street"]
        if address.get("street_line_2"):
            address_data["street_line_2"] = address["street_line_2"]
        if address.get("city"):
            address_data["city"] = address["city"]
        # Always set state, default to CA if not provided
        address_data["state"] = address.get("state") or Config.DEFAULT_STATE
        if address.get("zip"):
            address_data["zip"] = address["zip"]
        if address.get("country"):
            address_data["country"] = address["country"]
        else:
            address_data["country"] = "US"

        result = self.hcp_client.add_customer_address(customer_id, address_data)
        if result:
            return result.get("id")
        return None

    def _create_job(
        self,
        customer_id: str,
        message: str,
        form_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Create job for customer.

        Args:
            customer_id: Customer ID
            message: Job description/message
            form_data: Original form data

        Returns:
            Job ID or None on failure
        """
        # Build job description
        if message:
            description = f"Website inquiry: {message}"
        else:
            description = "Website inquiry from Elfsight form"

        job_data = {
            "customer_id": customer_id,
            "description": description,
            "work_status": "unscheduled"
        }

        # Add tags only if configured (not empty strings)
        tags = []
        if Config.HCP_LEAD_TAG and Config.HCP_LEAD_TAG.strip():
            tags.append(Config.HCP_LEAD_TAG)
        if Config.HCP_WEBSITE_TAG and Config.HCP_WEBSITE_TAG.strip():
            tags.append(Config.HCP_WEBSITE_TAG)
        if tags:
            job_data["tags"] = tags

        # Only add lead_source if it's configured and not empty
        # (lead source must exist in HCP before it can be used)
        if Config.HCP_LEAD_SOURCE:
            job_data["lead_source"] = Config.HCP_LEAD_SOURCE

        result = self.hcp_client.create_job(job_data)
        if result:
            return result.get("id")
        return None

    def _create_lead_with_job_type(
        self,
        customer_id: str,
        form_data: Dict[str, Any],
        line_items: Optional[list] = None,
        note: Optional[str] = None,
        address_id: Optional[str] = None,
        address: Optional[Dict[str, str]] = None
    ) -> Optional[str]:
        """
        Create lead for customer with appropriate job_type mapping.

        According to HCP API docs, line_items, note, and address can be included
        directly in the create lead request.

        Args:
            customer_id: Customer ID
            form_data: Original form data
            line_items: Optional list of line item dicts to include
            note: Optional note text to include
            address_id: Optional address ID to use for existing customer
            address: Optional address dict with full address fields

        Returns:
            Lead ID or None on failure
        """
        # Map "Service Needed" to job_type
        service_needed = form_data.get("service_needed", "")
        job_type = Config.JOB_TYPE_MAPPING.get(service_needed, "")

        if not job_type:
            logger.warning(f"No job_type mapping for: {service_needed}")
            job_type = "Plumbing Demand Maintenance"  # Default fallback

        lead_data = {
            "customer_id": customer_id,
            "job_type": job_type
        }

        # Add assigned employee for website leads
        if Config.HCP_ASSIGNED_EMPLOYEE_ID:
            lead_data["assigned_employee_id"] = Config.HCP_ASSIGNED_EMPLOYEE_ID
            logger.debug(f"Assigning to employee: {Config.HCP_ASSIGNED_EMPLOYEE_ID}")

        # Add address_id if provided (for existing customer with address)
        if address_id:
            lead_data["address_id"] = address_id
            logger.debug(f"Including address_id: {address_id}")

        # Add address fields if provided
        if address:
            lead_data["address"] = address
            logger.debug(f"Including address: {address.get('street')}, {address.get('city')}, {address.get('state')} {address.get('zip')}")

        # Add tags only if configured (not empty strings)
        tags = []
        if Config.HCP_LEAD_TAG and Config.HCP_LEAD_TAG.strip():
            tags.append(Config.HCP_LEAD_TAG)
        if Config.HCP_WEBSITE_TAG and Config.HCP_WEBSITE_TAG.strip():
            tags.append(Config.HCP_WEBSITE_TAG)
        if tags:
            lead_data["tags"] = tags

        # Only add lead_source if configured
        if Config.HCP_LEAD_SOURCE:
            lead_data["lead_source"] = Config.HCP_LEAD_SOURCE

        # Include line items if provided
        if line_items:
            lead_data["line_items"] = line_items
            logger.debug(f"Including {len(line_items)} line items in lead creation")

        # Include note if provided
        if note:
            lead_data["note"] = note
            logger.debug("Including note in lead creation")

        logger.debug(f"Creating lead with job_type: {job_type}")
        result = self.hcp_client.create_lead(lead_data)
        if result:
            return result.get("id")
        return None

    def _build_line_items(
        self,
        service_details: list,
        service_request_details: str = ""
    ) -> Optional[list]:
        """
        Build line items array based on selected services.

        This method builds the line items data structure that will be
        included in the create lead request.

        Args:
            service_details: List of service detail selections from form
            service_request_details: Optional description to add to first line item

        Returns:
            List of line item dicts, or None if no service details
        """
        if not service_details:
            logger.warning("No service details provided for line items")
            return None

        line_items = []

        for idx, service_detail in enumerate(service_details):
            # Map form service name to HCP service name
            hcp_service_name = Config.SERVICE_DETAIL_MAPPING.get(service_detail)

            if not hcp_service_name:
                logger.warning(f"No mapping found for service: {service_detail}")
                hcp_service_name = service_detail  # Use original if no mapping

            line_item = {
                "name": hcp_service_name,
                "kind": "labor"
            }

            # Add service request details to first line item only
            if idx == 0 and service_request_details:
                line_item["description"] = service_request_details

            line_items.append(line_item)

        logger.debug(f"Built {len(line_items)} line items: {[item['name'] for item in line_items]}")
        return line_items
