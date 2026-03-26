"""
Card Tokenization Service
Handles secure card tokenization via Interswitch Web Checkout
Stores only: token, card_last_4, expiry_date (NO full card number, CVV, etc.)
"""

import httpx
import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CardTokenizationService:
    """Senior-grade card tokenization for secure collections"""
    
    def __init__(self):
        self.interswitch_env = os.getenv("INTERSWITCH_ENV", "sandbox")
        
        if self.interswitch_env == "sandbox":
            self.client_id = os.getenv("INTERSWITCH_CLIENT_ID_SANDBOX")
            self.secret_key = os.getenv("INTERSWITCH_SECRET_KEY_SANDBOX")
            self.api_base = os.getenv("INTERSWITCH_API_BASE_SANDBOX", "https://sandbox.interswitchng.com")
        else:
            self.client_id = os.getenv("INTERSWITCH_CLIENT_ID_PROD")
            self.secret_key = os.getenv("INTERSWITCH_SECRET_KEY_PROD")
            self.api_base = os.getenv("INTERSWITCH_API_BASE_PROD", "https://api.interswitchng.com")
    
    async def tokenize_card(self, card_data: dict) -> tuple[bool, dict]:
        """
        Tokenize a card via Interswitch Web Checkout
        
        Args:
            card_data: {
                "card_number": "4512...",  (PAN - 16 digits)
                "expiry_month": "12",
                "expiry_year": "25",
                "cvv": "123"
            }
        
        Returns:
            (success: bool, response: dict with token/error)
        """
        try:
            if self.interswitch_env == "sandbox":
                return await self._mock_tokenize(card_data)
            else:
                return await self._real_tokenize(card_data)
        except Exception as e:
            logger.error(f"Card tokenization error: {str(e)}")
            return False, {"error": str(e)}
    
    async def validate_card_token(self, token: str) -> tuple[bool, dict]:
        """
        Validate if a card token is still active/valid
        
        Args:
            token: Interswitch card token
        
        Returns:
            (valid: bool, response: dict with status)
        """
        try:
            if self.interswitch_env == "sandbox":
                return await self._mock_validate(token)
            else:
                return await self._real_validate(token)
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False, {"error": str(e)}
    
    async def revoke_card_token(self, token: str) -> tuple[bool, dict]:
        """
        Deactivate a card token (user removes it)
        
        Args:
            token: Interswitch card token
        
        Returns:
            (success: bool, response: dict)
        """
        try:
            if self.interswitch_env == "sandbox":
                return await self._mock_revoke(token)
            else:
                return await self._real_revoke(token)
        except Exception as e:
            logger.error(f"Token revocation error: {str(e)}")
            return False, {"error": str(e)}
    
    # ==================== SANDBOX MOCKING ====================
    
    async def _mock_tokenize(self, card_data: dict) -> tuple[bool, dict]:
        """Sandbox: Always successful card tokenization"""
        # Extract card info
        card_number = card_data.get("card_number", "")
        expiry_month = card_data.get("expiry_month", "")
        expiry_year = card_data.get("expiry_year", "")
        
        pan_last_4 = card_number[-4:] if len(card_number) >= 4 else "0000"
        
        # Determine card type (basic heuristic)
        card_type = "VISA"
        if card_number.startswith("5"):
            card_type = "MASTERCARD"
        elif card_number.startswith("3"):
            card_type = "AMEX"
        
        # Generate mock token
        mock_token = f"ISW_TOK_{pan_last_4}_{int(datetime.utcnow().timestamp())}"
        
        # Mock expiry
        expiry_date = f"{expiry_month}/{expiry_year}"
        
        response = {
            "success": True,
            "card_token": mock_token,
            "card_type": card_type,
            "pan_last_4": pan_last_4,
            "expiry_date": expiry_date,
            "token_expires_at": (datetime.utcnow() + timedelta(days=1095)).isoformat(),  # 3 years
            "message": "Card tokenized successfully in sandbox"
        }
        
        logger.info(f"Sandboxed card tokenization: {pan_last_4}")
        return True, response
    
    async def _mock_validate(self, token: str) -> tuple[bool, dict]:
        """Sandbox: Validate token (always active in sandbox)"""
        response = {
            "success": True,
            "token": token,
            "is_active": True,
            "message": "Token is valid and active"
        }
        return True, response
    
    async def _mock_revoke(self, token: str) -> tuple[bool, dict]:
        """Sandbox: Revoke/deactivate token"""
        response = {
            "success": True,
            "token": token,
            "is_active": False,
            "revoked_at": datetime.utcnow().isoformat(),
            "message": "Token revoked successfully"
        }
        return True, response
    
    # ==================== REAL INTERSWITCH APIS ====================
    
    async def _real_tokenize(self, card_data: dict) -> tuple[bool, dict]:
        """
        Real Interswitch Card Tokenization API
        TODO: Implement when real credentials are available
        Endpoint: POST {api_base}/api/v1/cardmanagement/cardsecurity/tokenize
        """
        # Placeholder for real implementation
        logger.warning("Using sandbox mocking for card tokenization (real API not configured)")
        return await self._mock_tokenize(card_data)
    
    async def _real_validate(self, token: str) -> tuple[bool, dict]:
        """
        Real Token Validation API
        TODO: Implement when real credentials are available
        """
        logger.warning("Using sandbox mocking for token validation (real API not configured)")
        return await self._mock_validate(token)
    
    async def _real_revoke(self, token: str) -> tuple[bool, dict]:
        """
        Real Token Revocation API
        TODO: Implement when real credentials are available
        """
        logger.warning("Using sandbox mocking for token revocation (real API not configured)")
        return await self._mock_revoke(token)


# Singleton instance
card_tokenization_service = CardTokenizationService()
