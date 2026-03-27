import logging
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session, joinedload
from urllib3.util.retry import Retry

from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_ID
from models import CircleMember, User

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self):
        self.api_token = WHATSAPP_API_TOKEN
        self.phone_id = WHATSAPP_PHONE_ID
        self.api_url = f"https://graph.facebook.com/v17.0/{self.phone_id}/messages"

        # WhatsApp sends use POST, so retries must explicitly allow POST.
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset({"POST"}),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def is_configured(self) -> bool:
        return all(
            [
                self.api_token,
                self.phone_id,
                self.api_token != "your-meta-whatsapp-token",
                self.phone_id != "your-whatsapp-phone-id",
            ]
        )

    @staticmethod
    def _normalize_phone(phone_number: Optional[str]) -> str:
        """Normalize a phone number to Nigerian E.164 digits without a leading plus."""
        if not phone_number:
            return ""

        digits = "".join(filter(str.isdigit, phone_number))
        if not digits:
            return ""

        if digits.startswith("00"):
            digits = digits[2:]

        if digits.startswith("0"):
            digits = "234" + digits[1:]
        elif not digits.startswith("234"):
            digits = "234" + digits

        return digits

    @staticmethod
    def _find_user_by_phone(db: Session, clean_phone: str) -> Optional[User]:
        """Match common local and E.164 variants for legacy stored numbers."""
        if not clean_phone:
            return None

        local_phone = clean_phone
        if clean_phone.startswith("234") and len(clean_phone) > 3:
            local_phone = "0" + clean_phone[3:]

        candidate_numbers = {
            clean_phone,
            f"+{clean_phone}",
            local_phone,
        }

        return db.query(User).filter(User.phone_number.in_(candidate_numbers)).first()

    def send_message(self, to_phone: str, text: str) -> bool:
        clean_phone = self._normalize_phone(to_phone)
        message_body = (text or "").strip()

        if not clean_phone:
            logger.error("Invalid phone number: %s", to_phone)
            return False

        if not message_body:
            logger.error("Refusing to send empty WhatsApp message", extra={"phone": clean_phone})
            return False

        if not self.is_configured():
            logger.warning("WhatsApp not configured. Skipping send.")
            logger.info("Fallback message to %s: %s", clean_phone, message_body)
            return False

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "text",
            "text": {"body": message_body},
        }

        try:
            response = self.session.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Message sent", extra={"phone": clean_phone})
            return True
        except requests.Timeout:
            logger.error("Timeout sending message", extra={"phone": clean_phone})
        except requests.HTTPError as exc:
            logger.error(
                "HTTP error",
                extra={
                    "phone": clean_phone,
                    "response": exc.response.text if exc.response else None,
                },
            )
        except requests.RequestException as exc:
            logger.error(
                "Request failed",
                extra={"phone": clean_phone, "error": str(exc)},
            )

        return False

    def process_incoming_message(
        self,
        phone_number: str,
        message_text: Optional[str],
        db: Session,
    ) -> bool:
        """Process basic WhatsApp bot commands."""
        clean_phone = self._normalize_phone(phone_number)
        if not clean_phone:
            logger.warning("Invalid incoming phone: %s", phone_number)
            return False

        user = self._find_user_by_phone(db, clean_phone)
        if not user:
            return self.send_message(
                clean_phone,
                "Welcome to Vortx! No account is linked to this number. "
                "Please register in the app and link your phone number.",
            )

        text = (message_text or "").strip().lower()
        if "balance" in text:
            return self._handle_balance(user, clean_phone)

        if any(word in text for word in ["payout", "turn"]):
            return self._handle_payout(user, clean_phone, db)

        if "help" in text:
            return self._handle_help(clean_phone)

        return self._handle_default(user, clean_phone)

    def _handle_balance(self, user: User, phone: str) -> bool:
        balance = float(getattr(user, "wallet_balance", 0) or 0)
        trust_score = getattr(user, "trust_score", 0)

        reply = (
            f"Your Vortx wallet balance is NGN {balance:,.2f}.\n"
            f"Trust Score: {trust_score}%."
        )
        return self.send_message(phone, reply)

    def _handle_payout(self, user: User, phone: str, db: Session) -> bool:
        member = (
            db.query(CircleMember)
            .options(joinedload(CircleMember.circle))
            .filter(CircleMember.user_id == user.id)
            .first()
        )

        payout_pos = getattr(member, "payout_position", None) if member else None
        if member and payout_pos:
            circle_name = member.circle.name if member.circle else "your circle"
            reply = f"You are in payout slot #{payout_pos} for {circle_name}."
        else:
            reply = "You do not have a payout position in any active circle."

        return self.send_message(phone, reply)

    def _handle_help(self, phone: str) -> bool:
        reply = (
            "Vortx Bot Help:\n"
            "- 'balance' -> Check wallet balance\n"
            "- 'payout' -> Check payout turn\n"
            "- 'help' -> Show this message"
        )
        return self.send_message(phone, reply)

    def _handle_default(self, user: User, phone: str) -> bool:
        first_name = (user.full_name or "there").split()[0]
        reply = (
            f"Hi {first_name}! I'm the Vortx assistant.\n"
            "You can ask about your balance or payout turn.\n"
            "Type 'help' to see options."
        )
        return self.send_message(phone, reply)


whatsapp_service = WhatsAppService()
