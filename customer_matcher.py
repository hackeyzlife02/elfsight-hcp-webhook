"""
Customer matching logic for determining if a form submission matches an existing customer.

Implements smart matching based on phone, email, and name with confidence scoring.
"""

import logging
from typing import Optional, Dict, List, Any, Tuple
from difflib import SequenceMatcher
from utils import normalize_phone, parse_address, compare_addresses

logger = logging.getLogger(__name__)


class MatchResult:
    """Result of customer matching operation"""

    def __init__(
        self,
        match_type: str,
        confidence: float,
        customer_id: Optional[str] = None,
        customer_data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        should_create_new: bool = False
    ):
        self.match_type = match_type  # 'exact', 'partial', 'none'
        self.confidence = confidence  # 0.0 to 1.0
        self.customer_id = customer_id
        self.customer_data = customer_data
        self.warnings = warnings or []
        self.should_create_new = should_create_new

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "match_type": self.match_type,
            "confidence": self.confidence,
            "customer_id": self.customer_id,
            "customer_data": self.customer_data,
            "warnings": self.warnings,
            "should_create_new": self.should_create_new
        }


class CustomerMatcher:
    """Handles customer matching logic"""

    def __init__(self, hcp_client):
        """
        Initialize customer matcher.

        Args:
            hcp_client: HCPClient instance
        """
        self.hcp_client = hcp_client

    def find_matching_customer(
        self,
        phone: Optional[str],
        email: Optional[str],
        name: Optional[str],
        address: Optional[Dict[str, Optional[str]]],
        is_existing_customer: bool = False
    ) -> MatchResult:
        """
        Find matching customer in HCP.

        Args:
            phone: Normalized phone number
            email: Email address
            name: Full name
            address: Parsed address dictionary
            is_existing_customer: True if form indicates "Existing Customer"

        Returns:
            MatchResult with match information

        Matching Logic:
        1. Search by phone and email
        2. Exact match: Both phone AND email match → Use existing customer
        3. Partial match: Phone OR email matches → Depends on is_existing_customer flag
           - If existing: Use matched customer with warning
           - If new: Create new customer with warning
        4. No match: Create new customer
        """
        logger.info(f"Searching for customer: phone={phone}, email={email}, name={name}")

        phone_matches = []
        email_matches = []

        # Search by phone
        if phone:
            phone_matches = self.hcp_client.search_customers(phone)
            logger.info(f"Found {len(phone_matches)} customers by phone")

        # Search by email
        if email:
            email_matches = self.hcp_client.search_customers(email)
            logger.info(f"Found {len(email_matches)} customers by email")

        # Find intersection (exact matches)
        exact_matches = self._find_exact_matches(phone_matches, email_matches)

        if exact_matches:
            # Exact match found
            logger.info(f"Found {len(exact_matches)} exact matches")
            best_match = self._select_best_match(exact_matches, name, address)

            return MatchResult(
                match_type="exact",
                confidence=1.0,
                customer_id=best_match["id"],
                customer_data=best_match,
                warnings=[],
                should_create_new=False
            )

        # Check for partial matches
        all_matches = self._deduplicate_customers(phone_matches + email_matches)

        if all_matches:
            # Partial match found
            logger.info(f"Found {len(all_matches)} partial matches")
            best_match = self._select_best_match(all_matches, name, address)

            # Calculate confidence based on what matched
            confidence = self._calculate_confidence(best_match, phone, email, name)

            warnings = []
            matched_fields = []

            if phone and self._customer_has_phone(best_match, phone):
                matched_fields.append("phone")
            if email and self._customer_has_email(best_match, email):
                matched_fields.append("email")

            warnings.append(
                f"Partial match: {' and '.join(matched_fields)} matched, "
                f"but not all fields. Please verify this is the correct customer."
            )

            # Decision based on is_existing_customer flag
            if is_existing_customer:
                # User says they're existing, use the matched customer
                logger.info("Using matched customer (user indicated existing)")
                return MatchResult(
                    match_type="partial",
                    confidence=confidence,
                    customer_id=best_match["id"],
                    customer_data=best_match,
                    warnings=warnings,
                    should_create_new=False
                )
            else:
                # User says they're new, but we found a match - flag for review
                logger.warning("User says new customer, but found potential match")
                warnings.append(
                    "⚠️ User indicated NEW customer, but potential duplicate found. "
                    "Creating new customer record. Please review and merge if duplicate."
                )
                return MatchResult(
                    match_type="partial",
                    confidence=confidence,
                    customer_id=None,
                    customer_data=best_match,  # Include for reference
                    warnings=warnings,
                    should_create_new=True
                )

        # No matches found
        logger.info("No matching customers found")
        return MatchResult(
            match_type="none",
            confidence=0.0,
            customer_id=None,
            customer_data=None,
            warnings=[],
            should_create_new=True
        )

    def _find_exact_matches(
        self,
        phone_matches: List[Dict],
        email_matches: List[Dict]
    ) -> List[Dict]:
        """
        Find customers that appear in both phone and email matches.

        Args:
            phone_matches: Customers matching phone
            email_matches: Customers matching email

        Returns:
            List of customers in both lists
        """
        if not phone_matches or not email_matches:
            return []

        phone_ids = {c["id"] for c in phone_matches}
        exact = [c for c in email_matches if c["id"] in phone_ids]

        return exact

    def _deduplicate_customers(self, customers: List[Dict]) -> List[Dict]:
        """
        Remove duplicate customers from list.

        Args:
            customers: List of customer dictionaries

        Returns:
            Deduplicated list
        """
        seen = set()
        unique = []

        for customer in customers:
            customer_id = customer.get("id")
            if customer_id and customer_id not in seen:
                seen.add(customer_id)
                unique.append(customer)

        return unique

    def _select_best_match(
        self,
        candidates: List[Dict],
        name: Optional[str],
        address: Optional[Dict[str, Optional[str]]]
    ) -> Dict[str, Any]:
        """
        Select best matching customer from candidates.

        Args:
            candidates: List of candidate customers
            name: Name to match against
            address: Address to match against

        Returns:
            Best matching customer
        """
        if len(candidates) == 1:
            return candidates[0]

        # Score each candidate
        scored = []
        for candidate in candidates:
            score = 0.0

            # Name similarity
            if name:
                candidate_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
                if candidate_name:
                    name_similarity = SequenceMatcher(None, name.lower(), candidate_name.lower()).ratio()
                    score += name_similarity * 0.5

            # Address similarity
            if address and candidate.get("addresses"):
                for cand_addr in candidate["addresses"]:
                    addr_similarity = compare_addresses(address, cand_addr)
                    score = max(score, score + addr_similarity * 0.5)

            scored.append((score, candidate))

        # Return highest scoring candidate
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _calculate_confidence(
        self,
        customer: Dict[str, Any],
        phone: Optional[str],
        email: Optional[str],
        name: Optional[str]
    ) -> float:
        """
        Calculate confidence score for a match.

        Args:
            customer: Matched customer
            phone: Phone to check
            email: Email to check
            name: Name to check

        Returns:
            Confidence score 0.0 to 1.0
        """
        score = 0.0
        factors = 0

        # Phone match (40% weight)
        if phone:
            factors += 1
            if self._customer_has_phone(customer, phone):
                score += 0.4

        # Email match (40% weight)
        if email:
            factors += 1
            if self._customer_has_email(customer, email):
                score += 0.4

        # Name similarity (20% weight)
        if name:
            factors += 1
            customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
            if customer_name:
                name_similarity = SequenceMatcher(None, name.lower(), customer_name.lower()).ratio()
                score += name_similarity * 0.2

        return score

    def _customer_has_phone(self, customer: Dict[str, Any], phone: str) -> bool:
        """Check if customer has matching phone number"""
        customer_phone = normalize_phone(customer.get("mobile_number") or customer.get("home_number") or "")
        return customer_phone == phone if customer_phone else False

    def _customer_has_email(self, customer: Dict[str, Any], email: str) -> bool:
        """Check if customer has matching email"""
        customer_email = (customer.get("email") or "").lower().strip()
        return customer_email == email.lower().strip() if customer_email else False

    def should_create_new_address(
        self,
        customer: Dict[str, Any],
        new_address: Dict[str, Optional[str]]
    ) -> bool:
        """
        Determine if a new address should be created for customer.

        Args:
            customer: Existing customer data
            new_address: New address from form

        Returns:
            True if new address should be created
        """
        if not new_address or not any(new_address.values()):
            return False

        existing_addresses = customer.get("addresses", [])
        if not existing_addresses:
            return True

        # Check if address is similar to any existing address
        for existing_addr in existing_addresses:
            similarity = compare_addresses(new_address, existing_addr)
            if similarity > 0.8:  # 80% similar
                logger.info(f"Address is {similarity:.0%} similar to existing, not creating new")
                return False

        # Address is different enough, create new one
        logger.info("Address is different from existing addresses, will create new")
        return True
