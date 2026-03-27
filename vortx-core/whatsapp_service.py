import logging

import requests
from sqlalchemy.orm import Session

from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_ID
from models import Circle, CircleMember, User

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self):
        self.api_token = WHATSAPP_API_TOKEN
        self.phone_id = WHATSAPP_PHONE_ID
        self.api_url = f"https://graph.facebook.com/v17.0/{self.phone_id}/messages"

    def is_configured(self) -> bool:
        return bool(
            self.api_token
            and self.phone_id
            and self.api_token != "your-meta-whatsapp-token"
            and self.phone_id != "your-whatsapp-phone-id"
        )

    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        return "".join(ch for ch in (phone_number or "") if ch.isdigit())

    def send_message(self, to_phone: str, text: str) -> bool:
        if not self.is_configured():
            logger.warning("WhatsApp service not configured. Message to %s was not sent.", to_phone)
            logger.info("WhatsApp fallback message: %s", text)
            return False

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_phone(to_phone),
            "type": "text",
            "text": {"body": text},
        }

        try:
            response = requests.post(self.api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            logger.info("WhatsApp message sent to %s", to_phone)
            return True
        except requests.RequestException as exc:
            body = exc.response.text if exc.response is not None else str(exc)
            logger.error("Failed to send WhatsApp message to %s: %s", to_phone, body)
            return False

    def process_incoming_message(self, phone_number: str, message_text: str, db: Session) -> bool:
        """Process simple WhatsApp bot commands."""
        clean_phone = self._normalize_phone(phone_number)
        user = db.query(User).filter(User.phone_number == clean_phone).first()

        if not user:
            return self.send_message(
                clean_phone,
                "Welcome to Vortx! We could not find an account linked to this number. Please register in the app and link your phone number first.",
            )

        text_lower = (message_text or "").lower().strip()

        if "balance" in text_lower or "money" in text_lower:
            reply = f"Your Vortx wallet balance is NGN {float(user.wallet_balance or 0):,.2f}. Trust Score: {user.trust_score}%."
        elif "turn" in text_lower or "payout" in text_lower or "when" in text_lower:
            member = db.query(CircleMember).filter(CircleMember.user_id == user.id).first()
            if member and member.payout_position:
                circle = db.query(Circle).filter(Circle.id == member.circle_id).first()
                circle_name = circle.name if circle else "your active circle"
                reply = f"You are currently in payout slot #{member.payout_position} for {circle_name}."
            else:
                reply = "You do not currently have an assigned payout position in an active circle."
        elif "help" in text_lower:
            reply = (
                "Vortx Bot Help\n"
                "- Ask: What is my balance?\n"
                "- Ask: When is my payout turn?\n"
                "- Ask: Help"
            )
        else:
            first_name = (user.full_name or "there").split()[0]
            reply = (
                f"Hi {first_name}. I am the Vortx assistant. "
                "Ask for your balance, payout turn, or type help."
            )

        return self.send_message(clean_phone, reply)


whatsapp_service = WhatsAppService()
