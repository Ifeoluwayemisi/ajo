from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# --- ENUMS ---
class FrequencyEnum(str, Enum):
    weekly = "weekly"
    monthly = "monthly"


class TransactionTypeEnum(str, Enum):
    deposit = "deposit"
    contribution = "contribution"
    payout = "payout"
    withdrawal = "withdrawal"


class CircleStatusEnum(str, Enum):
    pending = "pending"
    active = "active"
    completed = "completed"


# --- USER SCHEMAS ---
class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    user_type: str = Field(default="member")  # "organizer" or "member"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    wallet_balance: float
    trust_score: int
    user_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# --- WALLET SCHEMAS ---
class WalletFundRequest(BaseModel):
    amount: float = Field(..., gt=0)


class WalletResponse(BaseModel):
    user_id: str
    balance: float
    trust_score: int


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    type: str
    status: str
    timestamp: datetime

    class Config:
        from_attributes = True


# --- CIRCLE SCHEMAS ---
class CircleCreate(BaseModel):
    name: str = Field(..., min_length=2)
    description: Optional[str] = None
    contribution_amount: float = Field(..., gt=0)
    frequency: FrequencyEnum
    max_participants: int = Field(..., ge=2, le=20)


class CircleMemberResponse(BaseModel):
    id: str
    user_id: str
    payout_position: Optional[int]
    has_received_payout: bool
    joined_at: datetime
    verification_status: str
    join_method: str
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    commitment_fee_locked: float = 0.00

    class Config:
        from_attributes = True


class CircleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    contribution_amount: float
    frequency: str
    max_participants: int
    total_pot: float
    status: str
    creator_id: str
    short_code: Optional[str]
    members: List[CircleMemberResponse] = []
    created_at: datetime

    class Config:
        from_attributes = True


class JoinCircleRequest(BaseModel):
    circle_id: str


# --- TRUST SCORE SCHEMAS ---
class TrustScoreResponse(BaseModel):
    user_id: str
    trust_score: int
    risk_level: str
    recommended_position: str
    analysis: str


class AIInsightResponse(BaseModel):
    id: str
    user_id: str
    insight_text: str
    risk_level: str
    last_analyzed: datetime

    class Config:
        from_attributes = True

# --- INSURANCE POOL SCHEMAS ---
class InsurancePoolResponse(BaseModel):
    id: str
    circle_id: str
    total_collected: float
    total_paid_out: float
    current_balance: float
    created_at: datetime

    class Config:
        from_attributes = True


# --- LOAN REQUEST SCHEMAS ---
class LoanRequestCreate(BaseModel):
    circle_id: str
    principal_amount: float = Field(..., gt=0)


class LoanRequestResponse(BaseModel):
    id: str
    user_id: str
    circle_id: str
    principal_amount: float
    interest_amount: float
    total_due: float
    status: str
    created_at: datetime
    due_date: datetime
    is_repaid: bool

    class Config:
        from_attributes = True


# --- DEFAULT TRACKER SCHEMAS ---
class DefaultTrackerResponse(BaseModel):
    id: str
    circle_id: str
    user_id: str
    amount_owed: float
    due_date: datetime
    is_recovered: bool
    recovery_attempts: int

    class Config:
        from_attributes = True


# --- RETRY LOG SCHEMAS ---
class RetryLogResponse(BaseModel):
    id: str
    user_id: str
    circle_id: str
    amount: float
    attempt_count: int
    last_retry_at: datetime
    next_retry_at: Optional[datetime]
    status: str
    error_message: Optional[str]

    class Config:
        from_attributes = True


# --- CARD TOKEN SCHEMAS ---
class CardTokenRequest(BaseModel):
    card_number: str = Field(..., min_length=13, max_length=19)
    expiry_month: int = Field(..., ge=1, le=12)
    expiry_year: int = Field(..., ge=2025, le=2035)
    cvv: str = Field(..., min_length=3, max_length=4)


class CardTokenResponse(BaseModel):
    success: bool
    message: str
    token_preview: Optional[str]

    class Config:
        from_attributes = True


# --- VERIFICATION & ADMIN SCHEMAS ---
class RequestJoinCircleResponse(BaseModel):
    success: bool
    member_id: str
    circle_id: str
    message: str


class VerifyMemberRequest(BaseModel):
    approve: bool
    rejection_reason: Optional[str] = None


class VerifyMemberResponse(BaseModel):
    member_id: str
    user_id: str
    circle_id: str
    verification_status: str
    verified_by: str
    verified_at: datetime
    payout_position: Optional[int] = None
    message: str


class AddMemberAdminRequest(BaseModel):
    user_email: str


class AddMemberAdminResponse(BaseModel):
    success: bool
    member_id: str
    user_id: str
    circle_id: str
    message: str


# --- BANK INFO & KYC SCHEMAS ---

