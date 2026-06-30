# Android Setup

The native Kotlin Android app (Central Bank of India) runs the **LSTM Autoencoder on-device**
via TensorFlow Lite — only the reconstruction error leaves the device, never raw biometrics.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Android Studio | Hedgehog (2023.1.1) or later |
| Android SDK | `compileSdk 34`, `minSdk 26` (API 26+) |
| `ANDROID_HOME` | set to your SDK path |
| ADB | any (bundled with Android Studio) |
| Java | 17 (bundled with Android Studio) |

---

## 1. Copy the TFLite Model

The model file is gitignored (tracked in S3). Copy it from the local model mirror:

```bash
cp models/lstm_autoencoder_tflite/lstm_autoencoder@<version>/model.tflite \
   android/capture-sdk/src/main/assets/model.tflite
```

If the `models/` mirror is empty (fresh clone), train it first:

```bash
make train
# or manually:
docker compose exec gateway python -m training.train_lstm_autoencoder
```

Then copy the artifact from the version directory that just appeared in `models/lstm_autoencoder_tflite/`.

---

## 2. Build the Debug APK

```bash
cd android
./gradlew :app:assembleDebug
```

Output: `android/app/build/outputs/apk/debug/app-debug.apk`

---

## 3. Install on Device / Emulator

```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 4. Connect to the Gateway

### Emulator
The emulator maps host `localhost` to `10.0.2.2`. The app is pre-configured for this — no extra steps.

### Physical Device (ADB reverse tunnel)
Run the provided setup script from a PowerShell terminal:

```powershell
.\setup-demo.ps1
```

Or set up tunnels manually (replace `<serial>` with your device serial from `adb devices`):

```bash
adb -s <serial> reverse tcp:8000 tcp:8000   # gateway
adb -s <serial> reverse tcp:5173 tcp:5173   # web app (optional)
adb -s <serial> reverse tcp:5174 tcp:5174   # SOC dashboard (optional)
```

> Tunnels reset on USB disconnect. Re-run the script if the phone is unplugged.

---

## 5. Run Instrumented Tests

Requires a connected device or running emulator:

```bash
cd android
./gradlew :capture-sdk:connectedAndroidTest
```

This runs:
- `CanonicalTest` — verifies HMAC canonicalization matches the Python/TS golden vector
- `SignerTest` — end-to-end signing round-trip

---

## Behavioral Capture (Kotlin SDK)

`android/capture-sdk/` mirrors `behavior-sdk/` (TypeScript) exactly:

| Feature | Implementation |
|---------|---------------|
| Keystroke dynamics | `KeystrokeCapture.kt` — dwell / flight timing |
| Touch dynamics | `TouchCapture.kt` — pressure, area, velocity |
| On-device AE | `AutoencoderTFLite.kt` — TFLite model inference |
| HMAC signing | `Signer.kt` — HMAC-SHA256 matching Python canonical |
| API client | `CogniGuardClient.kt` — login, score-payment, step-up |

The `ae_recon_error` computed on-device is sent in the payload instead of raw sensor streams.
