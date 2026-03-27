$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8000"
$ts = Get-Date -Format "yyyyMMddHHmmss"

function Add-Result {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Name,
        [string]$Status,
        [string]$Detail
    )

    $Results.Add([pscustomobject]@{
        endpoint = $Name
        status = $Status
        detail = $Detail
    })
}

function Try-Step {
    param(
        [scriptblock]$Action
    )

    try {
        return & $Action
    }
    catch {
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
            return @{
                __error = $true
                message = $_.ErrorDetails.Message
            }
        }

        return @{
            __error = $true
            message = $_.Exception.Message
        }
    }
}

$results = New-Object 'System.Collections.Generic.List[object]'

$health = Invoke-RestMethod -Method Get -Uri "$base/health"
Add-Result $results "GET /health" "PASS" ($health | ConvertTo-Json -Compress)

$root = Invoke-RestMethod -Method Get -Uri "$base/"
Add-Result $results "GET /" "PASS" ($root | ConvertTo-Json -Compress)

$docs = Invoke-WebRequest -UseBasicParsing -Uri "$base/docs"
Add-Result $results "GET /docs" "PASS" "status=$($docs.StatusCode)"

$orgEmail = "organizer-$ts@test.io"
$memEmail = "member-$ts@test.io"

$org = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Organizer"
    email = $orgEmail
    password = "SecurePass123456"
    user_type = "organizer"
} | ConvertTo-Json)
Add-Result $results "POST /api/auth/register organizer" "PASS" $org.user.email

$mem = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Member"
    email = $memEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
Add-Result $results "POST /api/auth/register member" "PASS" $mem.user.email

$orgHeaders = @{ Authorization = "Bearer $($org.access_token)" }
$memHeaders = @{ Authorization = "Bearer $($mem.access_token)" }

$login = Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType "application/json" -Body (@{
    email = $orgEmail
    password = "SecurePass123456"
} | ConvertTo-Json)
Add-Result $results "POST /api/auth/login" "PASS" $login.user.email

$me = Invoke-RestMethod -Method Get -Uri "$base/api/auth/me" -Headers $orgHeaders
Add-Result $results "GET /api/auth/me" "PASS" $me.email

$wallet = Invoke-RestMethod -Method Get -Uri "$base/api/wallet" -Headers $orgHeaders
Add-Result $results "GET /api/wallet" "PASS" "balance=$($wallet.balance)"

$fund = Try-Step { Invoke-RestMethod -Method Post -Uri "$base/api/wallet/fund/initialize" -Headers $orgHeaders -ContentType "application/json" -Body (@{ amount = 25000 } | ConvertTo-Json) }
if ($fund.__error) {
    Add-Result $results "POST /api/wallet/fund/initialize" "FAIL" $fund.message
}
else {
    Add-Result $results "POST /api/wallet/fund/initialize" "PASS" ($fund | ConvertTo-Json -Compress)
}

$transactions = Invoke-RestMethod -Method Get -Uri "$base/api/transactions" -Headers $orgHeaders
Add-Result $results "GET /api/transactions" "PASS" "count=$(@($transactions).Count)"

$circle = Invoke-RestMethod -Method Post -Uri "$base/api/circles/create" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    name = "Circle $ts"
    description = "Smoke test circle"
    contribution_amount = 5000
    frequency = "monthly"
    max_participants = 5
} | ConvertTo-Json)
Add-Result $results "POST /api/circles/create" "PASS" $circle.short_code

$circleDetail = Invoke-RestMethod -Method Get -Uri "$base/api/circles/$($circle.id)" -Headers $orgHeaders
Add-Result $results "GET /api/circles/{id}" "PASS" $circleDetail.name

$circleByCode = Invoke-RestMethod -Method Get -Uri "$base/api/circles/code/$($circle.short_code)" -Headers $orgHeaders
Add-Result $results "GET /api/circles/code/{short_code}" "PASS" $circleByCode.short_code

$circles = Invoke-RestMethod -Method Get -Uri "$base/api/circles" -Headers $orgHeaders
Add-Result $results "GET /api/circles" "PASS" "count=$(@($circles).Count)"

