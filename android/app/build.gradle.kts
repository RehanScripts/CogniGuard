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
            // Use the PC's Wi-Fi IP directly to avoid dropping ADB reverse tunnels
            buildConfigField("String", "API_BASE", "\"http://10.22.36.33:8000\"")
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
    // CameraX for dummy face-auth preview (very_high risk, no capture/storage).
    val cameraxVersion = "1.3.1"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")
}
