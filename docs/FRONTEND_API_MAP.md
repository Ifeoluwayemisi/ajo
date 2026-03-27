# Frontend API Map

This document is the frontend-first contract for the current Vortx backend.

## Base

- Local base URL: `http://localhost:8000`
- Auth type: `Bearer <access_token>`
- Docs: `/docs`
- Health: `/health`

## Auth

- `POST /api/auth/register`
  Creates a user and returns `access_token`, `token_type`, and `user`.
- `POST /api/auth/login`
  Logs a user in and returns `access_token`, `token_type`, and `user`.
- `GET /api/auth/me`
  Returns the authenticated user.

## Wallet And KYC

- `GET /api/wallet`
  Returns wallet balance and trust score.
- `POST /api/wallet/fund/initialize`
  Records a pending deposit intent.
  Response now includes `provider_status`.
  Values:
  - `unconfigured`: provider init is not configured in this environment
  - `pending_handoff`: transaction is recorded locally and provider handoff is pending
- `GET /api/transactions`
  Returns the authenticated user's transactions.
- `POST /api/wallet/verify-bank-account`
  Verifies payout bank account details and stores verified payout info.
- `POST /api/wallet/verify-bvn`
  Verifies BVN, runs credit checks, and updates KYC status.
- `POST /api/wallet/verify-face`
  Performs face verification and may return manual review.
- `GET /api/wallet/kyc-status`
  Returns the consolidated KYC state, token expiry warning, and circles at risk.
- `POST /api/wallet/tokenize-card`
  Tokenizes a card and stores only token-safe metadata.

## Circles

- `POST /api/circles/create`
  Creates a circle and auto-adds the creator as first verified member and admin.
- `GET /api/circles`
  Lists circles the current user belongs to.
- `GET /api/circles/{circle_id}`
  Returns circle details.
- `GET /api/circles/code/{short_code}`
  Joins discovery flow by short code such as `VX-1234`.
- `POST /api/circles/{circle_id}/join`
  Direct join flow. Older path. Prefer request-based join for product UX.
- `POST /api/circles/{circle_id}/request-join`
  Creates a pending membership that requires admin verification.
- `POST /api/circles/{circle_id}/add-member`
  Admin adds a user by email with pending verification.
- `POST /api/circles/{circle_id}/verify-member/{member_id}`
  Approves or rejects a pending member.
  Important business rule:
  - approval fails if the member cannot lock the 5 percent commitment fee

## AI And Risk

- `GET /api/trust-score/{user_id}`
  Returns trust score, risk level, recommended position, and analysis.
- `GET /api/circles/{circle_id}/validate-readiness`
  Returns whether the group is safe enough to start.

## Contributions, Insurance, And Loans

- `POST /api/circles/{circle_id}/process-contribution`
  Processes a contribution and allocates the insurance safety fee.
- `GET /api/insurance/{circle_id}/status`
  Returns the insurance pool status for a circle.
- `POST /api/loans/request`
  Requests a nano-loan for a circle.
- `GET /api/loans`
  Lists the authenticated user's loans.

## Admin, CEO, And Operations

- `GET /api/admin/kyc/flagged-users`
  Returns the CEO war-room flagged KYC list.
- `POST /api/admin/kyc/approve-face-verification/{user_id}`
  Approves a manually reviewed face verification.
- `POST /api/admin/kyc/reject-face-verification/{user_id}`
  Rejects a manually reviewed face verification.
- `GET /api/admin/token-expiry-warnings/{circle_id}`
  Returns members with card expiry risk for the circle timeline.
- `GET /api/admin/escalated-payouts`
  Returns escalated and critical payouts.
- `POST /api/admin/escalated-payouts/{transaction_id}/approve`
  Manually approves an escalated payout transaction.
- `GET /api/ceo/payouts/pending`
  Returns pending and escalated payout approvals.
- `POST /api/ceo/payouts/{payout_id}/approve-and-push`
  Approves a payout and attempts provider transfer.
  Response includes `provider_status`.
  Values:
  - `not_ready`: no verified payout account is linked
  - `paid`: provider transfer succeeded
  - `provider_failed`: payout approval succeeded but provider transfer failed
- `POST /api/admin/trigger-gsi/{user_id}`
  Attempts a GSI recovery request.
  Response is now honest about provider outcome.
  Values:
  - `status=GSI_INITIATED` when the provider layer accepts the request
  - `status=GSI_UNAVAILABLE` when the request cannot be initiated

## Marketplace And Exit

- `POST /api/market/sell-position`
  Lists a verified payout position for sale.
- `POST /api/market/buy-position`
  Buys an active listed position.
- `POST /api/market/swap-position`
  Swaps two member positions and charges a swap fee.

## Webhooks And WhatsApp

- `GET /api/webhooks/whatsapp`
  Meta webhook verification route.
- `POST /api/webhooks/whatsapp`
  Receives inbound WhatsApp messages.
- `POST /api/webhooks/interswitch`
  Receives provider transaction callbacks.

## Frontend Notes

- Use `request-join` instead of the older direct `join` route for the main product flow.
- Treat provider-backed operations as environment-sensitive.
- In sandbox, some flows return simulated success data.
- In production without valid provider credentials, routes now return explicit provider-state messages rather than pretending success.
- The only env file the backend loads is the repo-root file: `hackathon/vortx/.env`.
