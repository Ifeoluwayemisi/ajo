"""
Interswitch Integration Service
Handles all communication with Interswitch APIs for payments
"""

import requests
import json
import time
import uuid
import hashlib
from typing import Optional, Dict
from config import (
    INTERSWITCH_CLIENT_ID,
    INTERSWITCH_SECRET_KEY,
    INTERSWITCH_API_BASE,
    INTERSWITCH_ENV,
)
import logging

logger = logging.getLogger(__name__)


class InterswitchService:
    """
    Service to integrate with Interswitch payment APIs
    Handles tokenization, auto-debit, transfers, and GSI
    """
    
    def __init__(self):
        self.client_id = INTERSWITCH_CLIENT_ID
        self.secret_key = INTERSWITCH_SECRET_KEY
        self.base_url = INTERSWITCH_API_BASE
        self.environment = INTERSWITCH_ENV
        self.session = requests.Session()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.secret_key)

    def _service_unavailable(self, operation: str, amount: float | None = None) -> Dict:
        message = (
            f"Interswitch {operation} is not configured for environment '{self.environment}'. "
            "Set valid Interswitch credentials to enable this operation."
        )
        logger.error(message)
        return {
            "success": False,
            "ref": None,
            "message": message,
            "amount": amount,
        }
    
    def _generate_signature(self, http_method: str, url: str) -> Dict:
        """
        Generate Interswitch authentication headers
        Uses SHA512 signature method
        """
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4()).replace("-", "")
        
        # Signature formula: HTTP_METHOD & URL & TIMESTAMP & NONCE & CLIENT_ID & SECRET_KEY
        signature_base = f"{http_method}&{url}&{timestamp}&{nonce}&{self.client_id}&{self.secret_key}"
        signature = hashlib.sha512(signature_base.encode()).hexdigest()
        
        return {
            "Authorization": f"InterswitchAuth {self.client_id}",
            "Timestamp": timestamp,
            "Nonce": nonce,
            "Signature": signature,
            "SignatureMethod": "SHA512",
            "Content-Type": "application/json"
        }
    
    async def tokenize_card(self, user_id: str, card_data: Dict) -> Optional[str]:
        """
        Tokenize user's card via Interswitch
        Input: { card_number, expiry_month, expiry_year, cvv }
        Output: token string or None if failed
        """
        url = f"{self.base_url}/api/v3/tokenize"
        headers = self._generate_signature("POST", url)
        
        payload = {
            "customerid": user_id,
            "cardnumber": card_data.get("card_number"),
            "expirymonth": card_data.get("expiry_month"),
            "expiryyear": card_data.get("expiry_year"),
            "cvv": card_data.get("cvv")
        }
        
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                token = result.get("cardtoken")
                logger.info(f"Card tokenized for user {user_id}")
                return token
            else:
                logger.error(f"Tokenization failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Tokenization error: {str(e)}")
            return None
    
    async def auto_debit(self, token: str, amount: float, narration: str) -> Dict:
        """
        Auto-debit tokenized card
        Returns: { success: bool, ref: str, message: str, amount: float }
        """
        if not self.is_configured():
            return self._service_unavailable("auto-debit", amount)

        url = f"{self.base_url}/api/v3/transactions/query"
        headers = self._generate_signature("POST", url)
        
        payload = {
            "cardtoken": token,
            "amount": int(amount * 100),  # Convert to kobo (smallest unit)
            "narration": narration,
            "reference": str(uuid.uuid4())
        }
        
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                success = result.get("responseCode") == "00"
                return {
                    "success": success,
                    "ref": result.get("transactionref"),
                    "message": result.get("responsemessage", ""),
                    "amount": amount
                }
            else:
                logger.error(f"Auto-debit failed: {response.text}")
                return {
                    "success": False,
                    "ref": None,
                    "message": f"HTTP {response.status_code}: {response.text}",
                    "amount": amount
                }
        except Exception as e:
            logger.error(f"Auto-debit error: {str(e)}")
            return {
                "success": False,
                "ref": None,
                "message": str(e),
                "amount": amount
            }
    
    async def transfer_funds(self, recipient_bank_code: str, 
                           account_number: str, amount: float, 
                           narration: str) -> Dict:
        """
        Transfer funds to recipient bank account
        Returns: { success: bool, ref: str, message: str }
        """
        if not self.is_configured():
            return self._service_unavailable("fund transfer", amount)

        url = f"{self.base_url}/api/v3/transfers/api/submitransaction"
        headers = self._generate_signature("POST", url)
        
        payload = {
            "destbankcode": recipient_bank_code,
            "desaccountnumber": account_number,
            "amount": int(amount * 100),  # Convert to kobo
            "narration": narration,
            "transactionreference": str(uuid.uuid4())
        }
        
        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                success = result.get("responseCode") == "00"
                return {
                    "success": success,
                    "ref": result.get("transactionref"),
                    "message": result.get("responsemessage", "")
                }
            else:
                logger.error(f"Transfer failed: {response.text}")
                return {
                    "success": False,
                    "ref": None,
                    "message": f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            logger.error(f"Transfer error: {str(e)}")
            return {
                "success": False,
                "ref": None,
                "message": str(e)
            }

    async def trigger_gsi(self, bvn_last4: str, reason: str) -> Dict:
        """Initiate a GSI recovery request when credentials are available."""
        if not self.is_configured():
            return self._service_unavailable("GSI trigger")

        reference = str(uuid.uuid4())
        logger.warning(
            "GSI trigger requested for BVN ending %s. Real provider-specific implementation still required.",
            bvn_last4,
        )
        return {
            "success": False,
            "ref": reference,
            "message": (
                "GSI trigger reached the Interswitch service layer, but the provider-specific "
                "request contract still needs to be wired for your account."
            ),
        }


# Initialize singleton instance
interswitch = InterswitchService()
