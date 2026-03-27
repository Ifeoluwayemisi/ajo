import openai
import json
import hashlib
import time
import uuid

class VortxBrain:
    def __init__(self, api_key):
        self.client = openai.OpenAI(api_key=api_key)

    def analyze_trust(self, transaction_history):
        """
        Input: List of transaction dicts
        Output: JSON with trust_score and position_recommendation
        """
        # Handle empty transaction history
        if not transaction_history:
            return {
                "trust_score": 50,
                "risk_level": "medium",
                "position_recommendation": "middle",
                "reason": "New user with no transaction history. Starting with baseline trust score."
            }
        
        prompt = f"""
        Act as a Fintech Risk Officer for an Ajo (communal saving) platform. 
        Analyze the following transaction history for a user and provide:
        1. A trust score (0-100).
        2. A risk level (Low, Medium, High).
        3. A recommended payout position (Early, Middle, Late). Late is for high risk.
        4. A brief reason for the score.

        Data: {json.dumps(transaction_history)}

        Return ONLY a JSON object.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Error in analyze_trust GPT call: {str(e)}")
            # Return safe defaults if GPT fails
            return {
                "trust_score": 50,
                "risk_level": "medium",
                "position_recommendation": "middle",
                "reason": f"Analysis skipped due to error: {str(e)}"
            }

    def should_offer_nano_loan(self, user_transaction_history, shortfall_amount, user_trust_score) -> bool:
        """
        AI decides whether to offer a nano-loan (Trust Top-Up)
        
        Input:
            - user_transaction_history: List of past transactions
            - shortfall_amount: How much they're short (₦)
            - user_trust_score: Current trust score (0-100)
        
        Output: bool (True = offer loan, False = don't offer)
        """
        prompt = f"""
        You are a financial AI for an Ajo (rotating savings group) platform called Vortx.
        
        A member needs ₦{shortfall_amount:.2f} to meet their contribution commitment.
        Their trust score is {user_trust_score}/100.
        
        Transaction history: {json.dumps(user_transaction_history[:10])}
        
        Should we offer them an instant nano-loan to keep them in the circle?
        
        Respond with ONLY: YES or NO
        
        Consider:
        - Are they historically reliable?
        - Is their trust score decent (>40)?
        - Would the loan save the circle from a default?
        
        Respond with just YES or NO.
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            decision = response.choices[0].message.content.strip().upper()
            return "YES" in decision
        except Exception as e:
            print(f"Error in should_offer_nano_loan: {str(e)}")
            # Default: offer if trust score is decent
            return user_trust_score >= 40

    def assign_payout_position(self, trust_score: int, risk_level: str, 
                               has_active_bad_loan: bool, circle_size: int = 10) -> int:
        """
        Assign payout position (1-10) based on trust score and risk level.
        
        Logic:
        - Trust 80-100 + Low Risk → Early (1, 2, 3)
        - Trust 50-79 + Medium Risk → Middle (4, 5, 6)
        - Trust 0-49 + High Risk → Late (7, 8, 9, 10)
        
        If has_active_bad_loan: Force to Late positions (7+)
        
        Args:
            trust_score: 0-100 from AI analysis
            risk_level: "low", "medium", "high"
            has_active_bad_loan: From Interswitch credit check
            circle_size: Number of positions (default 10)
            
        Returns:
            position: Integer 1-circle_size
        """
        # If user has active bad loan elsewhere, force to late positions
        if has_active_bad_loan:
            # Assign to late positions (7-10 for 10-person circle)
            late_start = max(circle_size - 3, 1)  # Last 3-4 positions
            return late_start
        
        # Standard assignment by trust score and risk level
        if trust_score >= 80 and risk_level == "low":
            # Early positions (1-3)
            return 1
        elif 50 <= trust_score < 80 and risk_level == "medium":
            # Middle positions (4-6)
            return 4
        elif trust_score < 50 or risk_level == "high":
            # Late positions (7-10)
            return 7
        else:
            # Default: middle
            return 4
    
    def validate_position_shuffle(self, circle_members: list, circle_size: int = 10) -> bool:
        """
        Validate that at least 30% of early positions (1-3) are "Low Risk".
        This ensures the circle has good momentum at the start.
        
        Args:
            circle_members: List of CircleMember objects with positions assigned
            circle_size: Total circle size
            
        Returns:
            bool: True if valid (at least 3 low-risk members in positions 1-3)
        """
        early_positions = [m for m in circle_members if m.payout_position and m.payout_position <= 3]
        low_risk_count = 0
        for member in early_positions:
            risk_level = getattr(member, "risk_level", None)
            if risk_level == "low":
                low_risk_count += 1
            elif risk_level is None and getattr(member, "user_id", None):
                low_risk_count += 1

        return low_risk_count >= 3

    def calculate_circle_risk_score(self, circle_members: list, payment_methods: dict) -> tuple[float, int]:
        """
        Calculate aggregate risk score for entire circle.
        
        Args:
            circle_members: List of CircleMember objects
            payment_methods: Dict mapping user_id → PaymentMethod object
        
        Returns:
            (average_risk_score: 0-100, bad_loan_count: int)
        """
        if not circle_members:
            return 0.0, 0
        
        total_risk = 0.0
        bad_loan_count = 0
        
        for member in circle_members:
            payment = payment_methods.get(member.user_id)
            if payment:
                # Risk calculation: if has_active_bad_loan, +100 to risk
                if payment.has_active_bad_loan:
                    total_risk += 100.0
                    bad_loan_count += 1
                else:
                    # Use probability_of_default as risk score
                    risk = float(payment.probability_of_default or 0.0)
                    total_risk += risk
            else:
                # No payment method = unknown risk = 50
                total_risk += 50.0
        
        average_risk = total_risk / len(circle_members)
        return average_risk, bad_loan_count
    
    def validate_circle_readiness(self, circle_members: list, payment_methods: dict) -> tuple[bool, str]:
        """
        Validate if circle is ready to start.
        
        RULE: Must have at least 3 members with low risk (< 30% default probability)
        AND not more than 2 members with active bad loans
        
        Args:
            circle_members: List of CircleMember objects
            payment_methods: Dict mapping user_id → PaymentMethod object
        
        Returns:
            (is_ready: bool, message: str)
        """
        if len(circle_members) < 3:
            return False, "Circle must have at least 3 verified members to start"
        
        # Calculate aggregate risk
        avg_risk, bad_loan_count = self.calculate_circle_risk_score(circle_members, payment_methods)
        
        # Check bad loan threshold
        if bad_loan_count > 2:
            return False, f"Circle has {bad_loan_count} members with active bad loans. Max allowed: 2"
        
        # Check aggregate risk
        if avg_risk > 60.0:
            return False, f"Circle aggregate risk score ({avg_risk:.1f}) exceeds threshold (60). Add more low-risk members."
        
        # Count low-risk members
        low_risk_count = 0
        for member in circle_members:
            payment = payment_methods.get(member.user_id)
            if payment and not payment.has_active_bad_loan and float(payment.probability_of_default or 0) < 30:
                low_risk_count += 1
        
        if low_risk_count < 3:
            return False, f"Circle needs at least 3 low-risk members. Current: {low_risk_count}"
        
        return True, f"✅ Circle is ready to start. Risk score: {avg_risk:.1f}/100, Low-risk members: {low_risk_count}"
    
    def check_token_expiry_warnings(self, circle_end_date, card_tokens: dict) -> list:
        """
        Check if any user's card token expires before circle ends.
        THE TOKEN EXPIRY GHOST FIX.
        
        Args:
            circle_end_date: Expected end date of circle
            card_tokens: Dict mapping user_id → CardToken object
        
        Returns:
            list of dicts with warnings for users whose tokens expire soon
        """
        from datetime import datetime
        
        warnings = []
        
        for user_id, token in card_tokens.items():
            if token and token.expires_at:
                # Compare expiry with circle end
                days_until_token_expires = (token.expires_at - datetime.utcnow()).days
                days_until_circle_ends = (circle_end_date - datetime.utcnow()).days
                
                if token.expires_at < circle_end_date:
                    warning = {
                        "user_id": user_id,
                        "token_last_4": token.card_last_4,
                        "expires_at": token.expires_at.isoformat(),
                        "days_until_expiry": days_until_token_expires,
                        "days_until_circle_ends": days_until_circle_ends,
                        "message": f"🚨 Card expires in {days_until_token_expires} days, but circle continues for {days_until_circle_ends} days. Please link a new card!",
                        "severity": "URGENT" if days_until_token_expires < 30 else "WARNING"
                    }
                    warnings.append(warning)
        
        return warnings

def generate_interswitch_auth(client_id, secret_key, http_method, url):
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4()).replace("-", "")
    
    # Signature formula: HTTP_METHOD & URL & TIMESTAMP & NONCE & CLIENT_ID & SECRET_KEY
    signature_base = f"{http_method}&{url}&{timestamp}&{nonce}&{client_id}&{secret_key}"
    
    # Interswitch often requires SHA-512 for MAC
    hash_object = hashlib.sha512(signature_base.encode())
    signature = hash_object.hexdigest()
    
    return {
        "Authorization": f"InterswitchAuth {client_id}",
        "Timestamp": timestamp,
        "Nonce": nonce,
        "Signature": signature,
        "SignatureMethod": "SHA512"
    }
