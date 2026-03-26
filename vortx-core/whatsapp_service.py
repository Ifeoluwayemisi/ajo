import os
import requests
import logging
from sqlalchemy.orm import Session
from models import User, CircleMember, Circle
from config import WHATSAPP_API_TOKEN, WHATSAPP_PHONE_ID

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.api_token = WHATSAPP_API_TOKEN
        self.phone_id = WHATSAPP_PHONE_ID
        self.api_url = f"https://graph.facebook.com/v17.0/{self.phone_id}/messages"
        
    def send_message(self, to_phone: str, text: str):
        if not self.api_token or not self.phone_id or self.api_token == "your-meta-whatsapp-token":
            logger.warning(f"💬 [MOCK WHATSAPP] To {to_phone}: {text}")
            return True
            
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {
                "body": text
            }
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            logger.info(f"WhatsApp message sent to {to_phone}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {str(e)}")
            return False

    def process_incoming_message(self, phone_number: str, message_text: str, db: Session):
        """Processes logic for Vortx commands via WhatsApp"""
        # Normalize phone number (strip leading + if any)
        clean_phone = phone_number.replace("+", "")
        
        # In a real scenario, users register their phones in the DB without the +
        user = db.query(User).filter(User.phone_number == clean_phone).first()
        
        if not user:
            # Fallback for hackathon: try matching just by any user for demo if none matches
            # Or enforce strict match
            return self.send_message(
                phone_number, 
                "Welcome to Vortx! 🚀 I couldn't find an account linked to this number. Please register on the app and link your phone number to use the bot!"
            )
            
        text_lower = message_text.lower().strip()
        
        reply = ""
        if "balance" in text_lower or "money" in text_lower:
            reply = f"💰 Your Vortx wallet balance is ₦{user.wallet_balance:,.2f}.\nTrust Score: {user.trust_score}%"
            
        elif "turn" in text_lower or "payout" in text_lower or "when" in text_lower:
            member = db.query(CircleMember).filter(CircleMember.user_id == user.id).first()
            if member and member.payout_position:
                circle = db.query(Circle).filter(Circle.id == member.circle_id).first()
                reply = f"📅 You are positioned at slot #{member.payout_position} for the circle '{circle.name}'."
            else:
                reply = "⚠️ You are not currently assigned a payout position in any active circles."
                
        elif "help" in text_lower:
            reply = (
                "🤖 *Vortx Bot Help*\n"
                "Try asking me:\n"
                "- 'What is my balance?'\n"
                "- 'When is my payout turn?'\n"
                "- 'Help'\n"
            )
        else:
            # Fallback
            reply = f"Hi {user.full_name.split()[0]}! I am the Vortx AI assistant. Please ask for your *balance*, *payout turn*, or *help*."
            
        return self.send_message(phone_number, reply)

whatsapp_service = WhatsAppService()