class BankAccountVerifyRequest(BaseModel):
    """User provides account number and bank code for payout verification"""
    bank_code: str = Field(..., min_length=3, max_length=3)  # e.g., "044"
    account_number: str = Field(..., min_length=10, max_length=10)  # NUBAN


class BankAccountVerifyResponse(BaseModel):
    """Response from Interswitch name inquiry"""
    verified: bool
    account_name: str
    account_number: str
    bank_code: str
    message: str


class BVNVerificationRequest(BaseModel):
    """User submits BVN for identity verification"""
    bvn: str = Field(..., min_length=11, max_length=11)  # 11-digit BVN


class BVNVerificationResponse(BaseModel):
    """Response after BVN verification"""
    verified: bool
    bvn_last_4: str  # Only show last 4 digits
    kyc_status: str  # pending, verified, rejected
    message: str


class PaymentMethodResponse(BaseModel):
    """User's complete payment/KYC profile"""
    id: str
    user_id: str
    
    # Payout info
    payout_bank_code: Optional[str]
    payout_account_name: Optional[str]
    payout_verified: bool
    
    # KYC Status
    kyc_status: str
    bvn_verified: bool
    credit_check_done: bool
    has_active_bad_loan: bool
    probability_of_default: float
    face_verified: bool
    
    # Position Info (Once assigned)
    assigned_position: Optional[int]
    position_status: str  # pending, assigned, paid
    
    # Card Expiry Warning (Token Expiry Ghost Alert)
    card_token_expires_at: Optional[datetime]
    card_expiry_warning: Optional[str]  # Message if card expires soon
    circles_at_risk: Optional[List[str]]  # Circle IDs where token expires before circle ends
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ==================== CARD TOKENIZATION ====================

class CardTokenizationRequest(BaseModel):
    """Request to tokenize a card for collections"""
    card_number: str  # 16-digit PAN
    expiry_month: str  # 2-digit, e.g., "12"
    expiry_year: str  # 2-digit, e.g., "25"
    cvv: str  # 3-4 digit security code


class CardTokenizationResponse(BaseModel):
    """Token response (NO sensitive card data returned)"""
    card_token: str
    card_type: str  # VISA, MASTERCARD, AMEX
    pan_last_4: str  # Last 4 digits only
    expiry_date: str  # MM/YY
    token_expires_at: datetime
    message: str


# ==================== FACE VERIFICATION ====================

class FaceVerificationRequest(BaseModel):
    """Request to verify face via biometric"""
    bvn: str  # 11-digit BVN (for matching with BVN photo)
    # Note: selfie_image would typically be uploaded as file, not in JSON


class FaceVerificationResponse(BaseModel):
    """Face verification result with manual review support"""
    verified: bool                      # Auto-passed (score >= 70%)
    requires_manual_review: bool        # Score 60-70% requires admin review
    bvn_last_4: str                     # Last 4 digits of BVN
    match_score: float                  # 0.0 - 1.0
    confidence_level: str               # LOW (60-70%), MEDIUM (70-80%), HIGH (80%+)
    message: str


# ==================== PAYOUT APPROVAL (Deadman's Switch) ====================

class PayoutApprovalResponse(BaseModel):
    """Payout approval status and tracking"""
    id: str
    circle_id: str
    user_id: str
    amount: float
    status: str  # pending, approved, paid, rejected, escalated
    created_at: datetime
    approved_at: Optional[datetime]
    paid_at: Optional[datetime]
    approved_by: Optional[str]
    rejection_reason: Optional[str]
    escalation_reason: Optional[str]
    interswitch_ref: Optional[str]
    message: str
    
    class Config:
        from_attributes = True


class KYCStatusResponse(BaseModel):
    """Extended KYC status including card expiry warnings"""
    id: str
    user_id: str
    kyc_status: str
    bvn_verified: bool
    payout_verified: bool
    face_verified: bool
    credit_check_done: bool
    has_active_bad_loan: bool
    probability_of_default: float
    
    # Card Expiry Warning (NEW - Token Expiry Ghost Alert)
    card_token_expires_at: Optional[datetime]
    card_expiry_warning: Optional[str]  # Message if card expires soon
    circles_at_risk: Optional[List[str]]  # Circle IDs where token expires before circle ends
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# ==================== MARKETPLACE SCHEMAS (The Exit Engine) ====================

class MarketSellRequest(BaseModel):
    circle_id: str
    asking_price: float = Field(..., gt=0)


class MarketBuyRequest(BaseModel):
    listing_id: str


class MarketSwapRequest(BaseModel):
    circle_id: str
    target_member_id: str


class PositionSaleResponse(BaseModel):
    id: str
    circle_id: str
    seller_id: str
    payout_position: int
    asking_price: float
    status: str
    created_at: datetime
    sold_at: Optional[datetime]
    
    class Config:
        from_attributes = True