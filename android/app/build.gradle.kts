plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.cogniguard.demoapp"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.cogniguard.demoapp"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        getByName("debug") {
            // 127.0.0.1 here relies on `adb reverse tcp:8000 tcp:8000` tunneling the
            // physical device's loopback port 8000 back to the host's gateway -- swap
            // for 10.0.2.2 (the emulator's host-loopback alias) if using the emulator.
            buildConfigField("String", "API_BASE", "\"http://127.0.0.1:8000\"")
            // Dev-only demo value mirroring the gateway's JWT_SECRET (same
            // simplification web-app/src/pages/Login.tsx's SIGNING_SECRET already
            // makes -- see that file's comment).
            buildConfigField("String", "SIGNING_SECRET", "\"change_me_dev_only_super_secret\"")
        }
    }
    buildFeatures {
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
}

dependencies {
    implementation(project(":capture-sdk"))
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    // Material widgets (cards/buttons/chips) for the production-banking look (Phase 31 reskin).
    implementation("com.google.android.material:material:1.11.0")
    // Real device biometric step-up (FINGERPRINT/FACE) for the `verify` action (Phase 24).
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
