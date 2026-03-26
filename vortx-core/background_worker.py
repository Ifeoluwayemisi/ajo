"""
Background Workers for Vortx
Handles:
- 4-hour retry engine for failed debits
- Loan offer generation (48h before due)
"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import RetryLog, LoanRequest, CircleMember, Circle, Transaction, CardToken, User, PayoutApproval
from models import TransactionStatus, TransactionType
from interswitch_service import interswitch
from vortx_brain import VortxBrain
from config import (
    RETRY_INTERVAL_HOURS, MAX_RETRY_ATTEMPTS, 
    NANO_LOAN_OFFER_HOURS, NANO_LOAN_TERM_DEFAULT,
    NANO_LOAN_INTEREST_RATE, OPENAI_API_KEY
)
import logging
import uuid

logger = logging.getLogger(__name__)


class BackgroundWorker:
    """
    Manages background tasks for Vortx system
    """
    
    def __init__(self):
        self.running = False
        self.retry_interval = RETRY_INTERVAL_HOURS * 3600  # Convert hours to seconds
        self.loan_offer_interval = 3600  # Check hourly for loans
        self.deadman_switch_interval = 3600  # Check every hour for stalled payouts
    
    async def start(self):
        """Start background worker tasks"""
        self.running = True
        logger.info("🌪️ Background worker started - Vortx engines running")
        
        try:
            await asyncio.gather(
                self._retry_loop(),
                self._loan_offer_loop(),
                self._deadman_switch_loop()  # NEW: Deadman's Switch
            )
        except Exception as e:
            logger.error(f"Background worker critical error: {str(e)}")
    
    async def _retry_loop(self):
        """Process failed debits every 4 hours (The 4-Hour Hawk)"""
        while self.running:
            try:
                db = SessionLocal()
                await self._process_retry_logs(db)
                db.close()
            except Exception as e:
                logger.error(f"Retry loop error: {str(e)}")
            
            # Sleep for configured interval
            await asyncio.sleep(self.retry_interval)
    
    async def _process_retry_logs(self, db: Session):
        """
        Retry failed debits
        The Hawk hunts for funds every 4 hours
        """
        pending_retries = db.query(RetryLog).filter(
            RetryLog.status == "pending",
            RetryLog.next_retry_at <= datetime.utcnow()
        ).all()
        
        logger.info(f"🦅 Hawk scanning {len(pending_retries)} pending retries...")
        
        for retry_log in pending_retries:
            try:
                # Get user's card token
                card = db.query(CardToken).filter(
                    CardToken.user_id == retry_log.user_id
                ).first()
                
                if not card or not card.is_active:
                    retry_log.status = "failed_permanently"
                    retry_log.error_message = "No active tokenized card"
                    logger.warning(f"No card for user {retry_log.user_id}")
                    db.add(retry_log)
                    continue
                
                # Attempt debit via Interswitch
                logger.info(f"🔄 Retry attempt {retry_log.attempt_count} for {retry_log.user_id}")
                result = await interswitch.auto_debit(
                    token=card.token,
                    amount=float(retry_log.amount),
                    narration=f"Ajo Retry #{retry_log.attempt_count}"
                )
                
                if result["success"]:
                    # Success! Update retry log and create transaction
                    retry_log.status = "success"
                    retry_log.interswitch_ref = result["ref"]
                    
                    transaction = Transaction(
                        id=str(uuid.uuid4()),
                        user_id=retry_log.user_id,
                        circle_id=retry_log.circle_id,
                        amount=retry_log.amount,
                        type=TransactionType.contribution,
                        status=TransactionStatus.success,
                        interswitch_ref=result["ref"]
                    )
                    db.add(transaction)
                    logger.info(f"✅ Retry successful for {retry_log.user_id}: {result['ref']}")
                
                else:
                    # Try again later
                    retry_log.attempt_count += 1
                    retry_log.last_retry_at = datetime.utcnow()
                    retry_log.next_retry_at = datetime.utcnow() + timedelta(hours=RETRY_INTERVAL_HOURS)
                    retry_log.error_message = result["message"]
                    
                    if retry_log.attempt_count >= MAX_RETRY_ATTEMPTS:
                        retry_log.status = "failed_permanently"
                        logger.error(f"❌ Retry failed after {MAX_RETRY_ATTEMPTS} attempts for {retry_log.user_id}")
                    else:
                        logger.warning(f"⏳ Retry scheduled for next cycle")
                
                db.add(retry_log)
            
            except Exception as e:
                logger.error(f"Error processing retry {retry_log.id}: {str(e)}")
        
        db.commit()
    
    async def _loan_offer_loop(self):
        """Check for members needing loans 48h before due date"""
        while self.running:
            try:
                db = SessionLocal()
                await self._check_and_offer_loans(db)
                db.close()
            except Exception as e:
                logger.error(f"Loan offer loop error: {str(e)}")
            
            await asyncio.sleep(self.loan_offer_interval)
    
    async def _check_and_offer_loans(self, db: Session):
        """
        Analyze member funding gaps and offer nano-loans
        Proactively offers loans 48 hours before contribution due
        """
        brain = VortxBrain(api_key=OPENAI_API_KEY)
        
        # Get all active circles
        circles = db.query(Circle).all()
        
        for circle in circles:
            members = db.query(CircleMember).filter(
                CircleMember.circle_id == circle.id
            ).all()
            
            for member in members:
                user = db.query(User).filter(User.id == member.user_id).first()
                if not user:
                    continue
                
                # Check if funding gap exists
                shortfall = float(circle.contribution_amount) - float(user.wallet_balance or 0)
                
                if shortfall > 0:
                    # Check if already has active loan
                    active_loan = db.query(LoanRequest).filter(
                        LoanRequest.user_id == user.id,
                        LoanRequest.circle_id == circle.id,
                        LoanRequest.status == "active"
                    ).first()
                    
                    if active_loan:
                        continue  # Already has loan
                    
                    # Check if has card token (needed for auto-repayment)
                    card = db.query(CardToken).filter(
                        CardToken.user_id == user.id
                    ).first()
                    
                    if not card or not card.is_active:
                        continue  # Can't auto-repay without card
                    
                    # Use AI to decide if loan should be offered
                    should_offer = brain.should_offer_nano_loan(
                        user_transaction_history=[],  # Would get real history
                        shortfall_amount=shortfall,
                        user_trust_score=user.trust_score
                    )
                    
                    if should_offer:
                        # Create and offer loan
                        amount = shortfall * 1.1  # 10% buffer
                        interest = amount * NANO_LOAN_INTEREST_RATE
                        
                        loan = LoanRequest(
                            id=str(uuid.uuid4()),
                            user_id=user.id,
                            circle_id=circle.id,
                            principal_amount=amount,
                            interest_amount=interest,
                            total_due=amount + interest,
                            due_date=datetime.utcnow() + timedelta(days=NANO_LOAN_TERM_DEFAULT),
                            status="active"
                        )
                        
                        db.add(loan)
                        logger.info(f"💰 Loan offered to {user.email}: ₦{amount:.2f}")
        
        db.commit()


# --- DEADMAN'S SWITCH (Payout Approval Timeout) ---
    async def _deadman_switch_loop(self):
        """Monitor pending payouts for > 24 hours without approval"""
        while self.running:
            try:
                db = SessionLocal()
                await self._check_stalled_payouts(db)
                db.close()
            except Exception as e:
                logger.error(f"Deadman switch loop error: {str(e)}")
            
            # Check every hour
            await asyncio.sleep(self.deadman_switch_interval)
    
    async def _check_stalled_payouts(self, db: Session):
        """
        Check for pending payouts older than 24 hours.
        Alert CEO to manually approve or push payout.
        
        The Deadman's Switch: If current_time - payout.created_at > 24 hours 
        and status == "PENDING", CEO gets High Priority Alert.
        """
        now = datetime.utcnow()
        cutoff_time = now - timedelta(hours=24)
        
        # Find all pending payouts older than 24 hours
        stalled_payouts = db.query(PayoutApproval).filter(
            PayoutApproval.status == "pending",
            PayoutApproval.created_at < cutoff_time
        ).all()
        
        if stalled_payouts:
            logger.warning(f"🚨 DEADMAN'S SWITCH ALERT: {len(stalled_payouts)} payouts stalled > 24 hours")
            
            for payout in stalled_payouts:
                # Calculate how long it's been pending
                hours_pending = (now - payout.created_at).total_seconds() / 3600
                
                # Escalate status to flag for manual review
                payout.status = "escalated"
                payout.escalation_reason = f"Stalled for {hours_pending:.1f} hours. CEO manual intervention required."
                
                # Get user info for the alert
                user = db.query(User).filter(User.id == payout.user_id).first()
                circle = db.query(Circle).filter(Circle.id == payout.circle_id).first()
                
                alert_message = (
                    f"🚨 HIGH PRIORITY ALERT:\n"
                    f"   Payout ID: {payout.id}\n"
                    f"   Member: {user.full_name} ({user.email})\n"
                    f"   Circle: {circle.name if circle else 'Unknown'}\n"
                    f"   Amount: ₦{payout.amount:.2f}\n"
                    f"   Pending Since: {payout.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"   Hours Pending: {hours_pending:.1f} hours\n"
                    f"   ACTION: CEO must manually approve or push payout to complete.\n"
                )
                
                logger.critical(alert_message)
                
                # TODO: In production, send email/SMS to CEO with alert
                # email_service.send_ceo_alert(alert_message)
                
                db.add(payout)
        
        db.commit()


# --- GLOBAL WORKER INSTANCE ---
worker = BackgroundWorker()
