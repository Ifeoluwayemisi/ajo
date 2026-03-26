# 🎯 QUICK REFERENCE - Test Commands

## Setup Test Data

```bash
# 1. Signup as ORGANIZER
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Chidi",
    "email": "chidi@vortx.io",
    "password": "TestPass123456",
    "user_type": "organizer"
  }'

# Copy the access_token from response
TOKEN_ORG="<paste_token_here>"

# 2. Signup as MEMBER
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Eze",
    "email": "eze@vortx.io",
    "password": "TestPass654321",
    "user_type": "member"
  }'

# Copy the access_token
TOKEN_MEM="<paste_token_here>"
```

---

## Create Circle (as Organizer)

```bash
CIRCLE_ID=$(curl -s -X POST http://localhost:8000/api/circles/create \
  -H "Authorization: Bearer $TOKEN_ORG" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Savings Circle",
    "contribution_amount": 10000,
    "frequency": "monthly",
    "max_participants": 5
  }' | jq -r '.id')

echo "Circle ID: $CIRCLE_ID"
```

---

## Member Requests to Join

```bash
MEMBER_ID=$(curl -s -X POST http://localhost:8000/api/circles/$CIRCLE_ID/request-join \
  -H "Authorization: Bearer $TOKEN_MEM" \
  -H "Content-Type: application/json" | jq -r '.member_id')

echo "Member ID: $MEMBER_ID"
echo "Status: PENDING (waiting for approval)"
```

---

## Organizer Approves Member

```bash
# Approve
curl -X POST http://localhost:8000/api/circles/$CIRCLE_ID/verify-member/$MEMBER_ID \
  -H "Authorization: Bearer $TOKEN_ORG" \
  -H "Content-Type: application/json" \
  -d '{"approve": true}'

# Response should show: "verification_status": "verified"
```

---

## Alternative: Organizer Directly Adds Member

```bash
curl -X POST http://localhost:8000/api/circles/$CIRCLE_ID/add-member \
  -H "Authorization: Bearer $TOKEN_ORG" \
  -H "Content-Type: application/json" \
  -d '{"user_email": "eze@vortx.io"}'

# Member automatically VERIFIED (no approval needed)
```

---

## Common Errors & Fixes

| Error                      | Cause                    | Fix                                 |
| -------------------------- | ------------------------ | ----------------------------------- |
| "Invalid token"            | Missing "Bearer " prefix | Use `Authorization: Bearer {token}` |
| "Not a circle admin"       | Member trying to approve | Only circle creator can approve     |
| "Email already registered" | Email exists             | Use different email with timestamp  |
| "Method Not Allowed"       | Wrong HTTP method        | Check POST vs GET                   |

---

## Python Testing Script

```python
import requests
import time

BASE = "http://localhost:8000"
EMAIL_SUFFIX = int(time.time() * 1000) % 1000000

# Organizer signup
org = requests.post(f"{BASE}/api/auth/register", json={
    "full_name": "Organizer", "email": f"org-{EMAIL_SUFFIX}@test.io",
    "password": "SecurePass123456", "user_type": "organizer"
}).json()
token_org = org["access_token"]

# Member signup
mem = requests.post(f"{BASE}/api/auth/register", json={
    "full_name": "Member", "email": f"mem-{EMAIL_SUFFIX}@test.io",
    "password": "SecurePass123456", "user_type": "member"
}).json()
token_mem = mem["access_token"]

# Create circle
circle = requests.post(f"{BASE}/api/circles/create",
    json={"name": f"Circle {EMAIL_SUFFIX}", "contribution_amount": 5000,
          "frequency": "monthly", "max_participants": 5},
    headers={"Authorization": f"Bearer {token_org}"}
).json()
circle_id = circle["id"]

# Member requests
join = requests.post(f"{BASE}/api/circles/{circle_id}/request-join",
    headers={"Authorization": f"Bearer {token_mem}"}
).json()
member_id = join["member_id"]

# Organizer approves
verify = requests.post(f"{BASE}/api/circles/{circle_id}/verify-member/{member_id}",
    json={"approve": True},
    headers={"Authorization": f"Bearer {token_org}"}
).json()

print(f"Status: {verify['verification_status']}")  # Should print: verified
```

---

## Server Commands

```bash
# Start server
cd vortx-core
python run_server.py

# Run tests
python test_roles.py       # Full role test
python quick_test.py       # Quick verification test

# Check health
curl http://localhost:8000/health
```

---

## Important Notes

✅ **Token Format**: Always use `Bearer {token}` in Authorization header  
✅ **Auto-Admin**: Circle creators are automatically CEO admins  
✅ **User Types**: organizer | member (choose at signup)  
✅ **Join Methods**: request-to-join OR direct-add-by-admin  
✅ **Verification**: PENDING → VERIFIED after organizer approval

---

## Files for Reference

- [MEMBER_JOINING_GUIDE.md](./MEMBER_JOINING_GUIDE.md) - Complete guide
- [test_roles.py](./test_roles.py) - Full test script
- [quick_test.py](./quick_test.py) - Quick test
- [MEMBER_JOINING_IMPLEMENTATION_COMPLETE.md](../MEMBER_JOINING_IMPLEMENTATION_COMPLETE.md) - Summary
