from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, List
from passlib.context import CryptContext
from jose import JWTError, jwt
import json
import asyncio
import logging
import base64

from database import SessionLocal, init_db
from models import (
    User, Circle, CircleMember, CircleAdmin, Transaction, AIInsight,
    InsurancePool, DefaultTracker, RetryLog, LoanRequest, CardToken, IdempotencyKey,
    PaymentMethod, PayoutApproval, PositionSaleMarket
)
from models import Frequency, TransactionType, TransactionStatus, RiskLevel, CircleStatus
from schemas import (
    UserRegister, UserLogin, UserResponse, TokenResponse,
    CircleCreate, CircleResponse, CircleMemberResponse, JoinCircleRequest,
    WalletFundRequest, WalletResponse, TransactionResponse,
    TrustScoreResponse, AIInsightResponse,
    InsurancePoolResponse, LoanRequestResponse, DefaultTrackerResponse,
    RetryLogResponse, CardTokenRequest, CardTokenResponse, LoanRequestCreate,
    RequestJoinCircleResponse, VerifyMemberRequest, VerifyMemberResponse,
    AddMemberAdminRequest, AddMemberAdminResponse,
    BankAccountVerifyRequest, BankAccountVerifyResponse,
    BVNVerificationRequest, BVNVerificationResponse,
    KYCStatusResponse,
    CardTokenizationRequest, CardTokenizationResponse,
    FaceVerificationRequest, FaceVerificationResponse,
    PayoutApprovalResponse,
    MarketSellRequest, MarketBuyRequest, MarketSwapRequest, PositionSaleResponse
)
from config import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, OPENAI_API_KEY,
    INSURANCE_SAFETY_FEE, NANO_LOAN_INTEREST_RATE, WHATSAPP_VERIFY_TOKEN
)
from vortx_brain import VortxBrain
from bank_verification import bank_verification_service
from card_tokenization import card_tokenization_service
from encryption import encryption_service
from interswitch_service import interswitch
from background_worker import worker
from whatsapp_service import whatsapp_service
from decimal import Decimal
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Initialize FastAPI ---
app = FastAPI(title="Vortx API", version="0.1.0")


@app.get("/")
def root():
    """Simple health/info route for the base URL."""
    return {
        "message": "Welcome to the Vortx API",
        "docs": "/docs",
        "status": "running",
    }

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Password Hashing ---
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# --- Initialize DB ---
init_db()

# --- Initialize Vortx Brain ---
brain = VortxBrain(api_key=OPENAI_API_KEY)


# --- STARTUP & SHUTDOWN EVENTS ---
@app.on_event("startup")
async def startup_event():
    """Start background worker on app startup"""
    logger.info("Starting Vortx background workers...")
    asyncio.create_task(worker.start())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background worker on app shutdown"""
    logger.info("Stopping Vortx background workers...")
    worker.running = False


# --- Dependencies ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def check_idempotency(request_id: str, endpoint: str, user_id: str, db: Session) -> tuple[bool, dict]:
    """
    Check if request has already been processed (prevent duplicate payouts)
    
    Returns:
        (is_duplicate: bool, previous_response: dict)
    """
    existing = db.query(IdempotencyKey).filter(
        IdempotencyKey.request_id == request_id,
        IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.user_id == user_id
    ).first()
    
    if existing and existing.response_data:
        import json
        return True, json.loads(existing.response_data)
    
    return False, {}


def store_idempotency_response(request_id: str, endpoint: str, user_id: str, response_data: dict, db: Session):
    """
    Store idempotency key for successful request
    """
    import json
    
    idempotency_key = IdempotencyKey(
        id=str(uuid.uuid4()),
        request_id=request_id,
        endpoint=endpoint,
        user_id=user_id,
        response_data=json.dumps(response_data),
        expires_at=datetime.utcnow() + timedelta(hours=24)  # Valid for 24 hours
    )
    
    db.add(idempotency_key)
    db.commit()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(credentials: HTTPBearer = Depends(HTTPBearer()), db: Session = Depends(get_db)) -> User:
    """Extract user from JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# --- AUTH ENDPOINTS ---
@app.post("/api/auth/register", response_model=TokenResponse)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if email exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        id=str(uuid.uuid4()),
        full_name=user_data.full_name,
        email=user_data.email,
        user_type=user_data.user_type if user_data.user_type in ["organizer", "member"] else "member",
        wallet_balance=0.00,
        trust_score=50,  # Default trust score
    )
    # Store password hash
    new_user.password_hash = hash_password(user_data.password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Create token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": new_user.id},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(new_user)
    }


@app.post("/api/auth/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login user"""
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.from_orm(user)
    }


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(
    user: User = Depends(get_current_user)
):
    """Get current user"""
    return UserResponse.from_orm(user)


# --- WALLET ENDPOINTS ---
@app.get("/api/wallet", response_model=WalletResponse)
def get_wallet(
    user: User = Depends(get_current_user)
):
    """Get wallet balance"""
    return {
        "user_id": user.id,
        "balance": float(user.wallet_balance),
        "trust_score": user.trust_score
    }


@app.post("/api/wallet/fund/initialize")
def initialize_payment(
    request: WalletFundRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initialize Interswitch payment"""
    # Create pending transaction
    transaction = Transaction(
        id=str(uuid.uuid4()),
        user_id=user.id,
        amount=request.amount,
        type=TransactionType.deposit,
        status=TransactionStatus.pending
    )
    db.add(transaction)
    db.commit()
    
    provider_status = "unconfigured" if not interswitch.is_configured() else "pending_handoff"
    provider_state = (
        "Interswitch payment initialization is not configured for the current environment."
        if provider_status == "unconfigured"
        else "Transaction recorded locally; provider handoff is pending."
    )
    return {
        "status": "pending",
        "provider_status": provider_status,
        "transaction_id": transaction.id,
        "amount": float(request.amount),
        "message": provider_state
    }


@app.get("/api/transactions", response_model=List[TransactionResponse])
def get_transactions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user transaction history"""
    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    return [TransactionResponse.from_orm(t) for t in transactions]


# --- CIRCLE ENDPOINTS ---
@app.post("/api/circles/create", response_model=CircleResponse)
def create_circle(
    circle_data: CircleCreate,
    creator: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new circle"""
    
    new_circle = Circle(
        id=str(uuid.uuid4()),
        name=circle_data.name,
        description=circle_data.description,
        contribution_amount=circle_data.contribution_amount,
        frequency=Frequency[circle_data.frequency],
        max_participants=circle_data.max_participants,
        creator_id=creator.id,
        short_code=f"VX-{uuid.uuid4().hex[:4].upper()}",
        status=CircleStatus.pending
    )
    
    db.add(new_circle)
    db.commit()
    db.refresh(new_circle)
    
    # Add creator as first member (verified + admin)
    member = CircleMember(
        id=str(uuid.uuid4()),
        circle_id=new_circle.id,
        user_id=creator.id,
        payout_position=1,
        verification_status="verified",
        join_method="creator",
        verified_by=creator.id,
        verified_at=datetime.utcnow()
    )
    db.add(member)
    
    # Auto-assign creator as admin
    admin = CircleAdmin(
        id=str(uuid.uuid4()),
        circle_id=new_circle.id,
        user_id=creator.id,
        role="ceo",  # Circle organizer is CEO
        assigned_by=None  # Self-assigned
    )
    db.add(admin)
    db.commit()
    
    return CircleResponse.from_orm(new_circle)


@app.post("/api/circles/{circle_id}/join", response_model=CircleResponse)
def join_circle(
    circle_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Join an existing circle"""
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Check if already member
    existing_member = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id,
        CircleMember.user_id == user.id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="Already a member")
    
    # Check max participants
    member_count = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id
    ).count()
    
    if member_count >= circle.max_participants:
        raise HTTPException(status_code=400, detail="Circle is full")
    
    # Add as member
    member = CircleMember(
        id=str(uuid.uuid4()),
        circle_id=circle_id,
        user_id=user.id,
        payout_position=member_count + 1
    )
    db.add(member)
    db.commit()
    
    # Run AI trust analysis to reorder positions
    analyze_and_reorder_circle(circle_id, db)
    
    db.refresh(circle)
    return CircleResponse.from_orm(circle)