$joinRequest = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($circle.id)/request-join" -Headers $memHeaders
Add-Result $results "POST /api/circles/{id}/request-join" "PASS" $joinRequest.message

$verifyMember = Try-Step {
    Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($circle.id)/verify-member/$($joinRequest.member_id)" -Headers $orgHeaders -ContentType "application/json" -Body (@{
        approve = $true
    } | ConvertTo-Json)
}
if ($verifyMember.__error) {
    if ($verifyMember.message -match "commitment fee") {
        Add-Result $results "POST /api/circles/{id}/verify-member/{member_id}" "BLOCKED" $verifyMember.message
    }
    else {
        Add-Result $results "POST /api/circles/{id}/verify-member/{member_id}" "FAIL" $verifyMember.message
    }
}
else {
    Add-Result $results "POST /api/circles/{id}/verify-member/{member_id}" "PASS" $verifyMember.verification_status
}

$trust = Try-Step { Invoke-WebRequest -UseBasicParsing -Headers $orgHeaders -Uri "$base/api/trust-score/$($mem.user.id)" }
if ($trust.__error) {
    Add-Result $results "GET /api/trust-score/{user_id}" "FAIL" $trust.message
}
else {
    Add-Result $results "GET /api/trust-score/{user_id}" "PASS" "status=$($trust.StatusCode)"
}

$bank = Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bank-account" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    bank_code = "044"
    account_number = "0123456789"
} | ConvertTo-Json)
Add-Result $results "POST /api/wallet/verify-bank-account" "PASS" $bank.account_name

$bvn = Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bvn" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678901"
} | ConvertTo-Json)
Add-Result $results "POST /api/wallet/verify-bvn" "PASS" $bvn.kyc_status

$kyc = Invoke-RestMethod -Method Get -Uri "$base/api/wallet/kyc-status" -Headers $orgHeaders
Add-Result $results "GET /api/wallet/kyc-status" "PASS" $kyc.kyc_status

$tokenize = Try-Step {
    Invoke-RestMethod -Method Post -Uri "$base/api/wallet/tokenize-card" -Headers $orgHeaders -ContentType "application/json" -Body (@{
        card_number = "4242424242424242"
        expiry_month = "12"
        expiry_year = "29"
        cvv = "123"
    } | ConvertTo-Json)
}
if ($tokenize.__error) {
    Add-Result $results "POST /api/wallet/tokenize-card" "FAIL" $tokenize.message
}
else {
    Add-Result $results "POST /api/wallet/tokenize-card" "PASS" $tokenize.pan_last_4
}

$face = Try-Step {
    Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-face" -Headers $orgHeaders -ContentType "application/json" -Body (@{
        bvn = "12345678901"
    } | ConvertTo-Json)
}
if ($face.__error) {
    Add-Result $results "POST /api/wallet/verify-face" "FAIL" $face.message
}
else {
    Add-Result $results "POST /api/wallet/verify-face" "PASS" $face.confidence_level
}

$readiness = Invoke-RestMethod -Method Get -Uri "$base/api/circles/$($circle.id)/validate-readiness" -Headers $orgHeaders
Add-Result $results "GET /api/circles/{id}/validate-readiness" "PASS" $readiness.message

$contribution = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($circle.id)/process-contribution?amount=1000" -Headers $orgHeaders
Add-Result $results "POST /api/circles/{id}/process-contribution" "PASS" "net=$($contribution.net_contribution)"

$insurance = Invoke-RestMethod -Method Get -Uri "$base/api/insurance/$($circle.id)/status"
Add-Result $results "GET /api/insurance/{circle_id}/status" "PASS" "balance=$($insurance.current_balance)"

$loan = Try-Step {
    Invoke-RestMethod -Method Post -Uri "$base/api/loans/request" -Headers $orgHeaders -ContentType "application/json" -Body (@{
        circle_id = $circle.id
        principal_amount = 1500
    } | ConvertTo-Json)
}
if ($loan.__error) {
    Add-Result $results "POST /api/loans/request" "FAIL" $loan.message
}
else {
    Add-Result $results "POST /api/loans/request" "PASS" $loan.status
}

