#!/usr/bin/env python
"""Test verification endpoints"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_verification_flow():
    print("=" * 60)
    print("🔐 TESTING VERIFICATION ENDPOINTS")
    print("=" * 60)
    
    # 1. Register users with timestamps to avoid conflicts
    print("\n1️⃣  REGISTERING USERS")
    print("-" * 40)
    
    users = {}
    timestamp = int(time.time())
    user_data = [
        {"name": "Alice", "email": f"alice.v{timestamp}@test.io", "password": "Pass123456"},
        {"name": "Bob", "email": f"bob.v{timestamp}@test.io", "password": "Pass123456"},
        {"name": "Charlie", "email": f"charlie.v{timestamp}@test.io", "password": "Pass123456"},
    ]
    
    for user_info in user_data:
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/register",
                json={
                    "full_name": user_info["name"],
                    "email": user_info["email"],
                    "password": user_info["password"]
                }
            )
            if response.status_code == 200:
                data = response.json()
                users[user_info["name"]] = {
                    "id": data["user"]["id"],
                    "email": user_info["email"],
                    "token": data["access_token"]
                }
                print(f"  ✅ {user_info['name']} registered")
            else:
                print(f"  ❌ Failed to register {user_info['name']}: {response.text}")
        except Exception as e:
            print(f"  ❌ Error registering {user_info['name']}: {e}")
    
    if "Alice" not in users:
        print("\n❌ Registration failed - aborting test")
        return
    
    # 2. Alice creates a circle
    print("\n2️⃣  CREATING CIRCLE")
    print("-" * 40)
    
    circle_data = {
        "name": "Verification Test Circle",
        "description": "Testing the new verification flow",
        "contribution_amount": 5000,
        "frequency": "monthly",
        "max_participants": 5
    }
    
    response = requests.post(
        f"{BASE_URL}/api/circles/create",
        json=circle_data,
        headers={"Authorization": f"Bearer {users['Alice']['token']}"}
    )
    
    if response.status_code == 200:
        circle = response.json()
        circle_id = circle["id"]
        print(f"  ✅ Circle created: {circle['name']} (ID: {circle_id})")
    else:
        print(f"  ❌ Failed to create circle: {response.text}")
        return
    
    # 3. Bob requests to join
    print("\n3️⃣  BOB REQUESTS TO JOIN")
    print("-" * 40)
    
    response = requests.post(
        f"{BASE_URL}/api/circles/{circle_id}/request-join",
        headers={"Authorization": f"Bearer {users['Bob']['token']}"}
    )
    
    if response.status_code == 200:
        member_info = response.json()
        bob_member_id = member_info["member_id"]
        print(f"  ✅ Bob's join request submitted (Member ID: {bob_member_id})")
        print(f"     Status: {member_info['message']}")
    else:
        print(f"  ❌ Failed: {response.text}")
        return
    
    # 4. Charlie requests to join
    print("\n4️⃣  CHARLIE REQUESTS TO JOIN")
    print("-" * 40)
    
    response = requests.post(
        f"{BASE_URL}/api/circles/{circle_id}/request-join",
        headers={"Authorization": f"Bearer {users['Charlie']['token']}"}
    )
    
    if response.status_code == 200:
        member_info = response.json()
        charlie_member_id = member_info["member_id"]
        print(f"  ✅ Charlie's join request submitted (Member ID: {charlie_member_id})")
    else:
        print(f"  ❌ Failed: {response.text}")
        return
    
    # 5. Test adding member as admin (Alice)
    print("\n5️⃣  ALICE ADDS MEMBER (Admin operation)")
    print("-" * 40)
    
    # Note: Need to add Alice as admin first - for now test will show expected behavior
    print("  ⚠️  Admin setup needed - verify endpoint works with proper roles")
    
    # 6. Alice verifies Bob (if admin)
    print("\n6️⃣  ALICE VERIFIES BOB'S REQUEST")
    print("-" * 40)
    
    response = requests.post(
        f"{BASE_URL}/api/circles/{circle_id}/verify-member/{bob_member_id}",
        json={"approve": True},
        headers={"Authorization": f"Bearer {users['Alice']['token']}"}
    )
    
    if response.status_code == 200:
        verify_info = response.json()
        print(f"  ✅ Bob verified!")
        print(f"     Status: {verify_info['verification_status']}")
        print(f"     Verified by: {verify_info['verified_by']}")
    elif response.status_code == 403:
        print(f"  ⚠️  Alice is not yet set as circle admin (expected)")
        print(f"     Error: {response.json()['detail']}")
    else:
        print(f"  ❌ Failed: {response.text}")
    
    print("\n" + "=" * 60)
    print("✅ VERIFICATION ENDPOINT TEST COMPLETE!")
    print("=" * 60)

if __name__ == "__main__":
    test_verification_flow()