@app.get("/api/circles/{circle_id}", response_model=CircleResponse)
def get_circle(
    circle_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get circle details"""
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    return CircleResponse.from_orm(circle)


@app.get("/api/circles/code/{short_code}", response_model=CircleResponse)
def get_circle_by_code(
    short_code: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get circle details by short code (e.g., VX-8B9M)"""
    circle = db.query(Circle).filter(Circle.short_code == short_code).first()
    
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    return CircleResponse.from_orm(circle)


@app.get("/api/circles", response_model=List[CircleResponse])
def get_circles(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all circles for user"""
    
    # Get circles where user is member
    member_circles = db.query(Circle).join(
        CircleMember
    ).filter(CircleMember.user_id == user.id).all()
    
    return [CircleResponse.from_orm(c) for c in member_circles]


# --- HELPER FUNCTION FOR ADMIN CHECK ---
def check_is_circle_admin(user_id: str, circle_id: str, db: Session):
    """Check if user is an admin of the circle"""
    admin = db.query(CircleAdmin).filter(
        CircleAdmin.user_id == user_id,
        CircleAdmin.circle_id == circle_id
    ).first()
    return admin is not None


def require_admin_user(user: User):
    """Restrict sensitive operational routes to organizer accounts."""
    if user.user_type != "organizer":
        raise HTTPException(status_code=403, detail="Organizer access required")


# --- VERIFICATION & ADMIN ENDPOINTS ---
@app.post("/api/circles/{circle_id}/request-join", response_model=RequestJoinCircleResponse)
def request_join_circle(
    circle_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User requests to join a circle (requires verification after)"""
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Check if already member
    existing_member = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id,
        CircleMember.user_id == user.id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="Already a member of this circle")
    
    # Check max participants
    member_count = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id
    ).count()
    
    if member_count >= circle.max_participants:
        raise HTTPException(status_code=400, detail="Circle is full")
    
    # Create member with pending verification
    member = CircleMember(
        id=str(uuid.uuid4()),
        circle_id=circle_id,
        user_id=user.id,
        verification_status="pending",
        join_method="self_requested",
        payout_position=None  # Will be assigned after verification
    )
    db.add(member)
    db.commit()
    
    return RequestJoinCircleResponse(
        success=True,
        member_id=member.id,
        circle_id=circle_id,
        message="Join request submitted. Awaiting admin approval."
    )


