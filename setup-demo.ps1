#!/usr/bin/env pwsh
# ===================================================
# CogniGuard Demo Environment Setup Script
# Run this ONCE before starting the Android demo.
# ===================================================

$ErrorActionPreference = "Continue"
$device = "89b67c32"

Write-Host "`n===================================================" -ForegroundColor Cyan
Write-Host " CogniGuard Demo Environment Setup" -ForegroundColor Cyan
Write-Host "===================================================`n" -ForegroundColor Cyan

# 1. Docker health
Write-Host "[1/4] Checking Docker containers..." -ForegroundColor Yellow
$containers = docker compose ps --format "table {{.Name}}`t{{.Status}}" 2>&1
Write-Host $containers

# 2. Gateway health
Write-Host "`n[2/4] Gateway health check..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
    if ($response.status -eq "ok") {
        Write-Host "  [OK] Gateway healthy: db=$($response.db) redis=$($response.redis) kafka=$($response.kafka)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Gateway not fully healthy: $($response | ConvertTo-Json -Compress)" -ForegroundColor Red
    }
} catch {
    Write-Host "  [ERROR] Gateway unreachable: $_" -ForegroundColor Red
    Write-Host "  Hint: Run 'docker compose up -d' first" -ForegroundColor Gray
}

# 3. ADB device + reverse tunnels
Write-Host "`n[3/4] ADB device check + reverse tunnels..." -ForegroundColor Yellow
$devices = adb devices 2>&1
Write-Host $devices

Write-Host "  Setting up adb reverse tunnels..." -ForegroundColor Gray

$r8000 = adb -s $device reverse tcp:8000 tcp:8000 2>&1
Write-Host "  tcp:8000 (gateway): $r8000" -ForegroundColor $(if ($r8000 -match "8000") {"Green"} else {"Red"})

$r5174 = adb -s $device reverse tcp:5174 tcp:5174 2>&1
Write-Host "  tcp:5174 (SOC dashboard): $r5174" -ForegroundColor $(if ($r5174 -match "5174") {"Green"} else {"Red"})

$r5173 = adb -s $device reverse tcp:5173 tcp:5173 2>&1
Write-Host "  tcp:5173 (web app): $r5173" -ForegroundColor $(if ($r5173 -match "5173") {"Green"} else {"Red"})

Write-Host "`n  Active tunnels:" -ForegroundColor Gray
adb -s $device reverse --list 2>&1

# 4. Test gateway reachability from device
Write-Host "`n[4/4] Testing gateway reachability via adb..." -ForegroundColor Yellow
$healthCheck = adb -s $device shell "curl -s --connect-timeout 5 http://127.0.0.1:8000/health 2>&1"
if ($healthCheck -match '"status":"ok"') {
    Write-Host "  [OK] Device can reach gateway at http://127.0.0.1:8000" -ForegroundColor Green
} elseif ($healthCheck -match "not found" -or $healthCheck -eq "") {
    $wgetCheck = adb -s $device shell "wget -qO- --timeout=5 http://127.0.0.1:8000/health 2>&1"
    if ($wgetCheck -match '"status":"ok"') {
        Write-Host "  [OK] Device can reach gateway (wget test)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Cannot verify device connectivity directly, but tunnel is set up." -ForegroundColor Yellow
        Write-Host "     Build and run the app to test live." -ForegroundColor Gray
    }
} else {
    Write-Host "  [ERROR] Device cannot reach gateway: $healthCheck" -ForegroundColor Red
}

# Summary
Write-Host "`n===================================================" -ForegroundColor Cyan
Write-Host " Setup Complete - Demo Checklist" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Gateway:       http://localhost:8000" -ForegroundColor White
Write-Host " SOC Dashboard: http://localhost:5174" -ForegroundColor White
Write-Host " Web App:       http://localhost:5173" -ForegroundColor White
Write-Host " Android API:   http://127.0.0.1:8000 (via adb reverse)" -ForegroundColor White
Write-Host "`n Risk Matrix:" -ForegroundColor White
Write-Host "   Low Risk    -> Direct Allow (no re-auth)" -ForegroundColor Green
Write-Host "   Medium Risk -> OTP screen (enter 123456)" -ForegroundColor Yellow
Write-Host "   High Risk   -> OTP -> Fingerprint (2-step)" -ForegroundColor DarkYellow
Write-Host "   Very High   -> Block" -ForegroundColor Red
Write-Host "`n NOTE: adb reverse tunnels reset on USB disconnect." -ForegroundColor Gray
Write-Host "       Re-run this script if the phone is unplugged.`n" -ForegroundColor Gray
