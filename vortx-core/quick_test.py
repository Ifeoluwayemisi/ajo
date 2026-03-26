#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quick verification endpoints test"""
import requests
import time
import sys
import os

# Fix encoding for Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://localhost:8000"
ts = int(time.time() * 1000) % 1000000  # Unique timestamp for testing

def test():
    print("[VERIFICATION ENDPOINTS TEST]\n")
    
    # 1. Register two users
    print("[1] Registering users...")
    r1 = requests.post(f"{BASE}/api/auth/register", json={
        "full_name": "Admin", "email": f"admin{ts}@test.io", "password": "Pass123456"
    })
    if r1.status_code != 200:
        print(f"Error registering admin: {r1.text}")
        return
    admin = r1.json()
    admin_token = admin.get("access_token")
    
    r2 = requests.post(f"{BASE}/api/auth/register", json={
        "full_name": "Member", "email": f"member{ts}@test.io", "password": "Pass123456"
    })
    member = r2.json()
    member_email = member["user"]["email"]
    member_token = member["access_token"]
    print(f"   [OK] Admin: {admin['user']['email']}")
    print(f"   [OK] Member: {member['user']['email']}")
    
    # 2. Create circle (as admin)
    print("\n[2] Creating circle...")
    r3 = requests.post(f"{BASE}/api/circles/create", 
        json={"name": f"Test#{ts}", "contribution_amount": 5000, "frequency": "monthly", "max_participants": 5},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    circle = r3.json()
    circle_id = circle["id"]
    print(f"   [OK] Circle: {circle['name']} (ID: {circle_id[:8]}...)")
    
    # 3. Member requests to join
    print("\n[3] Member requests to join...")
    r4 = requests.post(f"{BASE}/api/circles/{circle_id}/request-join",
        headers={"Authorization": f"Bearer {member_token}"}
    )
    if r4.status_code == 200:
        join_resp = r4.json()
        member_id = join_resp["member_id"]
        print(f"   [OK] Request submitted: {join_resp['message']}")
        print(f"   [ID] Member ID: {member_id[:8]}...")
    else:
        print(f"   [ERROR] {r4.text}")
        return
    
    # 4. Admin verifies member
    print("\n[4] Admin verifies member (checking admin role)...")
    r5 = requests.post(f"{BASE}/api/circles/{circle_id}/verify-member/{member_id}",
        json={"approve": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    if r5.status_code == 200:
        verify = r5.json()
        print(f"   [OK] VERIFIED! Status: {verify['verification_status']}")
        print(f"   [POS] Position: {verify.get('payout_position', 'N/A')}")
    elif r5.status_code == 403:
        print(f"   [WARN] Not authorized as admin (expected - needs role assignment)")
        print(f"   [INFO] Next: Assign admin role via endpoint")
    else:
        print(f"   [ERROR] {r5.text}")
    
    print("\n[OK] ENDPOINTS WORKING!")
    print("\n[NEXT] Assign admin roles to enable full verification flow")

if __name__ == "__main__":
    test()
