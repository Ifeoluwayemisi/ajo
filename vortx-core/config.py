"""
Vortx Configuration
Load all environment variables from the project root .env file.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load .env from project root (hackathon/vortx/.env)
# override=True ensures the project file wins over stale shell/system vars.
load_dotenv(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'),
    override=True,
)

# ========================================
# CORE APPLICATION
# ========================================
APP_NAME = os.getenv("APP_NAME", "Vortx API")
APP_VERSION = "0.1.0"
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# ========================================
# DATABASE
# ========================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vortx.db")

# ========================================
# AUTHENTICATION & SECURITY
# ========================================
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# ========================================
# OPENAI / AI BRAIN
# ========================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o")

# ========================================
# INTERSWITCH INTEGRATION
# ========================================
# Environment selector: 'sandbox' or 'production'
INTERSWITCH_ENV = os.getenv("INTERSWITCH_ENV", "sandbox")

# Sandbox Credentials
INTERSWITCH_CLIENT_ID_SANDBOX = os.getenv("INTERSWITCH_CLIENT_ID_SANDBOX", "")
INTERSWITCH_SECRET_KEY_SANDBOX = os.getenv("INTERSWITCH_SECRET_KEY_SANDBOX", "")
INTERSWITCH_API_BASE_SANDBOX = os.getenv("INTERSWITCH_API_BASE_SANDBOX", "https://sandbox.interswitchng.com")

# Production Credentials
INTERSWITCH_CLIENT_ID_PROD = os.getenv("INTERSWITCH_CLIENT_ID_PROD", "")
INTERSWITCH_SECRET_KEY_PROD = os.getenv("INTERSWITCH_SECRET_KEY_PROD", "")
INTERSWITCH_API_BASE_PROD = os.getenv("INTERSWITCH_API_BASE_PROD", "https://api.interswitchng.com")

# Merchant Details (Same for both)
INTERSWITCH_TERMINAL_ID = os.getenv("INTERSWITCH_TERMINAL_ID", "")
INTERSWITCH_MERCHANT_CODE = os.getenv("INTERSWITCH_MERCHANT_CODE", "")
INTERSWITCH_PAY_ITEM_ID = os.getenv("INTERSWITCH_PAY_ITEM_ID", "")

# Select active credentials based on environment
if INTERSWITCH_ENV == "production":
    INTERSWITCH_CLIENT_ID = INTERSWITCH_CLIENT_ID_PROD
    INTERSWITCH_SECRET_KEY = INTERSWITCH_SECRET_KEY_PROD
    INTERSWITCH_API_BASE = INTERSWITCH_API_BASE_PROD
else:  # sandbox
    INTERSWITCH_CLIENT_ID = INTERSWITCH_CLIENT_ID_SANDBOX
    INTERSWITCH_SECRET_KEY = INTERSWITCH_SECRET_KEY_SANDBOX
    INTERSWITCH_API_BASE = INTERSWITCH_API_BASE_SANDBOX


# ========================================
# FINTECH REVENUE CONFIGURATION
# ========================================
# Safety fee taken from every contribution → insurance pool
INSURANCE_SAFETY_FEE = float(os.getenv("INSURANCE_SAFETY_FEE", "0.015"))  # 1.5%

# Transaction fee on contributions
TRANSACTION_FEE_RATE = float(os.getenv("TRANSACTION_FEE_RATE", "0.02"))  # 2%

# Interest rate for 48-hour nano-loans
NANO_LOAN_INTEREST_RATE = float(os.getenv("NANO_LOAN_INTEREST_RATE", "0.08"))  # 8%

# Commission on position swap fees (Vortx takes this %)
SWAP_COMMISSION_RATE = float(os.getenv("SWAP_COMMISSION_RATE", "0.5"))  # 50%

# Annual interest rate from Interswitch escrow account
ESCROW_INTEREST_RATE = float(os.getenv("ESCROW_INTEREST_RATE", "0.05"))  # 5%

# ========================================
# BUSINESS LOGIC - RETRY ENGINE
# ========================================
RETRY_INTERVAL_HOURS = int(os.getenv("RETRY_INTERVAL_HOURS", "4"))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "5"))

# ========================================
# BUSINESS LOGIC - NANO-LOANS
# ========================================
NANO_LOAN_OFFER_HOURS = int(os.getenv("NANO_LOAN_OFFER_HOURS", "48"))  # Check 48h before due
NANO_LOAN_TERM_DEFAULT = int(os.getenv("NANO_LOAN_TERM_DEFAULT", "7"))  # Default 7-day repayment

# ========================================
# BUSINESS LOGIC - GOVERNANCE
# ========================================
HIGH_VALUE_THRESHOLD = float(os.getenv("HIGH_VALUE_THRESHOLD", "100000"))  # ₦100k
DEADMAN_SWITCH_HOURS = int(os.getenv("DEADMAN_SWITCH_HOURS", "24"))  # Admin override after 24h

# ========================================
# MASTER CEO / OVERRIDE
# ========================================
MASTER_CEO_PIN = os.getenv("MASTER_CEO_PIN", "1234")

# ========================================
# WHATSAPP BOT
# ========================================
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "").strip().strip("\"'")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "").strip().strip("\"'")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip().strip("\"'")

# ========================================
# FRONTEND
# ========================================
NEXT_PUBLIC_API_URL = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
NEXT_PUBLIC_APP_NAME = os.getenv("NEXT_PUBLIC_APP_NAME", "Vortx")