$loans = Invoke-RestMethod -Method Get -Uri "$base/api/loans" -Headers $orgHeaders
Add-Result $results "GET /api/loans" "PASS" "count=$(@($loans).Count)"

$joinCircleEmail = "directjoin-$ts@test.io"
$joinCircleUser = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Direct Join User"
    email = $joinCircleEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$joinCircleHeaders = @{ Authorization = "Bearer $($joinCircleUser.access_token)" }
$directCircle = Invoke-RestMethod -Method Post -Uri "$base/api/circles/create" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    name = "Direct Circle $ts"
    description = "Direct join path"
    contribution_amount = 3000
    frequency = "monthly"
    max_participants = 5
} | ConvertTo-Json)
$directJoin = Try-Step { Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($directCircle.id)/join" -Headers $joinCircleHeaders }
if ($directJoin.__error) {
    Add-Result $results "POST /api/circles/{id}/join" "FAIL" $directJoin.message
}
else {
    Add-Result $results "POST /api/circles/{id}/join" "PASS" $directJoin.id
}

$addMemberEmail = "added-$ts@test.io"
$addMemberUser = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Added User"
    email = $addMemberEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$addMember = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($circle.id)/add-member" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    user_email = $addMemberEmail
} | ConvertTo-Json)
Add-Result $results "POST /api/circles/{id}/add-member" "PASS" $addMember.message

$manualEmail = "manual-$ts@test.io"
$manualUser = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Manual Review User"
    email = $manualEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$manualHeaders = @{ Authorization = "Bearer $($manualUser.access_token)" }
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bank-account" -Headers $manualHeaders -ContentType "application/json" -Body (@{
    bank_code = "044"
    account_number = "0123456790"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bvn" -Headers $manualHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678201"
} | ConvertTo-Json) | Out-Null
$manualFace = Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-face" -Headers $manualHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678201"
} | ConvertTo-Json)
if ($manualFace.requires_manual_review) {
    Add-Result $results "POST /api/wallet/verify-face manual-review" "PASS" $manualFace.message
}
else {
    Add-Result $results "POST /api/wallet/verify-face manual-review" "FAIL" ($manualFace | ConvertTo-Json -Compress)
}

$approveManual = Invoke-RestMethod -Method Post -Uri "$base/api/admin/kyc/approve-face-verification/$($manualUser.user.id)" -Headers $orgHeaders
Add-Result $results "POST /api/admin/kyc/approve-face-verification/{user_id}" "PASS" $approveManual.message

$rejectEmail = "reject-$ts@test.io"
$rejectUser = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Reject Review User"
    email = $rejectEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$rejectHeaders = @{ Authorization = "Bearer $($rejectUser.access_token)" }
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bank-account" -Headers $rejectHeaders -ContentType "application/json" -Body (@{
    bank_code = "044"
    account_number = "0123456791"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bvn" -Headers $rejectHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678211"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-face" -Headers $rejectHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678211"
} | ConvertTo-Json) | Out-Null
$rejectManual = Invoke-RestMethod -Method Post -Uri "$base/api/admin/kyc/reject-face-verification/$($rejectUser.user.id)" -Headers $orgHeaders
Add-Result $results "POST /api/admin/kyc/reject-face-verification/{user_id}" "PASS" $rejectManual.message

$flaggedEmail = "flagged-$ts@test.io"
$flaggedUser = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Flagged User"
    email = $flaggedEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$flaggedHeaders = @{ Authorization = "Bearer $($flaggedUser.access_token)" }
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bank-account" -Headers $flaggedHeaders -ContentType "application/json" -Body (@{
    bank_code = "044"
    account_number = "0123456792"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/verify-bvn" -Headers $flaggedHeaders -ContentType "application/json" -Body (@{
    bvn = "12345678909"
} | ConvertTo-Json) | Out-Null
$flaggedUsers = Invoke-RestMethod -Method Get -Uri "$base/api/admin/kyc/flagged-users" -Headers $orgHeaders
if ($flaggedUsers.count -ge 1) {
    Add-Result $results "GET /api/admin/kyc/flagged-users" "PASS" "count=$($flaggedUsers.count)"
}
else {
    Add-Result $results "GET /api/admin/kyc/flagged-users" "FAIL" ($flaggedUsers | ConvertTo-Json -Compress)
}

