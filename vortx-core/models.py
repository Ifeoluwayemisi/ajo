from sqlalchemy import Column, String, Integer, ForeignKey, Boolean, DateTime, Enum, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime
from decimal import Decimal
import uuid
from enum import Enum as PyEnum

Base = declarative_base()

# --- ENUMS --- 
class Frequency(PyEnum):
    weekly = "weekly"
    monthly = "monthly"

class CircleStatus(PyEnum):
    pending = "pending"
    active = "active"
    completed = "completed"

class TransactionType(PyEnum):
    deposit = "deposit"
    contribution = "contribution"
    payout = "payout"
    withdrawal = "withdrawal"

class TransactionStatus(PyEnum):
    success = "success"
    failed = "failed"
    pending = "pending"

class RiskLevel(PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


# --- TABLES ---
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=False)
    wallet_balance = Column(Numeric(18, 2), default=0.00)
    trust_score = Column(Integer, default=50)
    interswitch_customer_id = Column(String, nullable=True)
    user_type = Column(String, default="member")  # "organizer" or "member"
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    circle_memberships = relationship("CircleMember", foreign_keys="CircleMember.user_id", back_populates="user")


class Circle(Base):
    __tablename__ = "circles"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(String)
    contribution_amount = Column(Numeric(18,2), nullable=False)
    frequency = Column(Enum(Frequency), nullable=False)
    max_participants = Column(Integer, nullable=False)
    total_pot = Column(Numeric(18,2), default=0.00)
    status = Column(Enum(CircleStatus), default=CircleStatus.pending)
    creator_id = Column(String, ForeignKey("users.id"))
    short_code = Column(String(7), unique=True, index=True, nullable=True) # VX-XXXX
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Circle Timeline (for token expiry checks)
    cycle_duration_months = Column(Integer, default=10)  # Typical: 10 months
    expected_end_date = Column(DateTime, nullable=True)  # Calculated: created_at + (cycle_duration_months * 30 days)
    
    # Relationships
    members = relationship("CircleMember", back_populates="circle")


class CircleMember(Base):
    __tablename__ = "circle_members"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"))
    user_id = Column(String, ForeignKey("users.id"))
    payout_position = Column(Integer, nullable=True)
    has_received_payout = Column(Boolean, default=False)
    commitment_fee_locked = Column(Numeric(18,2), default=0.00)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Verification fields (NEW)
    verification_status = Column(String, default="pending")  # pending, verified, rejected
    join_method = Column(String, default="self_requested")  # self_requested or admin_added
    verified_by = Column(String, ForeignKey("users.id"), nullable=True)  # Admin who verified
    verified_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String, nullable=True)  # If rejected
    
    # Relationships
    circle = relationship("Circle", back_populates="members")
    user = relationship("User", foreign_keys="CircleMember.user_id", back_populates="circle_memberships")



class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    circle_id = Column(String, ForeignKey("circles.id"), nullable=True)
    amount = Column(Numeric(18,2), nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending)
    interswitch_ref = Column(String, unique=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Deadman's Switch: Track payout request timing for 24h escalation
    payout_requested_at = Column(DateTime, nullable=True)  # When payout was requested
    payout_approved_at = Column(DateTime, nullable=True)   # When payout was approved/paid
    escalated_to_ceo = Column(Boolean, default=False)      # TRUE if escalated after 24h


class AIInsight(Base):
    __tablename__ = "ai_insights"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    insight_text = Column(String)
    risk_level = Column(Enum(RiskLevel), nullable=False)
    last_analyzed = Column(DateTime, default=datetime.datetime.utcnow)


# --- INSURANCE POOL (The Shield) ---
class InsurancePool(Base):
    __tablename__ = "insurance_pools"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"), unique=True)
    total_collected = Column(Numeric(18, 2), default=0.00)  # Safety fees collected
    total_paid_out = Column(Numeric(18, 2), default=0.00)   # Paid to cover defaults
    current_balance = Column(Numeric(18, 2), default=0.00)  # total_collected - total_paid_out
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    circle = relationship("Circle", backref="insurance_pool")


# --- DEFAULT TRACKER (Recovery) ---
class DefaultTracker(Base):
    __tablename__ = "default_trackers"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"))
    user_id = Column(String, ForeignKey("users.id"))
    amount_owed = Column(Numeric(18, 2), nullable=False)
    due_date = Column(DateTime, nullable=False)
    is_recovered = Column(Boolean, default=False)
    recovery_attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    circle = relationship("Circle", backref="defaults")
    user = relationship("User", backref="defaults")


# --- RETRY LOG (4-Hour Hawk) ---
class RetryLog(Base):
    __tablename__ = "retry_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    circle_id = Column(String, ForeignKey("circles.id"))
    amount = Column(Numeric(18, 2), nullable=False)
    attempt_count = Column(Integer, default=1)
    last_retry_at = Column(DateTime, default=datetime.datetime.utcnow)
    next_retry_at = Column(DateTime)
    status = Column(String, default="pending")  # pending, success, failed_permanently
    error_message = Column(String, nullable=True)
    interswitch_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    circle = relationship("Circle", backref="retries")
    user = relationship("User", backref="retries")


# --- LOAN REQUEST (AI Nano-Loans) ---
class LoanRequest(Base):
    __tablename__ = "loan_requests"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    circle_id = Column(String, ForeignKey("circles.id"))
    principal_amount = Column(Numeric(18, 2), nullable=False)
    interest_amount = Column(Numeric(18, 2), nullable=False)
    total_due = Column(Numeric(18, 2), nullable=False)
    is_repaid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    due_date = Column(DateTime, nullable=False)
    repayment_date = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active, repaid, overdue, cancelled
    
    # Relationships
    circle = relationship("Circle", backref="loans")
    user = relationship("User", backref="loans")


# --- CARD TOKEN (Tokenized Card for Auto-Debit) ---
class CardToken(Base):
    __tablename__ = "card_tokens"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), unique=True)
    token = Column(String, nullable=False, unique=True)  # Interswitch token
    card_last_4 = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", backref="card_token")