@app.post("/api/circles/{circle_id}/add-member", response_model=AddMemberAdminResponse)
def add_member_admin(
    circle_id: str,
    request_data: AddMemberAdminRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin adds a member to circle directly"""
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Check if user is circle admin
    if not check_is_circle_admin(user.id, circle_id, db):
        raise HTTPException(status_code=403, detail="Not a circle admin")
    
    # Find user by email
    target_user = db.query(User).filter(User.email == request_data.user_email).first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if already member
    existing_member = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id,
        CircleMember.user_id == target_user.id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="User is already a member")
    
    # Check max participants
    member_count = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id
    ).count()
    
    if member_count >= circle.max_participants:
        raise HTTPException(status_code=400, detail="Circle is full")
    
    # Create member added by admin (still needs verification)
    member = CircleMember(
        id=str(uuid.uuid4()),
        circle_id=circle_id,
        user_id=target_user.id,
        verification_status="pending",
        join_method="admin_added",
        payout_position=None
    )
    db.add(member)
    db.commit()
    
    return AddMemberAdminResponse(
        success=True,
        member_id=member.id,
        user_id=target_user.id,
        circle_id=circle_id,
        message=f"Member {target_user.email} added. Verification required."
    )


@app.post("/api/circles/{circle_id}/verify-member/{member_id}", response_model=VerifyMemberResponse)
def verify_member(
    circle_id: str,
    member_id: str,
    request_data: VerifyMemberRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin verifies/approves a member request with AI-based position assignment"""
    # Check if user is circle admin
    if not check_is_circle_admin(user.id, circle_id, db):
        raise HTTPException(status_code=403, detail="Not a circle admin")
    
    member = db.query(CircleMember).filter(
        CircleMember.id == member_id,
        CircleMember.circle_id == circle_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    payout_position = None
    
    if request_data.approve:
        # Approve: assign AI-based position and mark verified
        member_user = db.query(User).filter(User.id == member.user_id).first()
        
        # Get latest AI insight for risk level
        ai_insight = db.query(AIInsight).filter(
            AIInsight.user_id == member.user_id
        ).order_by(AIInsight.last_analyzed.desc()).first()
        
        # Get payment method for bad loan check
        payment_method = db.query(PaymentMethod).filter(
            PaymentMethod.user_id == member.user_id
        ).first()
        
        # Get circle size for position assignment
        circle = db.query(Circle).filter(Circle.id == circle_id).first()
        circle_size = circle.max_participants
        
        # --- THE LOCK: 5% COMMITMENT FEE ---
        commitment_fee = float(circle.contribution_amount) * 0.05
        if float(member_user.wallet_balance) < commitment_fee:
            raise HTTPException(
                status_code=400, 
                detail=(
                    f"User wallet balance (NGN {member_user.wallet_balance}) is insufficient "
                    f"to lock the 5% commitment fee (NGN {commitment_fee})."
                )
            )
            
        # Deduct wallet and lock fee
        member_user.wallet_balance = float(member_user.wallet_balance) - commitment_fee
        member.commitment_fee_locked = commitment_fee
        db.add(member_user)
        # -----------------------------------
        
        # Assign position using AI analysis
        trust_score = member_user.trust_score if member_user else 50
        risk_level = ai_insight.risk_level.value if ai_insight else RiskLevel.medium.value
        has_bad_loan = payment_method.has_active_bad_loan if payment_method else False
        
        payout_position = brain.assign_payout_position(
            trust_score=trust_score,
            risk_level=risk_level,
            has_active_bad_loan=has_bad_loan,
            circle_size=circle_size
        )
        
        member.verification_status = "verified"
        member.verified_by = user.id
        member.verified_at = datetime.utcnow()
        member.payout_position = payout_position
        
        # Validate position shuffle to ensure diversity
        circle_members = db.query(CircleMember).filter(
            CircleMember.circle_id == circle_id,
            CircleMember.verification_status == "verified"
        ).all()
        
        position_valid = brain.validate_position_shuffle(circle_members, circle_size)
        if not position_valid:
            logger.warning(f"Position shuffle validation failed for circle {circle_id}")
        
        message = f"Member verified and assigned to payout position {payout_position}"
    else:
        # Reject
        member.verification_status = "rejected"
        member.verified_by = user.id
        member.verified_at = datetime.utcnow()
        member.rejection_reason = request_data.rejection_reason or "Admin rejection"
        
        message = "Member request rejected"
    
    db.commit()
    
    return VerifyMemberResponse(
        member_id=member.id,
        user_id=member.user_id,
        circle_id=member.circle_id,
        verification_status=member.verification_status,
        verified_by=member.verified_by,
        verified_at=member.verified_at,
        payout_position=payout_position,
        message=message
    )


# --- TRUST SCORE ENDPOINT ---
@app.get("/api/trust-score/{user_id}", response_model=TrustScoreResponse)
def get_trust_score(
    user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze user trust score"""
    try:
        # Get user's transaction history
        transactions = db.query(Transaction).filter(
            Transaction.user_id == user_id
        ).all()
        
        transaction_history = [
            {
                "amount": float(t.amount),
                "type": t.type.value if t.type else "unknown",
                "status": t.status.value if t.status else "unknown",
                "timestamp": t.timestamp.isoformat()
            }
            for t in transactions
        ]
        
        # Analyze with AI
        analysis = brain.analyze_trust(transaction_history)
        
        # Extract and normalize risk level
        risk_level_str = analysis.get("risk_level", "medium")
        if isinstance(risk_level_str, str):
            risk_level_str = risk_level_str.lower()
        else:
            risk_level_str = "medium"
        
        # Validate risk level
        if risk_level_str not in ["low", "medium", "high"]:
            risk_level_str = "medium"
        
        # Store insight
        insight = AIInsight(
            id=str(uuid.uuid4()),
            user_id=user_id,
            insight_text=analysis.get("reason", ""),
            risk_level=RiskLevel[risk_level_str]
        )
        db.add(insight)
        
        # Update user's trust score
        target_user = db.query(User).filter(User.id == user_id).first()
        if target_user:
            target_user.trust_score = analysis.get("trust_score", 50)
            db.add(target_user)
        
        db.commit()
        
        return {
            "user_id": user_id,
            "trust_score": analysis.get("trust_score", 50),
            "risk_level": risk_level_str,
            "recommended_position": analysis.get("position_recommendation", "middle"),
            "analysis": analysis.get("reason", "")
        }
    except Exception as e:
        print(f"Error in get_trust_score: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return a safe default if something goes wrong
        return {
            "user_id": user_id,
            "trust_score": 50,
            "risk_level": "medium",
            "recommended_position": "middle",
            "analysis": "Default analysis due to processing error"
        }


# --- HELPER FUNCTIONS ---
def analyze_and_reorder_circle(circle_id: str, db: Session):
    """Analyze all members and reorder by trust score"""
    members = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id
    ).all()
    
    # Calculate scores for each member
    member_scores = []
    for member in members:
        user = db.query(User).filter(User.id == member.user_id).first()
        transactions = db.query(Transaction).filter(
            Transaction.user_id == member.user_id
        ).all()
        
        transaction_history = [
            {
                "amount": float(t.amount),
                "type": t.type.value if t.type else "unknown",
                "status": t.status.value if t.status else "unknown",
                "timestamp": t.timestamp.isoformat()
            }
            for t in transactions
        ]
        
        if transaction_history:
            analysis = brain.analyze_trust(transaction_history)
            score = analysis.get("trust_score", 50)
        else:
            score = 50
        
        member_scores.append({
            "member": member,
            "score": score,
            "user": user
        })
    
    # Sort by score (highest first = safer payout order)
    member_scores.sort(key=lambda x: x["score"], reverse=True)
    
    # Update positions
    for position, item in enumerate(member_scores, 1):
        item["member"].payout_position = position
        db.add(item["member"])
    
    db.commit()


# --- CARD TOKENIZATION ENDPOINTS ---
@app.post("/api/wallet/tokenize-card", response_model=CardTokenizationResponse)
async def tokenize_card(
    card_data: CardTokenizationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Tokenize user's card for auto-debit collections
    Stores only token, card_type, expiry, and last 4 digits
    NO full card number, expiry, or CVV storage
    """
    # Tokenize card with Interswitch
    success, token_response = await card_tokenization_service.tokenize_card({
        "card_number": card_data.card_number,
        "expiry_month": card_data.expiry_month,
        "expiry_year": card_data.expiry_year,
        "cvv": card_data.cvv
    })
    
    if not success:
        raise HTTPException(status_code=400, detail=token_response.get("error", "Card tokenization failed"))
    
    # Store token in DB (NO card details - only token)
    existing = db.query(CardToken).filter(CardToken.user_id == user.id).first()
    if existing:
        existing.token = token_response["card_token"]
        existing.card_last_4 = token_response["pan_last_4"]
        existing.is_active = True
        existing.expires_at = token_response.get("token_expires_at")
    else:
        card_token = CardToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token=token_response["card_token"],
            card_last_4=token_response["pan_last_4"],
            is_active=True,
            expires_at=token_response.get("token_expires_at")
        )
        db.add(card_token)
    
    db.commit()
    logger.info(
        "Card tokenized for user %s: %s ending in %s",
        user.id,
        token_response["card_type"],
        token_response["pan_last_4"],
    )
    
    return CardTokenizationResponse(
        card_token=token_response["card_token"],
        card_type=token_response["card_type"],
        pan_last_4=token_response["pan_last_4"],
        expiry_date=token_response["expiry_date"],
        token_expires_at=token_response["token_expires_at"],
        message=token_response.get("message", "Card tokenized successfully")
    )


@app.post("/api/wallet/verify-face", response_model=FaceVerificationResponse)
async def verify_face(
    request_data: FaceVerificationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify user's face via biometric KYC
    Compares selfie with BVN photo from Interswitch
    
    Handling:
    - Score >= 70%: Auto-verified (face_verified = true)
    - Score 60-70%: Requires manual admin review (requires_manual_review = true)
    - Score < 60%: Auto-rejected (face_verified = false)
    """
    # Check if user has PaymentMethod and verified BVN
    payment_method = db.query(PaymentMethod).filter(
        PaymentMethod.user_id == user.id
    ).first()
    
    if not payment_method:
        raise HTTPException(
            status_code=400,
            detail="PaymentMethod not found. Verify bank account and BVN first."
        )
    
    if not payment_method.bvn_verified:
        raise HTTPException(
            status_code=400,
            detail="BVN must be verified before face verification"
        )
    
    selfie_image = b""
    if request_data.selfie_image_base64:
        try:
            selfie_image = base64.b64decode(request_data.selfie_image_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid selfie_image_base64 payload: {exc}") from exc

    verified, face_response = await bank_verification_service.verify_face(
        selfie_image=selfie_image,
        bvn=request_data.bvn
    )
    
    match_score = face_response.get("match_score", 0.0)
    requires_manual_review = face_response.get("requires_manual_review", False)
    
    # Update PaymentMethod with face verification result
    payment_method.face_match_score = Decimal(str(match_score * 100))  # Store as 0-100
    payment_method.face_verified = verified and not requires_manual_review
    payment_method.face_requires_manual_review = requires_manual_review
    
    if payment_method.face_verified:
        payment_method.face_verified_at = datetime.utcnow()
    
    db.commit()
    
    status = (
        "Verified"
        if payment_method.face_verified
        else ("Pending Manual Review" if requires_manual_review else "Failed")
    )
    logger.info(f"Face verification for user {user.id}: {status} (score: {match_score})")
    
    return FaceVerificationResponse(
        verified=payment_method.face_verified,
        requires_manual_review=requires_manual_review,
        bvn_last_4=face_response.get("bvn_last_4", "****"),
        match_score=match_score,
        confidence_level=face_response.get("confidence_level", "LOW"),
        message=face_response.get("message", "Face verification processed")
    )


# --- ADMIN KYC REVIEW ENDPOINTS ---

@app.post("/api/admin/kyc/approve-face-verification/{user_id}")
def approve_face_verification(
    user_id: str,
    admin_note: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin approves manual face verification (for 60-70% scores)
    Only accessible to admin users
    """
    require_admin_user(user)
    
    payment_method = db.query(PaymentMethod).filter(
        PaymentMethod.user_id == user_id
    ).first()
    
    if not payment_method:
        raise HTTPException(status_code=404, detail="PaymentMethod not found")
    
    if not payment_method.face_requires_manual_review:
        return {
            "success": False,
            "message": "No manual review pending for this user"
        }
    
    # Approve the manual review
    payment_method.face_verified = True
    payment_method.face_requires_manual_review = False
    payment_method.face_verified_at = datetime.utcnow()
    
    db.commit()
    
    logger.info(f"👤 Admin approved face verification for user {user_id} (note: {admin_note})")
    
    return {
        "success": True,
        "message": f"Face verification approved for user {user_id}",
        "face_match_score": float(payment_method.face_match_score or 0) / 100
    }


@app.post("/api/admin/kyc/reject-face-verification/{user_id}")
def reject_face_verification(
    user_id: str,
    rejection_reason: str = "Admin rejection",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Admin rejects manual face verification (user must re-submit)
    """
    require_admin_user(user)

    payment_method = db.query(PaymentMethod).filter(
        PaymentMethod.user_id == user_id
    ).first()
    
    if not payment_method:
        raise HTTPException(status_code=404, detail="PaymentMethod not found")
    
    # Reject the face verification
    payment_method.face_verified = False
    payment_method.face_requires_manual_review = False
    
    db.commit()
    
    logger.info(f"❌ Admin rejected face verification for user {user_id}: {rejection_reason}")
    
    return {
        "success": True,
        "message": f"Face verification rejected for user {user_id}",
        "reason": rejection_reason
    }


@app.get("/api/admin/kyc/flagged-users")
def get_flagged_kyc_users(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    CEO War Room: Get all flagged KYC statuses
    Shows users that need admin attention:
    - Manual face verification reviews (60-70%)
    - Bad loan detected
    - KYC rejected or flagged
    """
    require_admin_user(user)

    # Get all payment methods with flags
    flagged_users = db.query(PaymentMethod).filter(
        (PaymentMethod.face_requires_manual_review == True) |
        (PaymentMethod.has_active_bad_loan == True) |
        (PaymentMethod.kyc_status.in_(["flagged", "rejected"]))
    ).all()
    
    result = []
    for pm in flagged_users:
        user_obj = db.query(User).filter(User.id == pm.user_id).first()
        if user_obj:
            flags = []
            if pm.face_requires_manual_review:
                flags.append(f"Face verification pending (score: {float(pm.face_match_score or 0) / 100:.1%})")
            if pm.has_active_bad_loan:
                flags.append("Active bad loan detected")
            if pm.kyc_status == "flagged":
                flags.append("KYC flagged")
            if pm.kyc_status == "rejected":
                flags.append("KYC rejected")
            
            result.append({
                "user_id": pm.user_id,
                "full_name": user_obj.full_name,
                "email": user_obj.email,
                "kyc_status": pm.kyc_status,
                "flags": flags,
                "trust_score": user_obj.trust_score,
                "probability_of_default": float(pm.probability_of_default or 0),
                "updated_at": pm.updated_at.isoformat() if pm.updated_at else None
            })
    
    logger.info(f"CEO War Room: {len(result)} flagged users retrieved")
    
    return {
        "count": len(result),
        "flagged_users": result
    }


# --- DEADMAN'S SWITCH: PAYOUT APPROVAL MANAGEMENT ---

@app.get("/api/admin/token-expiry-warnings/{circle_id}")
def get_token_expiry_warnings(
    circle_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check for users whose card tokens expire before circle ends.
    THE TOKEN EXPIRY GHOST FIX - prevents 4-Hour Hawk failures.
    
    Returns: List of users needing new cards
    """
    require_admin_user(user)

    if not check_is_circle_admin(user.id, circle_id, db):
        raise HTTPException(status_code=403, detail="Not a circle admin")
    
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Get all members
    members = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id,
        CircleMember.verification_status == "verified"
    ).all()
    
    # Get card tokens for all members
    card_tokens = {}
    for member in members:
        card = db.query(CardToken).filter(CardToken.user_id == member.user_id).first()
        if card:
            card_tokens[member.user_id] = card
    
    # Check expiry
    circle_end_date = circle.expected_end_date or (datetime.utcnow() + timedelta(days=300))
    warnings = brain.check_token_expiry_warnings(circle_end_date, card_tokens)
    
    logger.info(f"Token expiry check for circle {circle_id}: {len(warnings)} warnings")
    
    return {
        "circle_id": circle_id,
        "circle_name": circle.name,
        "expected_end_date": circle_end_date.isoformat(),
        "warning_count": len(warnings),
        "warnings": warnings
    }


@app.get("/api/admin/escalated-payouts")
def get_escalated_payouts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    CEO War Room: Get all payouts pending > 24 hours.
    DEADMAN'S SWITCH - auto-escalates at 24h mark.
    
    Shows transactions that are:
    - Still in PENDING status
    - Requested more than 24 hours ago
    - Not yet escalated to CEO
    """
    require_admin_user(user)

    # Get all pending payouts older than 24 hours
    escalation_threshold = datetime.utcnow() - timedelta(hours=24)
    
    old_pending_payouts = db.query(Transaction).filter(
        Transaction.status == TransactionStatus.pending,
        Transaction.payout_requested_at <= escalation_threshold,
        Transaction.escalated_to_ceo == False
    ).all()
    
    # Also get recently escalated (in last 24 hours)
    recently_escalated = db.query(Transaction).filter(
        Transaction.escalated_to_ceo == True,
        Transaction.payout_requested_at >= escalation_threshold
    ).all()
    
    result_pending = []
    for txn in old_pending_payouts:
        hours_pending = (datetime.utcnow() - txn.payout_requested_at).total_seconds() / 3600
        member = db.query(CircleMember).filter(
            CircleMember.circle_id == txn.circle_id,
            CircleMember.user_id == txn.user_id
        ).first()
        user_obj = db.query(User).filter(User.id == txn.user_id).first()
        
        result_pending.append({
            "transaction_id": txn.id,
            "user_id": txn.user_id,
            "full_name": user_obj.full_name if user_obj else "Unknown",
            "circle_id": txn.circle_id,
            "amount": float(txn.amount),
            "type": txn.type.value if txn.type else "unknown",
            "payout_requested_at": txn.payout_requested_at.isoformat() if txn.payout_requested_at else None,
            "hours_pending": round(hours_pending, 1),
            "payout_position": member.payout_position if member else None,
            "action_required": "YES" if hours_pending > 24 else "SOON"
        })
    
    result_escalated = []
    for txn in recently_escalated:
        hours_escalated = (datetime.utcnow() - txn.payout_requested_at).total_seconds() / 3600
        result_escalated.append({
            "transaction_id": txn.id,
            "user_id": txn.user_id,
            "amount": float(txn.amount),
            "payout_approved_at": txn.payout_approved_at.isoformat() if txn.payout_approved_at else None,
            "hours_since_escalation": round(hours_escalated, 1)
        })
    
    logger.info(f"CEO Escalated Payouts: {len(old_pending_payouts)} urgent, {len(recently_escalated)} acted on")
    
    return {
        "critical_count": len(old_pending_payouts),
        "urgent_payouts": result_pending,
        "recently_escalated": result_escalated,
        "ceo_action_required": len(old_pending_payouts) > 0
    }


@app.post("/api/admin/escalated-payouts/{transaction_id}/approve")
def approve_escalated_payout(
    transaction_id: str,
    manual_approval_note: str = "CEO override",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    CEO manually approves a payout that was escalated.
    Bypasses circle admin approval if it's been > 24 hours.
    """
    require_admin_user(user)

    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if txn.status != TransactionStatus.pending:
        raise HTTPException(status_code=400, detail="Transaction is not pending")
    
    # Approve the payout
    txn.status = TransactionStatus.success
    txn.payout_approved_at = datetime.utcnow()
    txn.escalated_to_ceo = True
    
    db.commit()
    
    logger.info("CEO approved escalated payout: %s (note: %s)", transaction_id, manual_approval_note)
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "status": "approved",
        "payout_approved_at": txn.payout_approved_at.isoformat(),
        "message": f"Payout approved manually by CEO. Amount: NGN {txn.amount}"
    }


@app.get("/api/ceo/payouts/pending")
def get_pending_payouts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    CEO War Room: Get all pending & escalated payouts
    Uses this to manually push stalled payouts that are stuck > 24 hours
    """
    require_admin_user(user)

    pending = db.query(PayoutApproval).filter(
        PayoutApproval.status.in_(["pending", "escalated"])
    ).order_by(PayoutApproval.created_at.asc()).all()
    
    result = []
    for payout in pending:
        member = db.query(User).filter(User.id == payout.user_id).first()
        circle = db.query(Circle).filter(Circle.id == payout.circle_id).first()
        
        hours_pending = (datetime.utcnow() - payout.created_at).total_seconds() / 3600
        
        result.append({
            "id": payout.id,
            "circle_name": circle.name if circle else "Unknown",
            "member_name": member.full_name if member else "Unknown",
            "member_email": member.email if member else "Unknown",
            "amount": float(payout.amount),
            "status": payout.status,
            "created_at": payout.created_at.isoformat(),
            "hours_pending": round(hours_pending, 1),
            "escalation_reason": payout.escalation_reason,
            "flag_level": "CRITICAL" if hours_pending > 24 else "WARNING" if hours_pending > 12 else "INFO"
        })
    
    return {
        "count": len(result),
        "pending_payouts": result
    }


@app.post("/api/ceo/payouts/{payout_id}/approve-and-push")
async def approve_and_push_payout(
    payout_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    CEO Manual Payout Override: Approve a stalled payout and immediately process it.
    Bypasses normal admin review for emergency situations.
    
    This is the "push" action mentioned in the Deadman's Switch.
    """
    require_admin_user(user)

    payout = db.query(PayoutApproval).filter(PayoutApproval.id == payout_id).first()
    
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")
    
    if payout.status not in ["pending", "escalated"]:
        raise HTTPException(status_code=400, detail=f"Cannot approve payout with status: {payout.status}")
    
    # Update payout to approved
    payout.status = "approved"
    payout.approved_at = datetime.utcnow()
    payout.approved_by = user.id
    
    payout_result = None
    if payout.payment_method and payout.payment_method.payout_verified:
        payout_result = await interswitch.transfer_funds(
            recipient_bank_code=payout.payment_method.payout_bank_code,
            account_number=payout.payment_method.payout_account_number,
            amount=float(payout.amount),
            narration=f"Vortx payout {payout.id}"
        )
        payout.interswitch_ref = payout_result.get("ref")
        if payout_result.get("success"):
            payout.status = "paid"
            payout.paid_at = datetime.utcnow()
    
    db.add(payout)
    db.commit()
    
    member = db.query(User).filter(User.id == payout.user_id).first()
    circle = db.query(Circle).filter(Circle.id == payout.circle_id).first()
    
    logger.info(
        "CEO override approved payout %s by %s. Amount: NGN %.2f to %s",
        payout_id,
        user.full_name,
        float(payout.amount),
        member.full_name if member else "Unknown",
    )

    if payout_result is None:
        provider_status = "not_ready"
        provider_message = "No verified payout account linked"
        response_message = "Payout approved, but no verified payout account is linked yet."
    elif payout_result.get("success"):
        provider_status = "paid"
        provider_message = payout_result.get("message", "Provider transfer succeeded")
        response_message = "Payout approved and paid."
    else:
        provider_status = "provider_failed"
        provider_message = payout_result.get("message", "Provider transfer failed")
        response_message = "Payout approved, but the provider transfer did not complete."
    
    return {
        "success": True,
        "message": response_message,
        "payout_id": payout.id,
        "status": payout.status,
        "amount": float(payout.amount),
        "member": member.full_name if member else "Unknown",
        "circle": circle.name if circle else "Unknown",
        "provider_status": provider_status,
        "provider_message": provider_message
    }


# --- CIRCLE VALIDATION & INSURANCE POOL ENDPOINTS ---



@app.get("/api/circles/{circle_id}/validate-readiness")
def validate_circle_readiness(
    circle_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Validate if a circle is ready to start (CEO/Admin check).
    
    Rules:
    - At least 3 verified members
    - Max 2 members with active bad loans
    - Aggregate risk score < 60
    - At least 3 low-risk members
    
    Returns: readiness_status with message
    """
    # Check if user is circle admin
    if not check_is_circle_admin(user.id, circle_id, db):
        raise HTTPException(status_code=403, detail="Not a circle admin")
    
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Get all verified members
    members = db.query(CircleMember).filter(
        CircleMember.circle_id == circle_id,
        CircleMember.verification_status == "verified"
    ).all()
    
    if not members:
        return {
            "is_ready": False,
            "member_count": 0,
            "message": "No verified members in circle"
        }
    
    # Get payment methods for all members
    payment_methods = {}
    for member in members:
        pm = db.query(PaymentMethod).filter(PaymentMethod.user_id == member.user_id).first()
        if pm:
            payment_methods[member.user_id] = pm
    
    # Validate using AI brain
    is_ready, readiness_message = brain.validate_circle_readiness(members, payment_methods)
    avg_risk, bad_loan_count = brain.calculate_circle_risk_score(members, payment_methods)
    
    return {
        "is_ready": is_ready,
        "member_count": len(members),
        "aggregate_risk_score": round(avg_risk, 2),
        "bad_loan_count": bad_loan_count,
        "message": readiness_message
    }


@app.post("/api/circles/{circle_id}/process-contribution")
def process_contribution(
    circle_id: str,
    amount: float,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process a contribution with safety fee → insurance pool
    Called after successful debit from Interswitch
    """
    circle = db.query(Circle).filter(Circle.id == circle_id).first()
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Calculate insurance fee (1.5% by default)
    safety_fee = amount * INSURANCE_SAFETY_FEE
    net_contribution = amount - safety_fee
    
    # Get or create insurance pool
    pool = db.query(InsurancePool).filter(InsurancePool.circle_id == circle_id).first()
    if not pool:
        pool = InsurancePool(id=str(uuid.uuid4()), circle_id=circle_id)
        db.add(pool)
        db.flush()
    
    # Update pool
    pool.total_collected = float(pool.total_collected or 0) + safety_fee
    pool.current_balance = float(pool.total_collected or 0) - float(pool.total_paid_out or 0)
    
    # Update circle pot
    circle.total_pot = float(circle.total_pot or 0) + net_contribution
    
    # Create transaction
    transaction = Transaction(
        id=str(uuid.uuid4()),
        user_id=user.id,
        circle_id=circle_id,
        amount=net_contribution,
        type=TransactionType.contribution,
        status=TransactionStatus.success
    )
    
    db.add(pool)
    db.add(circle)
    db.add(transaction)
    db.commit()
    
    logger.info(
        "Contribution processed: NGN %.2f to pot, NGN %.2f to insurance",
        net_contribution,
        safety_fee,
    )
    
    return {
        "status": "success",
        "gross_amount": amount,
        "safety_fee": safety_fee,
        "net_contribution": net_contribution,
        "circle_pot": float(circle.total_pot)
    }


@app.get("/api/insurance/{circle_id}/status", response_model=InsurancePoolResponse)
def get_insurance_status(
    circle_id: str,
    db: Session = Depends(get_db)
):
    """Get insurance pool status for a circle"""
    pool = db.query(InsurancePool).filter(InsurancePool.circle_id == circle_id).first()
    
    if not pool:
        return {
            "id": str(uuid.uuid4()),
            "circle_id": circle_id,
            "total_collected": 0.0,
            "total_paid_out": 0.0,
            "current_balance": 0.0,
            "created_at": datetime.utcnow()
        }
    
    return InsurancePoolResponse.from_orm(pool)


# --- LOAN ENDPOINTS ---
@app.post("/api/loans/request", response_model=LoanRequestResponse)
def request_nano_loan(
    request_data: LoanRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    User requests or accepts AI-suggested nano-loan
    Used to bridge funding gaps before contribution due date
    """
    # Check if user has tokenized card
    card = db.query(CardToken).filter(CardToken.user_id == user.id).first()
    if not card or not card.is_active:
        raise HTTPException(status_code=400, detail="Tokenize card first")
    
    # Check circle exists
    circle = db.query(Circle).filter(Circle.id == request_data.circle_id).first()
    if not circle:
        raise HTTPException(status_code=404, detail="Circle not found")
    
    # Calculate interest
    interest = request_data.principal_amount * NANO_LOAN_INTEREST_RATE
    total_due = request_data.principal_amount + interest
    
    # Create loan
    loan = LoanRequest(
        id=str(uuid.uuid4()),
        user_id=user.id,
        circle_id=request_data.circle_id,
        principal_amount=request_data.principal_amount,
        interest_amount=interest,
        total_due=total_due,
        due_date=datetime.utcnow() + timedelta(days=7),
        status="active"
    )
    
    # Fund user's wallet immediately
    user.wallet_balance = float(user.wallet_balance or 0) + request_data.principal_amount
    
    db.add(loan)
    db.add(user)
    db.commit()
    
    logger.info("Nano-loan issued: NGN %.2f to %s", request_data.principal_amount, user.email)
    
    return LoanRequestResponse.from_orm(loan)


@app.get("/api/loans", response_model=List[LoanRequestResponse])
def get_user_loans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all loans for the current user"""
    loans = db.query(LoanRequest).filter(LoanRequest.user_id == user.id).all()
    
    return [LoanRequestResponse.from_orm(l) for l in loans]


# --- WEBHOOK HANDLER ---
@app.post("/api/webhooks/interswitch")
async def handle_interswitch_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive callbacks from Interswitch for completed transactions
    Updates transaction status and triggers next steps
    """
    try:
        body = await request.json()
        
        ref = body.get("transactionref")
        status_str = body.get("status", "").lower()  # success or failed
        amount = float(body.get("amount", 0)) / 100  # Convert from kobo to Naira
        
        logger.info(f"Webhook received: ref={ref}, status={status_str}")
        
        # Find transaction by interswitch reference
        transaction = db.query(Transaction).filter(
            Transaction.interswitch_ref == ref
        ).first()
        
        if not transaction:
            logger.warning(f"Transaction not found for ref: {ref}")
            return {"status": "not_found"}
        
        if status_str == "success":
            transaction.status = TransactionStatus.success
            
            # If this was a contribution, process it
            if transaction.type == TransactionType.contribution:
                circle = db.query(Circle).filter(
                    Circle.id == transaction.circle_id
                ).first()
                if circle:
                    circle.total_pot = float(circle.total_pot or 0) + amount
                    db.add(circle)
            
            # Check if any loan was being repaid
            loan = db.query(LoanRequest).filter(
                LoanRequest.user_id == transaction.user_id,
                LoanRequest.circle_id == transaction.circle_id,
                LoanRequest.is_repaid == False
            ).first()
            
            if loan and amount >= float(loan.total_due):
                loan.is_repaid = True
                loan.repayment_date = datetime.utcnow()
                db.add(loan)
                logger.info(f"Loan repaid: {loan.id}")
        
        else:
            transaction.status = TransactionStatus.failed
            
            # If contribution failed, create retry log
            if transaction.type == TransactionType.contribution:
                retry_log = RetryLog(
                    id=str(uuid.uuid4()),
                    user_id=transaction.user_id,
                    circle_id=transaction.circle_id,
                    amount=transaction.amount,
                    status="pending",
                    next_retry_at=datetime.utcnow() + timedelta(hours=4)
                )
                db.add(retry_log)
                logger.info(f"Retry scheduled for user {transaction.user_id}")
        
        db.add(transaction)
        db.commit()
        
        return {"status": "received", "transaction_id": transaction.id}
    
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}


# --- BANK INFO & KYC VERIFICATION ENDPOINTS ---

@app.post("/api/wallet/verify-bank-account", response_model=dict)
async def verify_bank_account(
    request: BankAccountVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify bank account (on blur) - calls Interswitch Name Inquiry.
    
    This is called immediately after user enters account number and selects bank.
    Returns account_name for verification.
    
    Step 1 in KYC flow: Bank Account Verification
    """
    try:
        from bank_verification import bank_verification_service
        
        # Verify bank account with Interswitch
        verified, bank_data = await bank_verification_service.verify_account(
            request.bank_code, 
            request.account_number
        )
        
        if not verified:
            return {
                "verified": False,
                "message": "Bank account verification failed",
                "account_name": None
            }
        
        # Store bank info in payment_method
        payment_method = db.query(PaymentMethod).filter(
            PaymentMethod.user_id == user.id
        ).first()
        
        if not payment_method:
            payment_method = PaymentMethod(
                id=str(uuid.uuid4()),
                user_id=user.id
            )
            db.add(payment_method)
        
        # Update payout info
        payment_method.payout_bank_code = request.bank_code
        payment_method.payout_account_number = request.account_number
        payment_method.payout_account_name = bank_data.get("account_name")
        payment_method.payout_verified = True
        payment_method.payout_verified_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "verified": True,
            "account_name": bank_data.get("account_name"),
            "message": "Bank account verified successfully"
        }
    
    except Exception as e:
        logger.error(f"Bank account verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wallet/verify-bvn", response_model=dict)
async def verify_bvn(
    request: BVNVerificationRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify BVN and credit history.
    
    Step 2 in KYC flow: BVN Verification + Credit Check
    
    This also:
    1. Checks for active bad loans elsewhere
    2. Calculates probability of default
    3. Determines if user should be pushed to late positions
    """
    try:
        from bank_verification import bank_verification_service
        from encryption import encryption_service
        
        # Verify BVN
        bvn_verified, bvn_data = await bank_verification_service.verify_bvn(
            request.bvn,
            user.full_name
        )
        
        if not bvn_verified:
            return {
                "verified": False,
                "kyc_status": "rejected",
                "message": "BVN verification failed"
            }
        
        # Get credit history
        credit_verified, credit_data = await bank_verification_service.check_credit_history(
            request.bvn
        )
        
        # Get or create payment method
        payment_method = db.query(PaymentMethod).filter(
            PaymentMethod.user_id == user.id
        ).first()
        
        if not payment_method:
            payment_method = PaymentMethod(
                id=str(uuid.uuid4()),
                user_id=user.id
            )
            db.add(payment_method)
        
        # Store BVN (encrypted!) and credit info
        payment_method.bvn_encrypted = encryption_service.encrypt(request.bvn)
        payment_method.bvn_verified = True
        payment_method.bvn_verified_at = datetime.utcnow()
        
        # Store credit check results
        payment_method.credit_check_done = True
        payment_method.has_active_bad_loan = credit_data.get("has_active_bad_loan", False)
        payment_method.probability_of_default = Decimal(credit_data.get("probability_of_default", 0))
        
        # Determine KYC status
        if credit_data.get("has_active_bad_loan") or payment_method.probability_of_default > 0.5:
            payment_method.kyc_status = "flagged"  # Will be assigned to late positions
        else:
            payment_method.kyc_status = "verified"
        
        db.commit()
        
        return {
            "verified": True,
            "bvn_last_4": request.bvn[-4:],
            "kyc_status": payment_method.kyc_status,
            "has_active_bad_loan": credit_data.get("has_active_bad_loan", False),
            "probability_of_default": float(payment_method.probability_of_default),
            "message": "BVN and credit check completed successfully"
        }
    
    except Exception as e:
        logger.error(f"BVN verification error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wallet/kyc-status", response_model=KYCStatusResponse)
def get_kyc_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's complete KYC/payment method status.
    
    Shows:
    - Bank account verification status
    - BVN verification status
    - Credit check results
    - Assigned payout position (if in a circle)
    - **[NEW] Card expiry warnings if token expires before circle ends**
    """
    payment_method = db.query(PaymentMethod).filter(
        PaymentMethod.user_id == user.id
    ).first()
    
    if not payment_method:
        # Create blank payment method if doesn't exist
        payment_method = PaymentMethod(
            id=str(uuid.uuid4()),
            user_id=user.id
        )
        db.add(payment_method)
        db.commit()
    
    # === TOKEN EXPIRY GHOST ALERT (NEW) ===
    # Check if user's card token expires before any active circle ends
    card_token = db.query(CardToken).filter(
        CardToken.user_id == user.id,
        CardToken.is_active == True
    ).first()
    
    card_expiry_warning = None
    circles_at_risk = []
    
    if card_token and card_token.expires_at:
        # Get all circles this user is in
        user_circles = db.query(Circle).join(
            CircleMember, CircleMember.circle_id == Circle.id
        ).filter(
            CircleMember.user_id == user.id,
            Circle.status.in_(["active", "pending"])
        ).all()
        
        for circle in user_circles:
            if circle.expected_end_date:
                estimated_end = circle.expected_end_date
            elif circle.frequency.value == "weekly":
                estimated_end = circle.created_at + timedelta(weeks=circle.max_participants)
            elif circle.frequency.value == "monthly":
                estimated_end = circle.created_at + timedelta(days=30 * circle.max_participants)
            else:
                estimated_end = circle.created_at + timedelta(days=365)
            
            # Check if card expires before circle ends
            if card_token.expires_at < estimated_end:
                circles_at_risk.append(circle.id)
        
        if circles_at_risk:
            card_expiry_warning = (
                f"Your card expires on {card_token.expires_at.strftime('%B %d, %Y')} "
                "before this circle ends. Please link a new card to keep your spot."
            )
    
    return {
        "id": payment_method.id,
        "user_id": payment_method.user_id,
        "kyc_status": payment_method.kyc_status,
        "bvn_verified": payment_method.bvn_verified,
        "payout_verified": payment_method.payout_verified,
        "face_verified": payment_method.face_verified,
        "credit_check_done": payment_method.credit_check_done,
        "has_active_bad_loan": payment_method.has_active_bad_loan,
        "probability_of_default": float(payment_method.probability_of_default or 0),
        "card_token_expires_at": card_token.expires_at if card_token else None,
        "card_expiry_warning": card_expiry_warning,
        "circles_at_risk": circles_at_risk,
        "created_at": payment_method.created_at,
        "updated_at": payment_method.updated_at,
    }


# ==================== THE EXIT ENGINE (Marketplace) ====================

@app.post("/api/market/sell-position", response_model=PositionSaleResponse)
def sell_position(
    request: MarketSellRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List a circle position for sale"""
    # Verify user is in circle and has a position
    circle_member = db.query(CircleMember).filter(
        CircleMember.circle_id == request.circle_id,
        CircleMember.user_id == user.id,
        CircleMember.verification_status == "verified"
    ).first()
    
    if not circle_member or not circle_member.payout_position:
        raise HTTPException(status_code=400, detail="Valid position not found in this circle")
        
    # Check if already listed
    existing_sale = db.query(PositionSaleMarket).filter(
        PositionSaleMarket.circle_member_id == circle_member.id,
        PositionSaleMarket.status == "active"
    ).first()
    
    if existing_sale:
        raise HTTPException(status_code=400, detail="Position is already listed for sale")
        
    sale = PositionSaleMarket(
        id=str(uuid.uuid4()),
        circle_id=request.circle_id,
        seller_id=user.id,
        circle_member_id=circle_member.id,
        payout_position=circle_member.payout_position,
        asking_price=request.asking_price
    )
    
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return PositionSaleResponse.from_orm(sale)


@app.post("/api/market/buy-position")
def buy_position(
    request: MarketBuyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Buy a listed position from another user"""
    sale = db.query(PositionSaleMarket).filter(
        PositionSaleMarket.id == request.listing_id,
        PositionSaleMarket.status == "active"
    ).first()
    
    if not sale:
        raise HTTPException(status_code=404, detail="Listing not found or already sold")
        
    if sale.seller_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own position")
        
    # Check wallet balance
    if float(user.wallet_balance) < float(sale.asking_price):
        raise HTTPException(status_code=400, detail="Insufficient wallet balance")
        
    # Debit buyer, credit seller
    seller = db.query(User).filter(User.id == sale.seller_id).first()
    
    user.wallet_balance = float(user.wallet_balance) - float(sale.asking_price)
    seller.wallet_balance = float(seller.wallet_balance) + float(sale.asking_price)
    
    # Transfer position ownership
    circle_member = db.query(CircleMember).filter(CircleMember.id == sale.circle_member_id).first()
    circle_member.user_id = user.id
    
    # Mark as sold
    sale.status = "sold"
    sale.buyer_id = user.id
    sale.sold_at = datetime.utcnow()
    
    db.commit()
    return {"success": True, "message": f"Position {sale.payout_position} purchased successfully", "listing_id": sale.id}


@app.post("/api/market/swap-position")
def swap_position(
    request: MarketSwapRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Swap positions with another member (demands a 1% Kindness Bonus fee)"""
    user_member = db.query(CircleMember).filter(
        CircleMember.circle_id == request.circle_id,
        CircleMember.user_id == user.id
    ).first()
    
    target_member = db.query(CircleMember).filter(
        CircleMember.circle_id == request.circle_id,
        CircleMember.user_id == request.target_member_id
    ).first()
    
    if not user_member or not target_member:
        raise HTTPException(status_code=404, detail="One or both members not found in circle")
        
    # Deduct Swap Fee (e.g. fixed 500 NGN)
    swap_fee = 500.00
    if float(user.wallet_balance) < swap_fee:
        raise HTTPException(status_code=400, detail="Insufficient funds for swap fee")
        
    user.wallet_balance = float(user.wallet_balance) - swap_fee
    
    # Swap positions
    user_pos = user_member.payout_position
    user_member.payout_position = target_member.payout_position
    target_member.payout_position = user_pos
    
    db.commit()
    return {"success": True, "message": "Positions swapped successfully", "fee_charged": swap_fee}


# ==================== THE LEGAL PULL (GSI) ====================

@app.post("/api/admin/trigger-gsi/{user_id}")
async def trigger_gsi(
    user_id: str,
    admin: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger Interswitch Global Standing Instruction (GSI) 
    To recover funds from ANY Nigerian bank account linked to the defaulter's BVN.
    """
    require_admin_user(admin)
    
    defaulter = db.query(PaymentMethod).filter(PaymentMethod.user_id == user_id).first()
    if not defaulter or not defaulter.bvn_encrypted:
        raise HTTPException(status_code=400, detail="Cannot trigger GSI: No BVN found for user")
        
    user_data = db.query(User).filter(User.id == user_id).first()
    
    result = await interswitch.trigger_gsi(defaulter.bvn_encrypted[-4:], "Manual admin trigger")
    if result.get("success"):
        logger.critical("GSI triggered for user %s", user_data.email)
    else:
        logger.error("GSI request failed for user %s: %s", user_data.email, result.get("message"))
    
    return {
        "success": bool(result.get("success")),
        "status": "GSI_INITIATED" if result.get("success") else "GSI_UNAVAILABLE",
        "message": (
            f"Global Standing Instruction triggered across all accounts tied to BVN for {user_data.full_name}."
            if result.get("success")
            else "GSI request could not be initiated."
        ),
        "estimated_recovery": "2-4 hours" if result.get("success") else None,
        "provider_message": result.get("message")
    }


# ==================== WHATSAPP WEBHOOK ====================

@app.get("/api/webhooks/whatsapp")
def verify_whatsapp_webhook(
    request: Request
):
    """Webhook verification for Meta Graph API"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    logger.info(
        "WhatsApp webhook verify request: mode=%s token_present=%s token_match=%s",
        mode,
        bool(token),
        bool(token and token == WHATSAPP_VERIFY_TOKEN),
    )

    if mode and token:
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            logger.info("WEBHOOK_VERIFIED")
            return int(challenge)
        else:
            raise HTTPException(status_code=403, detail="Verification failed")
    raise HTTPException(status_code=400, detail="Missing parameters")


@app.post("/api/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle incoming WhatsApp messages"""
    body = await request.json()
    
    if body.get("object"):
        if "entry" in body and body["entry"]:
            for entry in body["entry"]:
                if "changes" in entry and entry["changes"]:
                    for change in entry["changes"]:
                        value = change.get("value", {})
                        if "messages" in value and value["messages"]:
                            for message in value["messages"]:
                                # Get phone number (WhatsApp ID)
                                from_phone = message.get("from")
                                
                                # Only process text messages
                                if message.get("type") == "text":
                                    text_body = message["text"].get("body")
                                    
                                    logger.info(f"Received WA message from {from_phone}: {text_body}")
                                    
                                    # Process synchronously so local webhook tests see the effect immediately.
                                    whatsapp_service.process_incoming_message(from_phone, text_body, db)

        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Not a WhatsApp API payload")


# --- HEALTH CHECK ---

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Vortx API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