$expiryWarnings = Invoke-RestMethod -Method Get -Uri "$base/api/admin/token-expiry-warnings/$($circle.id)" -Headers $orgHeaders
Add-Result $results "GET /api/admin/token-expiry-warnings/{circle_id}" "PASS" "warnings=$($expiryWarnings.warning_count)"

$escalated = Invoke-RestMethod -Method Get -Uri "$base/api/admin/escalated-payouts" -Headers $orgHeaders
Add-Result $results "GET /api/admin/escalated-payouts" "PASS" "critical=$($escalated.critical_count)"

$approveEscalated = Try-Step { Invoke-RestMethod -Method Post -Uri "$base/api/admin/escalated-payouts/not-a-real-transaction/approve" -Headers $orgHeaders }
if ($approveEscalated.__error -and $approveEscalated.message -match "Transaction not found") {
    Add-Result $results "POST /api/admin/escalated-payouts/{transaction_id}/approve" "PASS" "expected 404 for missing transaction seed"
}
else {
    Add-Result $results "POST /api/admin/escalated-payouts/{transaction_id}/approve" "FAIL" (($approveEscalated | ConvertTo-Json -Compress))
}

$ceoPending = Invoke-RestMethod -Method Get -Uri "$base/api/ceo/payouts/pending" -Headers $orgHeaders
Add-Result $results "GET /api/ceo/payouts/pending" "PASS" "count=$($ceoPending.count)"

$approvePush = Try-Step { Invoke-RestMethod -Method Post -Uri "$base/api/ceo/payouts/not-a-real-payout/approve-and-push" -Headers $orgHeaders }
if ($approvePush.__error -and $approvePush.message -match "Payout not found") {
    Add-Result $results "POST /api/ceo/payouts/{payout_id}/approve-and-push" "PASS" "expected 404 for missing payout seed"
}
else {
    Add-Result $results "POST /api/ceo/payouts/{payout_id}/approve-and-push" "FAIL" (($approvePush | ConvertTo-Json -Compress))
}

$gsi = Invoke-RestMethod -Method Post -Uri "$base/api/admin/trigger-gsi/$($org.user.id)" -Headers $orgHeaders
Add-Result $results "POST /api/admin/trigger-gsi/{user_id}" "PASS" $gsi.status

$marketCircle = Invoke-RestMethod -Method Post -Uri "$base/api/circles/create" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    name = "Market Circle $ts"
    description = "Marketplace test"
    contribution_amount = 4000
    frequency = "monthly"
    max_participants = 5
} | ConvertTo-Json)

$marketBuyerEmail = "marketbuyer-$ts@test.io"
$marketBuyer = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Market Buyer"
    email = $marketBuyerEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$marketBuyerHeaders = @{ Authorization = "Bearer $($marketBuyer.access_token)" }
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/tokenize-card" -Headers $marketBuyerHeaders -ContentType "application/json" -Body (@{
    card_number = "5555555555554444"
    expiry_month = "12"
    expiry_year = "29"
    cvv = "123"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/loans/request" -Headers $marketBuyerHeaders -ContentType "application/json" -Body (@{
    circle_id = $marketCircle.id
    principal_amount = 2000
} | ConvertTo-Json) | Out-Null
$marketJoin = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($marketCircle.id)/request-join" -Headers $marketBuyerHeaders
$marketVerify = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($marketCircle.id)/verify-member/$($marketJoin.member_id)" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    approve = $true
} | ConvertTo-Json)
Add-Result $results "POST /api/circles/{id}/verify-member/{member_id} with funded member" "PASS" $marketVerify.verification_status

$sell = Invoke-RestMethod -Method Post -Uri "$base/api/market/sell-position" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    circle_id = $marketCircle.id
    asking_price = 500
} | ConvertTo-Json)
Add-Result $results "POST /api/market/sell-position" "PASS" $sell.id