# --- IDEMPOTENCY KEY (Prevent Double-Payouts) ---
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"))
    endpoint = Column(String, nullable=False)  # e.g., "/api/transfer"
    response_data = Column(String)  # JSON
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", backref="idempotency_keys")


# --- CIRCLE ADMIN (Role Management) ---
class CircleAdmin(Base):
    __tablename__ = "circle_admins"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"))
    user_id = Column(String, ForeignKey("users.id"))
    role = Column(String, default="admin")  # admin, moderator, ceo
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    assigned_by = Column(String, ForeignKey("users.id"), nullable=True)  # Who assigned
    
    # Relationships
    circle = relationship("Circle", backref="admins")
    user = relationship("User", foreign_keys="CircleAdmin.user_id", backref="admin_circles")


# --- PAYMENT METHOD (Bank Info for Payouts & Collection) ---
class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Payout Info (Where user receives funds)
    payout_bank_code = Column(String, nullable=True)  # e.g., "044" for Access Bank
    payout_account_number = Column(String, nullable=True)  # 10-digit NUBAN
    payout_account_name = Column(String, nullable=True)  # Verified from bank
    payout_verified = Column(Boolean, default=False)
    payout_verified_at = Column(DateTime, nullable=True)
    
    # Collection Info (Where money is pulled from - Card tokens only)
    # NO Card Number, Expiry, CVV stored! Use card_token relationship instead
    
    # Identity Verification (KYC Ghost)
    bvn_encrypted = Column(String, nullable=True)  # Encrypted with AES-256
    bvn_verified = Column(Boolean, default=False)
    bvn_verified_at = Column(DateTime, nullable=True)
    
    # Risk Assessment
    kyc_status = Column(String, default="pending")  # pending, verified, rejected, flagged
    credit_check_done = Column(Boolean, default=False)
    has_active_bad_loan = Column(Boolean, default=False)  # From Interswitch Credit API
    probability_of_default = Column(Numeric(5, 2), default=0.0)  # 0.00 - 100.00
    
    # Face Verification (Biometric KYC)
    face_verified = Column(Boolean, default=False)
    face_verified_at = Column(DateTime, nullable=True)
    face_requires_manual_review = Column(Boolean, default=False)  # Score 60-70%
    face_match_score = Column(Numeric(5, 2), nullable=True)  # 0.00-99.99%
    
    # Metadata
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="payment_method")


# --- PAYOUT APPROVAL (Deadman's Switch) ---
class PayoutApproval(Base):
    __tablename__ = "payout_approvals"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)  # User receiving payout
    amount = Column(Numeric(18, 2), nullable=False)
    status = Column(String, default="pending")  # pending, approved, paid, rejected, escalated
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # CRITICAL for deadman's switch
    approved_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    approved_by = Column(String, ForeignKey("users.id"), nullable=True)  # Admin/CEO who approved
    rejection_reason = Column(String, nullable=True)
    escalation_reason = Column(String, nullable=True)  # If flagged for manual review
    payment_method_id = Column(String, ForeignKey("payment_methods.id"), nullable=True)  # Where payout goes
    interswitch_ref = Column(String, nullable=True)  # Payout transaction reference
    
    # Relationships
    circle = relationship("Circle", backref="payout_approvals")
    user = relationship("User", foreign_keys="PayoutApproval.user_id", backref="payout_approvals")
    approved_by_user = relationship("User", foreign_keys="PayoutApproval.approved_by", backref="approved_payouts")
    payment_method = relationship("PaymentMethod", backref="payout_approvals")


# --- POSITION MARKET (The Exit Engine) ---
class PositionSaleMarket(Base):
    __tablename__ = "position_sales"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    circle_id = Column(String, ForeignKey("circles.id"), nullable=False)
    seller_id = Column(String, ForeignKey("users.id"), nullable=False)
    circle_member_id = Column(String, ForeignKey("circle_members.id"), nullable=False)
    payout_position = Column(Integer, nullable=False)
    asking_price = Column(Numeric(18, 2), nullable=False)
    status = Column(String, default="active")  # active, sold, cancelled
    buyer_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)
    
    # Relationships
    circle = relationship("Circle", backref="market_listings")
    seller = relationship("User", foreign_keys="PositionSaleMarket.seller_id", backref="sold_positions")
    buyer = relationship("User", foreign_keys="PositionSaleMarket.buyer_id", backref="bought_positions")
    circle_member = relationship("CircleMember")