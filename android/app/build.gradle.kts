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
            // 10.0.2.2 is the Android emulator's host-loopback alias -- override for a
            // physical device on the same network as `docker compose up gateway`.
            buildConfigField("String", "API_BASE", "\"http://10.0.2.2:8000\"")
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
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
}
