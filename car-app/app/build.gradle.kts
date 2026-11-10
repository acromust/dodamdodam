plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ai.simeodum.car"
    compileSdk = 35
    useLibrary("android.car")

    defaultConfig {
        applicationId = "ai.simeodum.car"
        minSdk = 28
        targetSdk = 34
        versionCode = 2
        versionName = "1.0.0"
        // 차가 붙는 서버. 기본은 맥 서버(에뮬레이터에서 10.0.2.2), 클라우드에 올리면 그 https 주소(-PapiBase=...)
        val apiBase = (project.findProperty("apiBase") as String?) ?: "http://10.0.2.2:8090"
        buildConfigField("String", "API_BASE", "\"$apiBase\"")
        // 가족 폰에 보낼 초대 링크 주소. 서버를 밖에 열면 그 https 주소로(-PshareBase=...), 'same'이면 차가 붙는 서버 주소 그대로
        val shareBase = ((project.findProperty("shareBase") as String?) ?: "http://localhost:8090").let { if (it == "same") apiBase else it }
        buildConfigField("String", "SHARE_BASE", "\"$shareBase\"")
        // 클라우드 서버의 차 주소를 여는 열쇠(-PcarKey=...). 저장소에 적지 않고 빌드할 때만 넣는다
        buildConfigField("String", "CAR_KEY", "\"${(project.findProperty("carKey") as String?) ?: ""}\"")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
    buildTypes {
        // 개발 빌드만 http(맥 서버 10.0.2.2·사설망 주소)에 붙는다. release는 https만(AndroidManifest usesCleartextTraffic)
        getByName("debug") { manifestPlaceholders["cleartext"] = "true" }
        getByName("release") {
            manifestPlaceholders["cleartext"] = "false"
            // 공모전 제출용: 스토어에 안 올리므로 개발 서명으로 설치 가능한 release를 만든다(정식 배포 땐 배포용 키로 바꾼다)
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    lint { checkReleaseBuilds = false }   // 오프라인 빌드에서 린트 도구를 받을 수 없다
    androidResources { noCompress.add("glb") }   // 광장 장면 파일은 압축하지 않고 넣는다(읽을 때 풀지 않게)
}

// release인데 서버 주소가 http면 차가 서버에 못 붙는다(release는 http를 막음): 빌드할 때 알려 준다
gradle.taskGraph.whenReady {
    val api = (project.findProperty("apiBase") as String?) ?: "http://10.0.2.2:8090"
    if (allTasks.any { it.name.contains("Release") } && !api.startsWith("https://"))
        logger.warn("경고: release 빌드는 http 서버에 붙지 않습니다(-PapiBase=$api). 서버 없이 체험용 예시 메시지로만 돕니다.")
}

dependencies {
    implementation("ai.pleos.playground:Vehicle:2.3.2")
    implementation("ai.pleos.playground:NaviHelper:3.0.5")
    implementation("ai.pleos.playground:FusedLocation:1.1.3")
    implementation("com.google.zxing:core:3.5.3") // 초대 QR 그리기(인터넷 없이 차에서 바로)
    // 차 홈 광장(3D 더미). simeodum 시험 빌드(debug)에서 실측 통과한 버전 그대로 main으로
    implementation("com.google.android.filament:filament-android:1.57.1")
    implementation("com.google.android.filament:gltfio-android:1.57.1")
    implementation("com.google.android.filament:filament-utils-android:1.57.1")
}