$buyerTopup = Invoke-RestMethod -Method Post -Uri "$base/api/loans/request" -Headers $marketBuyerHeaders -ContentType "application/json" -Body (@{
    circle_id = $marketCircle.id
    principal_amount = 700
} | ConvertTo-Json)
$buy = Invoke-RestMethod -Method Post -Uri "$base/api/market/buy-position" -Headers $marketBuyerHeaders -ContentType "application/json" -Body (@{
    listing_id = $sell.id
} | ConvertTo-Json)
Add-Result $results "POST /api/market/buy-position" "PASS" $buy.message

$swapCircle = Invoke-RestMethod -Method Post -Uri "$base/api/circles/create" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    name = "Swap Circle $ts"
    description = "Swap test"
    contribution_amount = 4000
    frequency = "monthly"
    max_participants = 5
} | ConvertTo-Json)
$swapMemberEmail = "swapmember-$ts@test.io"
$swapMember = Invoke-RestMethod -Method Post -Uri "$base/api/auth/register" -ContentType "application/json" -Body (@{
    full_name = "Swap Member"
    email = $swapMemberEmail
    password = "SecurePass123456"
    user_type = "member"
} | ConvertTo-Json)
$swapMemberHeaders = @{ Authorization = "Bearer $($swapMember.access_token)" }
Invoke-RestMethod -Method Post -Uri "$base/api/wallet/tokenize-card" -Headers $swapMemberHeaders -ContentType "application/json" -Body (@{
    card_number = "4111111111111111"
    expiry_month = "12"
    expiry_year = "29"
    cvv = "123"
} | ConvertTo-Json) | Out-Null
Invoke-RestMethod -Method Post -Uri "$base/api/loans/request" -Headers $swapMemberHeaders -ContentType "application/json" -Body (@{
    circle_id = $swapCircle.id
    principal_amount = 1000
} | ConvertTo-Json) | Out-Null
$swapJoin = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($swapCircle.id)/request-join" -Headers $swapMemberHeaders
$swapVerify = Invoke-RestMethod -Method Post -Uri "$base/api/circles/$($swapCircle.id)/verify-member/$($swapJoin.member_id)" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    approve = $true
} | ConvertTo-Json)
$swap = Invoke-RestMethod -Method Post -Uri "$base/api/market/swap-position" -Headers $orgHeaders -ContentType "application/json" -Body (@{
    circle_id = $swapCircle.id
    target_member_id = $swapMember.user.id
} | ConvertTo-Json)
Add-Result $results "POST /api/market/swap-position" "PASS" $swap.message

$waVerify = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=cf4d90de6823de37f18612a0c23efd79&hub.challenge=12345"
if ($waVerify.Content -eq "12345") {
    Add-Result $results "GET /api/webhooks/whatsapp" "PASS" $waVerify.Content
}
else {
    Add-Result $results "GET /api/webhooks/whatsapp" "FAIL" $waVerify.Content
}

$waPost = Invoke-RestMethod -Method Post -Uri "$base/api/webhooks/whatsapp" -ContentType "application/json" -Body '{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"messages":[{"from":"2348012345678","type":"text","text":{"body":"help"}}]}}]}]}'
Add-Result $results "POST /api/webhooks/whatsapp" "PASS" $waPost.status

$interswitchWebhook = Invoke-RestMethod -Method Post -Uri "$base/api/webhooks/interswitch" -ContentType "application/json" -Body '{"transactionref":"missing-ref","status":"success","amount":100000}'
Add-Result $results "POST /api/webhooks/interswitch" "PASS" $interswitchWebhook.status

$passCount = @($results | Where-Object { $_.status -eq "PASS" }).Count
$blockedCount = @($results | Where-Object { $_.status -eq "BLOCKED" }).Count
$failCount = @($results | Where-Object { $_.status -eq "FAIL" }).Count

[pscustomobject]@{
    summary = [pscustomobject]@{
        pass = $passCount
        blocked = $blockedCount
        fail = $failCount
    }
    results = $results
} | ConvertTo-Json -Depth 5
