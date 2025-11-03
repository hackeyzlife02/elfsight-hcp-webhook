"""
HCP (Housecall Pro) API Client.

Provides methods for interacting with the Housecall Pro API.
Based on patterns from existing HCP integration scripts and API documentation.
"""

import time
import logging
import requests
from typing import Optional, Dict, List, Any
from config import Config

logger = logging.getLogger(__name__)


class HCPAPIError(Exception):
    """Custom exception for HCP API errors"""
    pass


class HCPClient:
    """Client for Housecall Pro API"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize HCP API client.

        Args:
            api_key: HCP API key (defaults to Config.HCP_API_KEY)
            base_url: HCP API base URL (defaults to Config.HCP_BASE_URL)
        """
        self.api_key = api_key or Config.HCP_API_KEY
        self.base_url = base_url or Config.HCP_BASE_URL
        self.session = requests.Session()
        self.session.headers.update(Config.get_hcp_headers())

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retry_count: int = 3
    ) -> Dict[str, Any]:
        """
        Make HTTP request to HCP API with rate limiting and retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/customers")
            params: Query parameters
            json_data: JSON body data
            retry_count: Number of retries on failure

        Returns:
            Response JSON data

        Raises:
            HCPAPIError: If request fails after retries
        """
        url = Config.get_api_url(endpoint)

        for attempt in range(retry_count):
            try:
                logger.debug(f"{method} {url} (attempt {attempt + 1}/{retry_count})")

                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    timeout=30
                )

                # Log response for debugging
                logger.debug(f"Response status: {response.status_code}")

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                # Raise for HTTP errors
                response.raise_for_status()

                # Rate limiting: wait between requests
                time.sleep(Config.API_RATE_LIMIT_DELAY)

                return response.json()

            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error: {e}")
                if e.response is not None:
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                else:
                    logger.error("No response received")

                if attempt == retry_count - 1:
                    raise HCPAPIError(f"HTTP error after {retry_count} attempts: {e}")

                time.sleep(2 ** attempt)  # Exponential backoff

            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")

                if attempt == retry_count - 1:
                    raise HCPAPIError(f"Request failed after {retry_count} attempts: {e}")

                time.sleep(2 ** attempt)  # Exponential backoff

        raise HCPAPIError(f"Request failed after {retry_count} attempts")

    def search_customers(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for customers by email, phone, or name.

        Args:
            query: Search query (email, phone, or name)

        Returns:
            List of matching customers

        Example:
            >>> client.search_customers("john@example.com")
            [{"id": "abc123", "email": "john@example.com", ...}]
        """
        try:
            response = self._request(
                method="GET",
                endpoint="/customers",
                params={"q": query}
            )

            customers = response.get("customers", [])
            logger.info(f"Found {len(customers)} customers matching '{query}'")
            return customers

        except HCPAPIError as e:
            logger.error(f"Error searching customers: {e}")
            return []

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get customer by ID.

        Args:
            customer_id: HCP customer ID

        Returns:
            Customer data or None if not found
        """
        try:
            response = self._request(
                method="GET",
                endpoint=f"/customers/{customer_id}"
            )
            # GET endpoints might return data directly or wrapped
            # Return the response as-is
            return response

        except HCPAPIError as e:
            logger.error(f"Error getting customer {customer_id}: {e}")
            return None

    def create_customer(self, customer_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new customer.

        Args:
            customer_data: Customer data following HCP API schema

        Returns:
            Created customer data or None on failure

        Example:
            >>> client.create_customer({
            ...     "first_name": "John",
            ...     "last_name": "Smith",
            ...     "email": "john@example.com",
            ...     "mobile_number": "+14155551234",
            ...     "lead_source": "Elfsight Form"
            ... })
        """
        try:
            logger.debug(f"Creating customer with data: {customer_data}")
            response = self._request(
                method="POST",
                endpoint="/customers",
                json_data=customer_data
            )

            logger.debug(f"Create customer response: {response}")

            # HCP returns customer data directly (no wrapper key)
            # Response has 'id' field if successful
            if response and response.get("id"):
                logger.info(f"Created customer: {response.get('id')}")
                return response
            else:
                logger.warning(f"No customer ID in response. Full response: {response}")
                return None

        except HCPAPIError as e:
            logger.error(f"Error creating customer: {e}")
            return None

    def add_customer_address(
        self,
        customer_id: str,
        address_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Add address to existing customer.

        Args:
            customer_id: HCP customer ID
            address_data: Address data

        Returns:
            Created address data or None on failure

        Example:
            >>> client.add_customer_address("customer_id", {
            ...     "type": "service",
            ...     "street": "123 Main St",
            ...     "city": "San Francisco",
            ...     "state": "CA",
            ...     "zip": "94102"
            ... })
        """
        try:
            response = self._request(
                method="POST",
                endpoint=f"/customers/{customer_id}/addresses",
                json_data=address_data
            )

            address = response.get("address")
            if address:
                logger.info(f"Added address to customer {customer_id}")
            return address

        except HCPAPIError as e:
            logger.error(f"Error adding address to customer {customer_id}: {e}")
            return None

    def create_job(self, job_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new job.

        Args:
            job_data: Job data following HCP API schema

        Returns:
            Created job data or None on failure

        Example:
            >>> client.create_job({
            ...     "customer_id": "abc123",
            ...     "description": "Website inquiry",
            ...     "work_status": "unscheduled",
            ...     "tags": ["Elfsight Lead", "Website"],
            ...     "lead_source": "Elfsight Form"
            ... })
        """
        try:
            response = self._request(
                method="POST",
                endpoint="/jobs",
                json_data=job_data
            )

            # HCP returns job data directly (no wrapper key)
            if response and response.get("id"):
                logger.info(f"Created job: {response.get('id')}")
                return response
            else:
                logger.warning(f"No job ID in response. Full response: {response}")
                return None

        except HCPAPIError as e:
            logger.error(f"Error creating job: {e}")
            return None

    def add_job_note(
        self,
        job_id: str,
        note: str,
        is_private: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Add note to job.

        Args:
            job_id: HCP job ID
            note: Note text
            is_private: Whether note is private (default: True)

        Returns:
            Created note data or None on failure
        """
        try:
            response = self._request(
                method="POST",
                endpoint=f"/jobs/{job_id}/notes",
                json_data={
                    "note": note,
                    "private": is_private
                }
            )

            note_data = response.get("note")
            if note_data:
                logger.info(f"Added note to job {job_id}")
            return note_data

        except HCPAPIError as e:
            logger.error(f"Error adding note to job {job_id}: {e}")
            return None

    def create_lead(self, lead_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new lead.

        Args:
            lead_data: Lead data following HCP API schema

        Returns:
            Created lead data or None on failure

        Example:
            >>> client.create_lead({
            ...     "customer_id": "abc123",
            ...     "job_type": "Plumbing Demand Maintenance",
            ...     "tags": ["Elfsight Lead", "Website"]
            ... })
        """
        try:
            logger.debug(f"Creating lead with data: {lead_data}")
            response = self._request(
                method="POST",
                endpoint="/leads",
                json_data=lead_data
            )

            logger.debug(f"Create lead response: {response}")
            # HCP returns lead data directly (no wrapper key)
            if response and response.get("id"):
                logger.info(f"Created lead: {response.get('id')}")
                return response
            else:
                logger.warning(f"No lead ID in response. Full response: {response}")
                return None

        except HCPAPIError as e:
            logger.error(f"Error creating lead: {e}")
            return None

    def add_lead_line_items(
        self,
        lead_id: str,
        line_items: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Add line items to a lead.

        Args:
            lead_id: HCP lead ID
            line_items: List of line item data dictionaries

        Returns:
            List of created line items or None on failure

        Example:
            >>> client.add_lead_line_items("lead_123", [{
            ...     "name": "Water Heater Service",
            ...     "kind": "labor",
            ...     "description": "Water heater repair"
            ... }])
        """
        try:
            logger.debug(f"Adding {len(line_items)} line items to lead {lead_id}")
            response = self._request(
                method="POST",
                endpoint=f"/leads/{lead_id}/line_items",
                json_data={"line_items": line_items}
            )

            logger.debug(f"Add line items response: {response}")
            created_items = response.get("line_items", [])
            if created_items:
                logger.info(f"Added {len(created_items)} line items to lead {lead_id}")
            return created_items

        except HCPAPIError as e:
            logger.error(f"Error adding line items to lead {lead_id}: {e}")
            return None

    def add_lead_note(
        self,
        lead_id: str,
        note: str,
        is_private: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Add note to lead.

        Args:
            lead_id: HCP lead ID
            note: Note text
            is_private: Whether note is private (default: True)

        Returns:
            Created note data or None on failure
        """
        try:
            response = self._request(
                method="POST",
                endpoint=f"/leads/{lead_id}/notes",
                json_data={
                    "note": note,
                    "private": is_private
                }
            )

            note_data = response.get("note")
            if note_data:
                logger.info(f"Added note to lead {lead_id}")
            return note_data

        except HCPAPIError as e:
            logger.error(f"Error adding note to lead {lead_id}: {e}")
            return None

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job by ID.

        Args:
            job_id: HCP job ID

        Returns:
            Job data or None if not found
        """
        try:
            response = self._request(
                method="GET",
                endpoint=f"/jobs/{job_id}"
            )
            # GET endpoints might return data directly or wrapped
            # Return the response as-is
            return response

        except HCPAPIError as e:
            logger.error(f"Error getting job {job_id}: {e}")
            return None

    def get_customer_addresses(self, customer_id: str) -> List[Dict[str, Any]]:
        """
        Get all addresses for a customer.

        Args:
            customer_id: HCP customer ID

        Returns:
            List of address dictionaries with IDs
        """
        try:
            response = self._request(
                method="GET",
                endpoint=f"/customers/{customer_id}/addresses"
            )

            addresses = response.get("addresses", [])
            logger.info(f"Found {len(addresses)} addresses for customer {customer_id}")
            return addresses

        except HCPAPIError as e:
            logger.error(f"Error getting addresses for customer {customer_id}: {e}")
            return []

    def get_address_by_id(
        self,
        customer_id: str,
        address_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific address by ID for a customer.

        Args:
            customer_id: HCP customer ID
            address_id: Address ID

        Returns:
            Address dictionary with all fields, or None on failure
        """
        try:
            response = self._request(
                method="GET",
                endpoint=f"/customers/{customer_id}/addresses/{address_id}"
            )

            logger.info(f"Retrieved address {address_id} for customer {customer_id}")
            return response

        except HCPAPIError as e:
            logger.error(f"Error getting address {address_id} for customer {customer_id}: {e}")
            return None

    def update_customer(
        self,
        customer_id: str,
        customer_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update existing customer.

        Args:
            customer_id: HCP customer ID
            customer_data: Customer data to update

        Returns:
            Updated customer data or None on failure
        """
        try:
            response = self._request(
                method="PUT",
                endpoint=f"/customers/{customer_id}",
                json_data=customer_data
            )

            customer = response.get("customer")
            if customer:
                logger.info(f"Updated customer: {customer_id}")
            return customer

        except HCPAPIError as e:
            logger.error(f"Error updating customer {customer_id}: {e}")
            return None
