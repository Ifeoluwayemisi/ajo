import requests
import json

BASE_URL = "http://localhost:8000"

# Register an organizer and member
print("=" * 50)
print("Creating test users...")

# Register organizer
org_resp = requests.post(f"{BASE_URL}/api/auth/register",
    json={
        "email": f"trust-test-org@vortx.io",
        "password": "TempPass123!",
        "full_name": "Trust Test Org",
        "user_type": "organizer"
    }
)
print(f"Register Response: {org_resp.json()}")
org_data = org_resp.json()
org_id = org_data.get("id") or org_data.get("user", {}).get("id")
org_token = org_data.get("access_token") or org_data.get("token")
print(f"✓ Organizer: {org_id}")

# Register member
mem_resp = requests.post(f"{BASE_URL}/api/auth/register",
    json={
        "email": f"trust-test-mem@vortx.io",
        "password": "TempPass123!",
        "full_name": "Trust Test Member",
        "user_type": "member"
    }
)
mem_data = mem_resp.json()
mem_id = mem_data.get("id") or mem_data.get("user", {}).get("id")
mem_token = mem_data.get("access_token") or mem_data.get("token")
print(f"✓ Member: {mem_id}")

# Test trust score endpoint
print("\n" + "=" * 50)
print("Testing trust-score endpoint...")
print(f"Endpoint: GET /api/trust-score/{mem_id}")
print(f"Auth: Bearer {mem_token[:30]}...")

trust = requests.get(f"{BASE_URL}/api/trust-score/{mem_id}",
    headers={"Authorization": f"Bearer {mem_token}"}
)

print(f"\nStatus Code: {trust.status_code}")
print(f"Response Headers: {dict(trust.headers)}")
print(f"Response Body:\n{json.dumps(trust.json(), indent=2)}")
