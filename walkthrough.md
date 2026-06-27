# Walkthrough: End-to-End Connectivity Fix

## Root Causes Identified
The Android app's "Couldn't connect to server" error was caused by a combination of issues when running on a physical Android 16 device:

1. **ADB Reverse Tunnel Missing**: The app was configured to reach the API at `http://127.0.0.1:8000`. On a physical device, `127.0.0.1` points to the phone itself, not the host machine. A reverse tunnel (`adb reverse tcp:8000 tcp:8000`) is required but wasn't active.
2. **Missing Network Security Config**: Even with `usesCleartextTraffic="true"` in the manifest, modern Android (API 28+) strict security policies sometimes block cleartext HTTP to loopback addresses unless explicitly whitelisted in a network security config.
3. **Infinite Hang on Failure**: `CogniGuardClient` lacked connection and read timeouts. When the tunnel was missing, requests hung indefinitely instead of failing fast, obscuring the root cause.

## Fixes Implemented

### 1. Fast-Fail Timeouts
Added timeouts to `CogniGuardClient.kt` so the app immediately reports connectivity issues rather than hanging:
```kotlin
conn.connectTimeout = 15_000   // 15 s – fail fast if adb reverse not set
conn.readTimeout    = 30_000   // 30 s – allow scoring pipeline latency
conn.setRequestProperty("User-Agent", "CogniGuard-Android/1.0")
```

### 2. Explicit Cleartext Allowlist
Created `network_security_config.xml` and referenced it in the `AndroidManifest.xml` to explicitly permit HTTP traffic to development loopback addresses:
```xml
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">127.0.0.1</domain>
        <domain includeSubdomains="false">10.0.2.2</domain>
        <domain includeSubdomains="false">localhost</domain>
    </domain-config>
</network-security-config>
```

### 3. Demo Setup Automation
Created a `setup-demo.ps1` PowerShell script at the root of the project to automate the environment preparation. 

Because the AI agent environment repeatedly restarts the ADB daemon (which drops reverse tunnels), **you must run this script from your local terminal to establish a stable connection**.

---

## Next Steps for the Demo

To test the full end-to-end flow and perform your screen recording:

1. **Run the setup script** from your own local PowerShell terminal to establish the tunnels:
   ```powershell
   .\setup-demo.ps1
   ```
2. **Open the App** on your phone (I have already built and installed the updated APK for you).
3. **Test the flows**:
   - **Low Risk**: Login normally → Direct Allow (Dashboard).
   - **Medium Risk**: Triggered by slight behavioral deviations → OTP Screen appears.
   - **High Risk**: Triggered by strong anomalies (e.g. emulator flag or mismatched IP) → OTP → Biometric flow.
4. **View SOC Dashboard**: Open `http://localhost:5174` on your PC to see the live `STEP_UP_REQUIRED` and `BIOMETRIC_SUCCESS` events as you test.
