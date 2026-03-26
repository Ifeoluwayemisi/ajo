import requests
import json
import random

BASE_URL = "http://localhost:8000"
TIMESTAMP = random.randint(100000, 999999)

# Register member directly
mem_resp = requests.post(f"{BASE_URL}/api/auth/register",
    json={
        "full_name": "Test Member",
        "email": f"test-mem-{TIMESTAMP}@vortx.io",
        "password": "TempPass123!",
        "user_type": "member"
    }
)

if mem_resp.status_code != 200:
    print(f"Registration failed: {mem_resp.status_code}")
    print(mem_resp.json())
    exit(1)

mem_data = mem_resp.json()
mem_id = mem_data["user"]["id"]
mem_token = mem_data["access_token"]

print(f"Member registered: {mem_id}")
print(f"Token: {mem_token[:30]}...")

# Now test trust score endpoint
print("\n" + "=" * 50)
print("Testing /api/trust-score/{} endpoint".format(mem_id))

trust_resp = requests.get(
    f"{BASE_URL}/api/trust-score/{mem_id}",
    headers={"Authorization": f"Bearer {mem_token}"}
)

print(f"Status: {trust_resp.status_code}")
if trust_resp.status_code == 200:
    print("Success!")
    print(json.dumps(trust_resp.json(), indent=2))
else:
    print("Error!")
    print(trust_resp.text)
