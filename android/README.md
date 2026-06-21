# CogniGuard Android (Phase 18)

Native Kotlin capture SDK (`capture-sdk/`) + demo Internet Banking app (`app/`), parity
with `web-app/` and `behavior-sdk/`. See `Implementation.md`'s Phase 18 section for the
full file-by-file spec, and `gateway/tests/fixtures/golden_canonical_mobile.json` for
the cross-language signing fixture this module's `CanonicalTest`/`SignerTest` pin
against.

## One-time setup

This module was written and reviewed without Android SDK/Gradle/an emulator available
in the authoring environment, so it has **not** been compiled or run here. Before
building:

```bash
cd android
gradle wrapper --gradle-version 8.4   # generates gradlew/gradlew.bat + the wrapper jar
```

You'll need:
- Android SDK with `compileSdk 34` / `minSdk 26` platform installed (`ANDROID_HOME` set).
- A copy of Phase 16's trained artifact at `capture-sdk/src/main/assets/model.tflite`
  (gitignored, same "tracked in S3/the model registry, not git" policy as `models/`):
  ```bash
  cp ../models/lstm_autoencoder_tflite/lstm_autoencoder@<version>/model.tflite \
     capture-sdk/src/main/assets/model.tflite
  ```
- An emulator/device for `./gradlew :capture-sdk:connectedAndroidTest`.
- The gateway running (`docker compose up gateway`) reachable at `10.0.2.2:8000` from
  an emulator (the standard host-loopback alias) -- override via `app`'s
  `BuildConfig.API_BASE` for a physical device on the same network.

## Build & test

```bash
./gradlew :capture-sdk:connectedAndroidTest
./gradlew :app:assembleDebug
```
