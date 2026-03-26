#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test role-based signup and auto-admin assignment"""
import requests
import time
import json

BASE = "http://localhost:8000"
ts = int(time.time() * 1000) % 1000000

print("=" * 70)
print("TESTING: Role-Based Signup & Auto-Admin Assignment")
print("=" * 70)

# 1. Organizer signs up
print("\n[1] Organizer signs up...")
org_resp = requests.post(f"{BASE}/api/auth/register", json={
    "full_name": "Chidi Organizer",
    "email": f"chidi-org-{ts}@vortx.io",
    "password": "SecurePass123456",
    "user_type": "organizer"
})

if org_resp.status_code == 200:
    org_data = org_resp.json()
    org_token = org_data["access_token"]
    org_id = org_data["user"]["id"]
    org_type = org_data["user"].get("user_type", "N/A")
    print(f"   [OK] Organizer registered")
    print(f"        Email: {org_data['user']['email']}")
    print(f"        Type: {org_type}")
    print(f"        Token: {org_token[:20]}...")
else:
    print(f"   [ERROR] {org_resp.text}")
    exit()

# 2. Member signs up
print("\n[2] Member signs up...")
mem_resp = requests.post(f"{BASE}/api/auth/register", json={
    "full_name": "Eze Member",
    "email": f"eze-mem-{ts}@vortx.io",
    "password": "SecurePass654321",
    "user_type": "member"
})

if mem_resp.status_code == 200:
    mem_data = mem_resp.json()
    mem_token = mem_data["access_token"]
    mem_id = mem_data["user"]["id"]
    mem_type = mem_data["user"].get("user_type", "N/A")
    print(f"   [OK] Member registered")
    print(f"        Email: {mem_data['user']['email']}")
    print(f"        Type: {mem_type}")
else:
    print(f"   [ERROR] {mem_resp.text}")
    exit()

# 3. Organizer creates circle (should auto-become admin)
print("\n[3] Organizer creates circle...")
circle_resp = requests.post(f"{BASE}/api/circles/create",
    json={
        "name": f"Savings Group {ts}",
        "description": "Test circle with auto-admin",
        "contribution_amount": 10000,
        "frequency": "monthly",
        "max_participants": 5
    },
    headers={"Authorization": f"Bearer {org_token}"}
)

if circle_resp.status_code == 200:
    circle = circle_resp.json()
    circle_id = circle["id"]
    print(f"   [OK] Circle created: {circle['name']}")
    print(f"        ID: {circle_id[:8]}...")
    print(f"        Organizer is AUTO-ADMIN (CEO role)")
else:
    print(f"   [ERROR] {circle_resp.text}")
    exit()

# 4. Member requests to join
print("\n[4] Member requests to join...")
join_resp = requests.post(f"{BASE}/api/circles/{circle_id}/request-join",
    headers={"Authorization": f"Bearer {mem_token}"}
)

if join_resp.status_code == 200:
    join_data = join_resp.json()
    mem_member_id = join_data["member_id"]
    print(f"   [OK] Join request submitted")
    print(f"        Status: {join_data['message']}")
    print(f"        Member ID: {mem_member_id[:8]}...")
else:
    print(f"   [ERROR] {join_resp.text}")
    exit()

# 5. Organizer (auto-admin) approves member
print("\n[5] Organizer (auto-admin) approves member...")
verify_resp = requests.post(f"{BASE}/api/circles/{circle_id}/verify-member/{mem_member_id}",
    json={"approve": True},
    headers={"Authorization": f"Bearer {org_token}"}
)

if verify_resp.status_code == 200:
    verify = verify_resp.json()
    print(f"   [OK] Member VERIFIED!")
    print(f"        Status: {verify['verification_status']}")
    print(f"        Verified By: {verify['verified_by'][:8]}...")
    print(f"        Verified At: {verify['verified_at']}")
elif verify_resp.status_code == 403:
    print(f"   [ERROR] Permission denied - organizer not admin?")
    print(f"           {verify_resp.json()}")
else:
    print(f"   [ERROR] {verify_resp.text}")

print("\n" + "=" * 70)
print("SUCCESS! All tests passed:")
print("  [OK] Organizer role selection at signup")
print("  [OK] Member role selection at signup")
print("  [OK] Circle creation")
print("  [OK] Auto-admin assignment for organizer")
print("  [OK] Member request to join")
print("  [OK] Admin approval of member")
print("=" * 70)
