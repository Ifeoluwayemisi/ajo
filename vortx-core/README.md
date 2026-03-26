# Vortx Backend API

FastAPI-based backend for the Vortx AI-powered group savings platform.

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables:

- `DATABASE_URL`: PostgreSQL connection
- `OPENAI_API_KEY`: Your OpenAI API key
- `SECRET_KEY`: Change to a random string in production
- `INTERSWITCH_*`: Your Interswitch merchant credentials

### 4. Initialize Database

```bash
python -c "from database import init_db; init_db()"
```

### 5. Run Server

```bash
python app.py
# OR use uvicorn
uvicorn app:app --reload
```

Server runs on `http://localhost:8000`

## API Endpoints

### Authentication

- **POST** `/api/auth/register` - Register new user
  - Body: `{ full_name, email, password }`
  - Returns: JWT token + user data

- **POST** `/api/auth/login` - Login user
  - Body: `{ email, password }`
  - Returns: JWT token + user data

- **GET** `/api/auth/me` - Get current user (requires auth)

### Wallet

- **GET** `/api/wallet` - Get wallet balance
- **POST** `/api/wallet/fund/initialize` - Start payment flow
  - Body: `{ amount }`
- **GET** `/api/transactions` - Transaction history

### Circles

- **POST** `/api/circles/create` - Create new circle
  - Body: `{ name, description, contribution_amount, frequency, max_participants }`
- **GET** `/api/circles` - Get user's circles

- **GET** `/api/circles/{circle_id}` - Get circle details

- **POST** `/api/circles/{circle_id}/join` - Join circle
  - Triggers AI reordering of members by trust score

### Trust Score

- **GET** `/api/trust-score/{user_id}` - Analyze user's trust score
  - Returns: score, risk level, recommended payout position

## Authentication

All protected endpoints require Bearer token in Authorization header:

```
Authorization: Bearer <your_jwt_token>
```

## Testing with cURL

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"John Doe","email":"john@example.com","password":"securepass123"}'

# Get wallet (replace TOKEN with your JWT)
curl -X GET http://localhost:8000/api/wallet \
  -H "Authorization: Bearer TOKEN"
```

## Next Steps

1. **Interswitch Integration** - Implement actual payment processing
2. **WebSocket Chat** - Real-time circle notifications
3. **Admin Dashboard** - Monitor platform metrics
4. **Mobile App** - React Native companion
