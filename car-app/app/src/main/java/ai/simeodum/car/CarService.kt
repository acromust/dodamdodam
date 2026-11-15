package ai.simeodum.car

import ai.pleos.playground.vehicle.Vehicle
import ai.pleos.playground.vehicle.api.model.area.WindowArea
import ai.pleos.playground.vehicle.constant.area.WindowValue
import ai.pleos.playground.vehicle.constant.control.VehicleGear
import ai.pleos.playground.vehicle.constant.control.WiperState
import ai.pleos.playground.vehicle.listener.GearSelectionListener
import ai.pleos.playground.vehicle.listener.SteeringWheelAngleListener
import ai.pleos.playground.vehicle.listener.WiperStateListener
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import java.time.LocalDate
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * 차가 켜지면 뒤에서 대기한다. 운전자는 앱을 켤 필요가 없다.
 * 순간(출발·도착·집 근처·비·배터리 부족)을 판단 → 안전 타이밍을 기다림 → 운전자가 고른 듣는 방식대로 들려준다.
 * 버튼 듣기(기본): 띵동 + 녹음 안내("음성 메시지가 도착했습니다.") → 8초 안에 핸들 가운데 버튼·알림 [듣기]면 재생, 아니면 도착해서.
 * 주행 중엔 소리만. 못 들은 메시지는 도착(P)해서 소리로, 다시 듣기·답장은 정차 중 앱 화면에서.
 */
class CarService : Service() {

    companion object {
        // 시연(맥 서버 개발 빌드·시연 도구 스위치·체험 메시지)에서만 줄이고, 그 밖에는 제품 값.
        // 클라우드 서버로 빌드한 심사용 APK는 개발 빌드여도 제품 값으로 돈다
        private val SHORT get() = Hub.shortTimes || Hub.demo
        const val RAIN_HOLD_MS = 10_000L       // 와이퍼 유지
        val ARRIVE_MIN_DRIVE_MS get() = if (SHORT) 15_000L else 180_000L // 주차로 볼 최소 주행
        const val STEER_CALM_DEG = 30f         // 직진으로 볼 조향각
        const val STEER_CALM_MS = 3_000L       // 직진 유지
        const val PREROLL_MS = 150L            // 음성 앞 묵음
        // 주행 중 하루 5개 상한은 11/09 사용자 결정으로 뺐다. 메시지 사이 1분 간격도 11/11 사용자 결정으로 뺐다(설명이 안 됨). 주의 분산은 메시지 길이 5초 제한(서버 max_sec)과 바쁜 순간 기다리기(roadReason)·핸들 버튼 선택으로 막는다
        const val STEER_WAIT_MS = 3_000L       // 핸들 각도 신호를 이만큼 못 받으면 주행 중에는 틀지 않고 주차해서(11/09 결정)
        const val MIN_SPEED_KPH = 15f          // 이 속도를 한 번 넘기면 주차장을 벗어난 것으로 본다
        const val LISTEN_WINDOW_MS = 8_000L    // 버튼 듣기: 안내가 끝난 뒤 기다리는 시간
        const val BATTERY_LOW_PCT = 15         // 배터리·기름 부족으로 볼 잔량
        const val HOME_RADIUS_M = 500f         // 집·장소 근처 반경
        val LIST_REFRESH_MS get() = if (SHORT) 30_000L else 300_000L // 주행 중에도 목록을 다시 받는 간격(새로 남긴 것·지운 것 반영)
        val AWAY_MIN_MS get() = if (SHORT) 20_000L else 180_000L // 반경을 나간 뒤 이만큼은 떠나 있어야 다시 들어온 걸로 본다
        val LONG_DRIVE_MS get() = if (SHORT) 30_000L else 7_200_000L // 오래 달렸을 때: P 없이 2시간
        const val TURN_CALM_MS = 3_000L        // 방향지시등이 꺼진 뒤 기다리는 시간
        const val PULL_AWAY_MS = 5_000L        // 서 있다가 출발한 직후 새로 시작하지 않는 시간(C10)
        const val MAX_CUTS = 2                 // 다른 소리(내비 안내 등)에 이만큼 끊기면 주차 후로 미룬다(C10)
        // 내비에 '집'이 없을 때 쓰는 시연용 집 좌표(에뮬레이터 기본 위치 근처)
        const val DEMO_HOME_LAT = 37.4127
        const val DEMO_HOME_LON = 127.0947
    }

    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private lateinit var nm: NotificationManager
    private lateinit var am: AudioManager
    private var vehicle: Vehicle? = null
    private var wheel: WheelWindow? = null
    // 배터리(전기차)와 기름(내연기관)은 따로 둔다: 한쪽 값이 다른 쪽을 덮으면 부족 순간을 잘못 잡는다
    private var evPct: Int? = null
    private var fuelPct: Int? = null
    private var turnOn = false            // 방향지시등 켜짐
    private var turnOffAt = 0L
    /** 오래 달렸을 때: P 없이 정해진 시간을 달리면 온다. 졸음 운전을 깨우는 순간. */
    private val listRefresh = object : Runnable {
        override fun run() { refresh { catchUpMoments() }; main.postDelayed(this, LIST_REFRESH_MS) }
    }
    /** 서버에 붙어 기다리다 바뀐 게 생기면 바로 목록을 다시 받는다. 위의 주기 갱신은 이게 끊겼을 때를 위한 대비. */
    @Volatile private var watching = true
    private val changeWatch = Thread {
        var since = -1L
        while (watching) {
            val v = runCatching { Api.waitChange(since) }.getOrNull()
            if (v == null) { runCatching { Thread.sleep(5_000) }; continue }
            if (since != -1L && v != since) main.post { Hub.log("새로 남긴 것·바뀐 것 있음 → 바로 받기"); refresh { catchUpMoments() } }
            // 체험·오프라인으로 기다리던 중에 서버가 깨어나 답하면 바로 진짜 목록으로 바꾼다
            else if (Hub.demo || Hub.offline) main.post { Hub.log("서버가 답함 → 바로 받기"); refresh { catchUpMoments() } }
            since = v
        }
    }.apply { isDaemon = true; name = "change-watch" }
    private val longDrive = Runnable { if (inTrip && Hub.enabled(this)) momentCame("long", "오래 달렸습니다.") }
    private var navi: ai.pleos.playground.navi.helper.NaviHelper? = null
    private var location: ai.pleos.playground.location.fused.FusedLocation? = null
    private var homeAlertId: String? = null
    private val placeAlerts = mutableMapOf<String, String>() // 메시지 id → 반경 알림 id
    private val deferredThisTrip = mutableSetOf<String>() // 버튼 듣기에서 대답 없어 도착으로 넘긴 것(이번 주행엔 다시 안 물음)
    private var asking: Hidden? = null                     // 버튼 듣기로 대답을 기다리는 메시지
    private val onEmulator = android.os.Build.HARDWARE == "ranchu" || android.os.Build.HARDWARE == "goldfish"
    private var annDone: (() -> Unit)? = null   // 녹음 안내가 끝나면 할 일
    private var screenOff: android.content.BroadcastReceiver? = null
    private var netWatch: android.net.ConnectivityManager.NetworkCallback? = null
    private var car: android.car.Car? = null
    private var speedWatch: android.car.hardware.property.CarPropertyManager.CarPropertyEventCallback? = null
    private var homeSource: String? = null      // 지금 집 반경 알림이 어디서 온 좌표인지(navi·demo·test). null이면 안 건 것
    private var homeTarget: Pair<Double, Double>? = null
    private var lastSender: String? = null      // 마지막으로 들려준 사람(같은 순간 여러 개면 다른 사람 것부터)
    private val heardThisTrip = mutableSetOf<String>() // 이번 운행에서 새로 들은 것(주차 알림을 띄울지)
    private var parkedOffer: String? = null     // 출발 전(P)에 알리는 중인 차 탈 때 메시지

    /** 재생 흐름의 예약(띵동→안내·이어 듣기·다시 시도). 시동 끔·주차·앱 닫음 때 한꺼번에 지워서 꺼진 뒤 소리가 나지 않게. */
    private val playToken = Any()
    private fun later(ms: Long, r: () -> Unit) { main.postAtTime(Runnable { r() }, playToken, SystemClock.uptimeMillis() + ms) }
    private fun cancelLater() = main.removeCallbacksAndMessages(playToken)
    /** 뒤 스레드 일. 서비스가 끝나 일꾼을 닫은 뒤에 늦게 온 일은 버린다(거절 예외로 죽지 않게). */
    private fun bg(r: () -> Unit) { runCatching { io.execute(r) } }

    private var gear: VehicleGear? = null
    private var drivingSince = 0L
    private var inTrip = false
    private var wiperOnAt = 0L
    private var rainFiredThisTrip = false
    private var steerAngle = 0f
    private var speedKph = 0f
    private var leftLot = false             // 이번 운행에서 주차장을 벗어났는가. 그 뒤로는 신호 대기·정체에서도 재생한다
    private var steerCalmSince = SystemClock.elapsedRealtime()
    private var steerSeen = false           // 핸들 각도를 한 번이라도 받았는가(못 받으면 주행 중 재생을 미룬다)
    private var lastPlayAt = 0L
    private var playing = false
    private var current: Hidden? = null // 주행 중 재생하다 끊긴 메시지를 되돌리기 위해

    private val queue = ArrayDeque<Hidden>()
    private val drivePlayed = mutableListOf<Pair<String, String>>() // (날짜, id)
    private fun drivePlaysToday() = drivePlayed.count { it.first == LocalDate.now().toString() }
    /** 하루 5개 제한은 앱이 다시 떠도 이어지게 기기에 남긴다(날짜와 함께). */
    private fun saveDrivePlayed() {
        val today = LocalDate.now().toString()
        getSharedPreferences("sim", MODE_PRIVATE).edit().putString("playedDay", today)
            .putStringSet("playedIds", drivePlayed.filter { it.first == today }.map { it.second }.toSet()).apply()
    }
    private fun loadDrivePlayed() {
        val p = getSharedPreferences("sim", MODE_PRIVATE)
        val today = LocalDate.now().toString()
        if (p.getString("playedDay", null) == today) p.getStringSet("playedIds", emptySet())!!.forEach { drivePlayed += today to it }
    }
    private var waitingLogged = false

    override fun onCreate() {
        super.onCreate()
        Hub.service = this
        Api.init(this)
        Hub.shortTimes = getSharedPreferences("sim", MODE_PRIVATE).getBoolean("shortTimes", BuildConfig.DEBUG && Api.BASE.contains("10.0.2.2"))
        loadDrivePlayed()
        nm = getSystemService(NotificationManager::class.java)
        am = getSystemService(AudioManager::class.java)
        // 채널 이름(63번 4장, 75번 A-2): 음성 메시지 개수 · 듣기 알림(같은 id로 다시 만들면 이름만 바뀐다)
        nm.createNotificationChannel(NotificationChannel("wait", "음성 메시지 개수", NotificationManager.IMPORTANCE_MIN))
        nm.createNotificationChannel(NotificationChannel("reply", "들은 메시지", NotificationManager.IMPORTANCE_LOW))
        // 버튼 듣기 카드: 화면 위에 잠깐 뜨는 알림(소리는 우리 띵동으로 내므로 알림 소리는 끈다)
        nm.createNotificationChannel(NotificationChannel("ask", "듣기 알림", NotificationManager.IMPORTANCE_HIGH).apply { setSound(null, null) })
        // 재생 중 알림 줄(멈추기): 화면 위에 뜨지 않고 알림 줄에만
        nm.createNotificationChannel(NotificationChannel("playing", "재생 중", NotificationManager.IMPORTANCE_LOW).apply { setSound(null, null) })
        startForeground(1, waitNotification(null), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        Hub.log("뒤에서 대기 시작")
        startVehicle()
        refresh()
        main.postDelayed(listRefresh, LIST_REFRESH_MS)
        changeWatch.start()
        // 시동 끔(절전) 직전엔 화면이 꺼진다: 재생을 멈추고 소리 권한을 반납한다(가이드 필수). 일반 앱은 차 전원 상태 권한이 없어 화면 꺼짐으로 대신한다.
        screenOff = object : android.content.BroadcastReceiver() {
            override fun onReceive(c: android.content.Context, i: Intent) { main.post { onPowerDown() } }
        }.also { registerReceiver(it, android.content.IntentFilter(Intent.ACTION_SCREEN_OFF)) }
        // 차가 켜질 때 네트워크가 늦게 잡혀도, 연결되면 다시 받는다
        runCatching {
            val cb = object : android.net.ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: android.net.Network) { main.post { Hub.log("네트워크 연결됨 → 다시 받기"); refresh() } }
                override fun onLost(network: android.net.Network) { main.post { Hub.offline = true; Hub.changed() } }
            }
            getSystemService(android.net.ConnectivityManager::class.java).registerDefaultNetworkCallback(cb)
            netWatch = cb
        }.onFailure { Hub.log("네트워크 감시 불가: $it") }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // 케이스 테스트용 명령 (adb shell am start-foreground-service ... --es cmd ...)
        when (intent?.getStringExtra("cmd")) {
            "close" -> quietUntilNextDrive()
            "weather" -> {
                // 광장 날씨 시험: --es value rain|snow|clear|night|day|off (off = 실제 신호대로)
                Hub.weatherTest = intent.getStringExtra("value")?.takeIf { it != "off" }
                Hub.log("[테스트] 광장 날씨 → ${Hub.weatherTest ?: "실제 신호"}")
            }
            "plaza" -> {
                // 광장 사람 행동 시험: --es value doze|drink|yawn|stretch|wave|read|stroll|visit|face2|lookup|lookat|turn|greet
                Hub.plazaTest = intent.getStringExtra("value")
                Hub.log("[테스트] 광장 행동 → ${Hub.plazaTest}")
            }
            "play_url" -> {
                val path = intent.getStringExtra("path") ?: return START_STICKY
                Hub.log("[테스트] 재생: $path")
                playAudio(Hidden("test", "테스트", "start", path, false, false)) { Hub.log("[테스트] 재생 끝: $path") }
            }
            "gain" -> {
                focusGain = if (intent.getStringExtra("value") == "transient") AudioManager.AUDIOFOCUS_GAIN_TRANSIENT else AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK
                focus = buildFocus()
                Hub.log("[테스트] 포커스 방식: ${if (focusGain == AudioManager.AUDIOFOCUS_GAIN_TRANSIENT) "잠깐 멈추기" else "덕킹"}")
            }
            "reset_day" -> {
                Hub.setLastStart(this, null); Hub.opened.clear(); Hub.heard.clear(); queue.clear(); lastPlayAt = 0L; arriveReady.clear(); Hub.occurredThisTrip.clear()
                drivePlayed.clear(); saveDrivePlayed()   // 시연을 여러 번 해도 하루 5개 상한에 걸리지 않게
                refresh(); Hub.log("[테스트] 오늘 첫 출발 상태로 초기화")
            }
            "sigtest" -> {
                // 아직 안 쓰는 신호 실측: 뒷좌석·조수석 착석, 운전석 열선, 핸들 열선
                val v = vehicle ?: return START_STICKY
                listOf(ai.pleos.playground.vehicle.constant.area.SeatValue.ROW_1_RIGHT, ai.pleos.playground.vehicle.constant.area.SeatValue.ROW_2_LEFT,
                    ai.pleos.playground.vehicle.constant.area.SeatValue.ROW_2_RIGHT).forEach { sv ->
                    runCatching {
                        v.getSeat().registerSeatOccupancy(ai.pleos.playground.vehicle.api.model.area.SeatArea(sv), object : ai.pleos.playground.vehicle.listener.SeatOccupancyListener {
                            override fun onSeatOccupancyUpdated(value: Boolean?) { main.post { Hub.log("[테스트] 착석 $sv → $value") } }
                            override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 착석 $sv 구독 실패: $e") } }
                        })
                    }.onFailure { Hub.log("[테스트] 착석 $sv 불가: $it") }
                }
                runCatching {
                    v.getSeat().registerHvacSeatTemperature(ai.pleos.playground.vehicle.api.model.area.SeatArea(ai.pleos.playground.vehicle.constant.area.SeatValue.ROW_1_LEFT), object : ai.pleos.playground.vehicle.listener.HvacSeatTemperatureListener {
                        override fun onHvacSeatTemperatureUpdated(value: Int?) { main.post { Hub.log("[테스트] 운전석 열선/통풍 → $value") } }
                        override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 운전석 열선 구독 실패: $e") } }
                    })
                }.onFailure { Hub.log("[테스트] 운전석 열선 불가: $it") }
                runCatching {
                    v.getSteeringWheel().registerHvacSteeringWheelHeatState(object : ai.pleos.playground.vehicle.listener.HvacSteeringWheelHeatStateListener {
                        override fun onHvacSteeringWheelHeatStateUpdated(value: Int?) { main.post { Hub.log("[테스트] 핸들 열선 → $value") } }
                        override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 핸들 열선 구독 실패: $e") } }
                    })
                }.onFailure { Hub.log("[테스트] 핸들 열선 불가: $it") }
            }
            "loctest" -> {
                // 집 근처 순간 실측: 위치 받기 + 반경 진입/이탈 알림(Pleos FusedLocation)
                val lat = intent.getStringExtra("lat")?.toDouble() ?: 37.4127; val lon = intent.getStringExtra("lon")?.toDouble() ?: 127.0947
                val radius = intent.getStringExtra("r")?.toFloat() ?: 300f
                val f = ai.pleos.playground.location.fused.FusedLocation(this)
                Hub.log("[테스트] 위치 SDK 지원: ${runCatching { f.isSupported() }.getOrElse { "예외 $it" }}")
                runCatching { f.initialize() }.onFailure { Hub.log("[테스트] 위치 초기화 실패: $it") }
                main.postDelayed({
                    runCatching {
                        f.registerFusedLocationCallback(object : ai.pleos.playground.location.fused.listener.FusedLocationListener {
                            override fun onChanged(d: ai.pleos.playground.location.fused.model.LocationData?) { main.post { Hub.log("[테스트] 위치 ${d?.let { "%.5f, %.5f".format(it.latitude, it.longitude) } ?: "없음"}") } }
                            override fun onError(e: Exception) { main.post { Hub.log("[테스트] 위치 오류: $e") } }
                        })
                    }.onFailure { Hub.log("[테스트] 위치 구독 실패: $it") }
                    runCatching {
                        f.addProximityAlert(ai.pleos.playground.location.fused.model.ProximityAlertRequest(lat, lon, radius,
                            setOf(ai.pleos.playground.location.fused.model.ProximityTransition.ENTER, ai.pleos.playground.location.fused.model.ProximityTransition.EXIT)),
                            object : ai.pleos.playground.location.fused.listener.ProximityAlertListener {
                                override fun onRegistered(id: String) { main.post { Hub.log("[테스트] 집 반경 ${radius.toInt()}m 등록 ($lat,$lon)") } }
                                override fun onTransition(e: ai.pleos.playground.location.fused.model.ProximityAlertEvent) { main.post { Hub.log("[테스트] 집 반경 → ${e.transition}") } }
                                override fun onError(e: Exception) { main.post { Hub.log("[테스트] 반경 알림 오류: $e") } }
                            })
                    }.onFailure { Hub.log("[테스트] 반경 알림 등록 실패: $it") }
                }, 1500)
            }
            "locstress" -> {
                // 반경 알림을 몇 개까지 걸 수 있는지 실측. 등록 성공·오류 수만 세고 바로 푼다.
                val n = intent.getStringExtra("n")?.toInt() ?: 100
                val f = location ?: ai.pleos.playground.location.fused.FusedLocation(this).also { it.initialize(); location = it }
                var ok = 0; var bad = 0; val ids = mutableListOf<String>()
                repeat(n) { i ->
                    runCatching {
                        f.addProximityAlert(ai.pleos.playground.location.fused.model.ProximityAlertRequest(37.0 + i * 0.01, 127.0, 300f,
                            setOf(ai.pleos.playground.location.fused.model.ProximityTransition.ENTER)),
                            object : ai.pleos.playground.location.fused.listener.ProximityAlertListener {
                                override fun onRegistered(id: String) { main.post { ok++; ids += id } }
                                override fun onTransition(e: ai.pleos.playground.location.fused.model.ProximityAlertEvent) {}
                                override fun onError(e: Exception) { main.post { bad++; if (bad == 1) Hub.log("[테스트] 첫 오류: $e") } }
                            })
                    }.onFailure { bad++; if (bad == 1) Hub.log("[테스트] 첫 예외: $it") }
                }
                main.postDelayed({ Hub.log("[테스트] 반경 알림 $n 요청: 성공 $ok, 실패 $bad"); ids.forEach { runCatching { f.removeProximityAlert(it) } } }, 8000)
            }
            "holdfocus" -> {
                val sec = intent.getStringExtra("sec")?.toLong() ?: 30L
                val r = am.requestAudioFocus(focus)
                Hub.log("[테스트] ${sec}초 동안 포커스 잡기: ${if (r == AudioManager.AUDIOFOCUS_REQUEST_GRANTED) "받음" else r} · 지금 소리 ${otherSounds()}")
                main.postDelayed({ am.abandonAudioFocusRequest(focus); Hub.log("[테스트] 포커스 반납 · 지금 소리 ${otherSounds()}") }, sec * 1000)
            }
            "configs" -> Hub.log("[테스트] 지금 재생 중인 소리: ${otherSounds().ifEmpty { listOf("없음") }}")
            "energytest" -> {
                // 실용 순간 후보 실측: 배터리 잔량(%), 충전구 열림, 전조등(로우빔)
                val v = vehicle ?: return START_STICKY
                runCatching {
                    v.getEvBattery().registerEvBatteryStateOfCharge(object : ai.pleos.playground.vehicle.listener.EvBatteryStateOfChargeListener {
                        override fun onEvBatteryStateOfChargeUpdated(value: Int?) { main.post { Hub.log("[테스트] 배터리 잔량 → $value%") } }
                        override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 배터리 잔량 구독 실패: $e") } }
                    })
                }.onFailure { Hub.log("[테스트] 배터리 잔량 불가: $it") }
                runCatching {
                    v.getEvBattery().registerEvChargePortOpen(object : ai.pleos.playground.vehicle.listener.EvChargePortOpenListener {
                        override fun onEvChargePortOpenUpdated(value: Boolean?) { main.post { Hub.log("[테스트] 충전구 열림 → $value") } }
                        override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 충전구 구독 실패: $e") } }
                    })
                }.onFailure { Hub.log("[테스트] 충전구 불가: $it") }
                runCatching {
                    v.getLight().registerLowBeamLightState(object : ai.pleos.playground.vehicle.listener.LightStateListener {
                        override fun onLightStateUpdated(value: ai.pleos.playground.vehicle.constant.control.LightState?) { main.post { Hub.log("[테스트] 전조등 → $value") } }
                        override fun onFailed(e: Exception) { main.post { Hub.log("[테스트] 전조등 구독 실패: $e") } }
                    })
                }.onFailure { Hub.log("[테스트] 전조등 불가: $it") }
            }
            "wheel" -> {
                val w = wheel()
                if (intent.getStringExtra("sound") == "close") w.close("명령") else {
                    w.open { key -> Hub.log("[테스트] 핸들 버튼 받음: $key → 듣기") }
                    w.closeAfter((intent.getStringExtra("sec")?.toLong() ?: 8L) * 1000) { Hub.log("[테스트] 대답 없음") }
                }
            }
            // 주차 목록 시험: list(목록을 기록에 한 줄로) · listplay(--es value 순번, 없으면 모두 듣기)
            "list" -> Hub.log("[테스트] 주차 목록 ${parkList().size}개: " + parkList().joinToString(" | ") { "${it.sender}·${it.moment}·${receivedAt(it)?.let { t -> java.text.SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(java.util.Date(t)) }}" } +
                " · 예약 ${reservedCount()}개 · 도착(주행 중 줄) ${arrivedLater()}개")
            "listplay" -> { val i = intent.getStringExtra("value")?.toIntOrNull(); Hub.log("[테스트] 목록 듣기 → ${playMissed(i?.let { parkList().getOrNull(it)?.id ?: "-" })}") }
            "listen" -> accept("알림 [듣기]")
            "stop" -> stopListening("알림 [멈추기]")
            "later" -> asking?.let { Hub.log("알림 [나중에]"); defer(it) }
            "startp" -> { getSharedPreferences("sim", MODE_PRIVATE).edit().remove("startOffered").apply(); offerStartParked() }
            "mode" -> { Hub.setListenMode(this, intent.getStringExtra("value") ?: "button"); Hub.log("[테스트] 듣는 방식 → ${Hub.listenMode(this)}"); Hub.changed() }
            "sethome" -> {
                val lat = intent.getStringExtra("lat")?.toDouble() ?: DEMO_HOME_LAT; val lon = intent.getStringExtra("lon")?.toDouble() ?: DEMO_HOME_LON
                watchHome(lat, lon, "테스트로 지정", "test")
            }
        }
        return START_STICKY
    }

    /** 우리 목소리가 끼어들면 안 되는 소리: 내비 안내·통화·음성비서·알람·차 안전음(시스템 용도 1000번대). */
    private fun importantSound(): String? = am.activePlaybackConfigurations
        .map { it.audioAttributes.usage }
        .firstOrNull { it == AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE || it == AudioAttributes.USAGE_VOICE_COMMUNICATION ||
            it == AudioAttributes.USAGE_ASSISTANT || it == AudioAttributes.USAGE_ALARM || it == AudioAttributes.USAGE_NOTIFICATION_RINGTONE || it >= 1000 }
        ?.let { usageName(it) }

    /** 다른 앱이 지금 내고 있는 소리의 용도(내비 안내·통화·음성비서 등). */
    private fun otherSounds(): List<String> = am.activePlaybackConfigurations
        .filter { it.audioAttributes.usage != AudioAttributes.USAGE_NOTIFICATION || player == null }
        .map { usageName(it.audioAttributes.usage) }

    private fun usageName(u: Int) = when (u) {
        AudioAttributes.USAGE_MEDIA -> "음악"
        AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE -> "내비 안내"
        AudioAttributes.USAGE_VOICE_COMMUNICATION -> "통화"
        AudioAttributes.USAGE_ASSISTANT -> "음성비서"
        AudioAttributes.USAGE_ALARM -> "알람"
        AudioAttributes.USAGE_NOTIFICATION -> "알림"
        AudioAttributes.USAGE_NOTIFICATION_RINGTONE -> "전화벨"
        1000 -> "긴급음"; 1001 -> "안전음"; 1002 -> "차량 상태음"; 1003 -> "안내 방송"
        else -> "용도$u"
    }
    override fun onBind(intent: Intent?): IBinder? = null

    /** 사용자가 앱을 닫았다: 지금 나오는 소리를 멈추고 이번 운행은 조용히 있는다. 시동을 끄면 풀린다. */
    override fun onTaskRemoved(rootIntent: Intent?) {
        quietUntilNextDrive()
        super.onTaskRemoved(rootIntent)
    }

    private fun quietUntilNextDrive() {
        Hub.log("앱 닫음 → 이번 운행은 재생 안 함")
        Hub.quiet = true
        cancelLater()   // 기다리던 띵동·안내·이어 듣기 예약도 버린다
        endAsking()
        // 버튼을 눌러 길이 트이길 기다리던 것·이어 듣던 것은 못 들은 것으로 남긴다
        current?.let { Hub.opened -= it.id }
        current = null; annDone = null; Hub.waiting = null; parkedOffer = null
        stopAnn()
        if (Hub.arrivalLeft > 0) { parkChain++; Hub.arrivalLeft = 0 }
        stopAudio()
        queue.clear()
        nm.cancel(3)
        Hub.changed()
    }

    override fun onDestroy() {
        main.removeCallbacks(listRefresh)
        cancelLater()
        watching = false; changeWatch.interrupt()
        stopAudio()
        wheel?.close("서비스 끝")
        // 다시 떠도 받는 곳·연결이 겹치지 않게 모두 푼다
        screenOff?.let { runCatching { unregisterReceiver(it) } }; screenOff = null
        netWatch?.let { cb -> runCatching { getSystemService(android.net.ConnectivityManager::class.java).unregisterNetworkCallback(cb) } }; netWatch = null
        runCatching { homeAlertId?.let { location?.removeProximityAlert(it) } }
        placeAlerts.values.filter { it.isNotEmpty() }.forEach { id -> runCatching { location?.removeProximityAlert(id) } }
        runCatching { location?.release() }
        runCatching { navi?.release() }
        stopAnn()
        runCatching { car?.disconnect() }
        runCatching { vehicle?.release() }
        io.shutdown()
        Hub.service = null
        super.onDestroy()
    }

    // ---------- 메시지 ----------

    /** 오늘 숨겨진 메시지를 서버에서 받아 Hub에 올린다. */
    fun refresh(then: (() -> Unit)? = null) = bg {
        val fetchDay = LocalDate.now().toString()
        // 처음 깐 차는 무료 서버가 잠에서 깨는 동안(최대 50초쯤) 기다린다. 금방 포기하면 진짜 서버가 있는데도 체험 메시지로 빠진다
        val first = !getSharedPreferences("sim", MODE_PRIVATE).getBoolean("everConnected", false)
        runCatching { Api.today(fetchDay, if (first) 60_000 else 8000) }
            .onSuccess { list ->
                Store.saveToday(this, list) // 목소리 파일까지 미리 받아 둔다
                // 날이 바뀌어도 다음 첫 주차까지 남기는 못 들은 메시지(11/09): 그날 목록을 다시 받아 남긴 사람이 지웠거나 들은 것은 뺀다(못 받으면 남겨 둔 그대로)
                val kept = Hub.carried(this, fetchDay).groupBy { it.day }.flatMap { (d, ms) ->
                    val then = d?.let { day -> runCatching { Api.today(day, 8000) }.getOrNull() }
                    if (then == null) ms else ms.mapNotNull { m -> then.firstOrNull { it.id == m.id && !it.done && !it.stopped } }
                }
                main.post {
                    Hub.offline = false
                    // 정차한 채 자정을 넘기면 어제 기록(열림·들음)을 비운다(반복 메시지가 오늘 다시 나오게). 운행 중·재생 중에는 건드리지 않는다
                    if (!inTrip && !playing && asking == null && current == null) Hub.rollDay()
                    if (Hub.demo) Hub.log("서버 연결됨 → 체험 메시지 끝, 진짜 메시지로")
                    Hub.demo = false
                    getSharedPreferences("sim", MODE_PRIVATE).edit().putBoolean("everConnected", true).apply()
                    // 운행 중에 자정이 지나 새 날 목록을 받으면, 어젯밤 순간이 왔던 메시지는 이번 운행이 끝날 때까지 남긴다(도착 때 들려주려고)
                    val ids0 = list.map { it.id }.toSet()
                    val carry0 = if (inTrip && listDay != fetchDay) Hub.today.filter { it.id in Hub.occurredThisTrip && it.id !in ids0 } else emptyList()
                    // 지난날 것 중 그날 목록에서 빠진 것(지움·들음)은 기록에서도 지운다
                    Hub.carried(this, fetchDay).filter { c -> kept.none { it.id == c.id } }.forEach { Hub.forgetOccurred(this, it.id) }
                    Hub.pruneOccurred(this, fetchDay, ids0)
                    val carry = (carry0 + kept.filter { k -> k.id !in ids0 && carry0.none { it.id == k.id } })
                    if (!inTrip || carry0.isEmpty()) listDay = fetchDay
                    val gone = Hub.today.filter { it.id !in ids0 && carry.none { c -> c.id == it.id } }
                    // 날이 바뀌어 빠진 것 중 자정 뒤에 들은 것은 지운 메시지가 아니다: 들은 메시지 화면에 남긴다
                    val aged = gone.filter { it.day != null && it.day < fetchDay && (it.id in Hub.heard || it.id in Hub.skipped) }
                    if (aged.isNotEmpty()) Hub.retired = Hub.retired.filter { r -> aged.none { it.id == r.id } } + aged
                    Hub.today = list + carry
                    Hub.loaded = true
                    // 목록에서 빠진 메시지(지워졌거나 날이 바뀜)는 차에 받아 둔 음성 파일도 바로 지운다(들은 메시지 화면에 남긴 것은 다시 듣기용으로 둔다)
                    val drop = gone.filter { g -> aged.none { it.id == g.id } }
                    if (drop.isNotEmpty()) bg { drop.forEach { runCatching { Store.audioFile(this, it).delete() } } }
                    // 남긴 사람이 지운 메시지는 기다리던 줄에서도 뺀다
                    val ids = Hub.today.map { it.id }.toSet()
                    queue.filter { it.id !in ids }.forEach { Hub.log("지워진 메시지 빼기: ${it.sender}") }
                    queue.removeAll { it.id !in ids }
                    // 지금 알리는 중이거나 재생을 기다리는 메시지가 지워졌으면(남긴 사람이 지움·신고) 조용히 끝낸다
                    asking?.takeIf { it.id !in ids }?.let { Hub.log("지워진 메시지라 알림 끝: ${it.sender}"); endAsking(); playing = false; Hub.changed() }
                    current?.takeIf { it.id !in ids && Hub.nowPlaying?.id != it.id }?.let { Hub.log("지워진 메시지라 재생 안 함: ${it.sender}"); current = null; playing = false; Hub.changed() }
                    val unsent = restoreHeard(list)
                    val repeats = Hub.unsentRepeats(this)
                    if (repeats.isNotEmpty()) bg { repeats.forEach { e -> runCatching { Api.setRepeat(e.substringBefore(':'), e.substringAfter(':') == "true") }.onSuccess { Hub.clearUnsentRepeat(this, e) } } }
                    if (unsent.isNotEmpty()) bg { unsent.forEach { h -> runCatching { Api.markPlayed(h.id, h.day) }.onSuccess { main.post { Hub.log("들음 다시 알림: ${h.sender}") } } } }
                    val left = updateWaitNote()
                    Plaza.load(this)   // 서버에 바뀐 게 있으면(새 사람 연결·끊김·자리) 광장도 다시 받는다
                    Hub.log("오늘 숨겨진 메시지 ${list.size}개 (남은 $left)")
                    Hub.changed()
                    watchPlaces()
                    updateDemoHome()
                    then?.invoke()
                }
            }
            .onFailure { e -> main.post {
                Hub.offline = true
                Hub.log("서버에 못 닿음: ${e.message}")
                val cached = Store.loadToday(this)
                if (cached != null && Hub.today.isEmpty()) {
                    Hub.today = cached + Hub.carried(this, LocalDate.now().toString()).filter { c -> cached.none { it.id == c.id } }; Hub.loaded = true
                    // 인터넷 없이 다시 켜져도 오늘 들은 것·넘긴 것·그만 들은 것은 다시 틀지 않는다(서버에 받았을 때와 같게)
                    restoreHeard(cached)
                    Hub.log("저장해 둔 오늘 메시지 ${cached.size}개로 대기 (오프라인)")
                    updateWaitNote()
                    Hub.changed()
                    then?.invoke()
                } else if (cached == null && (Hub.today.isEmpty() || Hub.demo) && !getSharedPreferences("sim", MODE_PRIVATE).getBoolean("everConnected", false)) {
                    // 체험 메시지는 서버에 한 번도 닿은 적 없는 차(심사용 APK를 처음 깐 경우)에만. 진짜로 쓰던 차가 지하주차장에서 가짜 메시지를 듣지 않게
                    // 심사용 APK를 처음 깔았을 때처럼 서버도 저장분도 없으면 예시 메시지로 바로 체험하게 한다
                    bg {
                        val demo = runCatching { Demo.messages(this) }.getOrElse { Hub.log("체험 메시지 준비 실패: $it"); emptyList() }
                        main.post {
                            if (!Hub.demo) Hub.log("체험 메시지 ${demo.size}개로 대기 (서버 없음)")
                            // 그사이 서버가 답해 진짜 목록을 받았으면 체험으로 덮지 않는다
                            if (getSharedPreferences("sim", MODE_PRIVATE).getBoolean("everConnected", false)) { then?.invoke(); return@post }
                            Hub.demo = true
                            Hub.today = demo; Hub.loaded = true
                            updateWaitNote()
                            Hub.changed()
                            updateDemoHome()
                            then?.invoke()
                        }
                    }
                } else { if (!Hub.loaded) { Hub.loaded = true; Hub.changed() }; then?.invoke() }
            } }
    }

    /** 서버·저장분 어느 쪽으로 받아도 오늘 들은 것·넘긴 것·그만 들은 것을 되살린다. 들었는데 서버가 모르는 것을 돌려준다. */
    private fun restoreHeard(list: List<Hidden>): List<Hidden> {
        Hub.opened += list.filter { it.done || it.stopped }.map { it.id }   // 그만 들은 반복 메시지는 목록엔 두되 다시 틀지 않는다
        // [다음]으로 넘긴 것은 앱이 다시 떠도 오늘 다시 틀지 않는다(들은 메시지 화면에서 골라 듣는다)
        Hub.skippedStored(this).let { sk -> list.filter { it.id in sk && it.id !in Hub.heard }.forEach { Hub.opened += it.id; Hub.skipped += it.id } }
        list.filter { it.played }.forEach { Hub.markHeard(this, it, now = false) }
        // 들었는데 서버가 모르는 것(알리다 끊김): 다시 재생하지 않고 다시 알린다
        val unsent = list.filter { !it.played && it.id in Hub.heardStored(this) }
        unsent.forEach { Hub.opened += it.id; Hub.heard += it.id }
        return unsent
    }

    /** 뒤에서 대기 알림을 지금 대기 개수로 고친다. 남은 개수를 돌려준다. */
    private fun updateWaitNote(): Int {
        val left = Hub.waitingCount(this)
        // 화면 큰 숫자와 같은 말(75번 A-2): 도착한 게 있으면 그 개수, 없으면 예약된 개수. 0개면 제목은 '도담도담'만(63번 4장)
        val arrived = runCatching { missed().size }.getOrDefault(0)
        val reserved = runCatching { reservedCount() }.getOrDefault(left)
        nm.notify(1, waitNotification(when { arrived > 0 -> "도착한 음성 메시지 ${arrived}개"; reserved > 0 -> "예약된 음성 메시지 ${reserved}개"; else -> null }))
        return left
    }

    private fun pending(moment: String) = Hub.today.filter { it.moment == moment && it.id !in Hub.opened }

    /** 운행 중에 새로 받은 메시지인데 그 순간이 이미 와 있는 중이면(비가 오는 중, 이미 부족한 잔량, 이미 오래 달림) 바로 순간으로 친다.
     *  가족이 지금 비 오는 걸 보고 남긴 메시지가 이번 운행에 들리게 하려는 것. 이번 운행에 이미 순간이 왔던 메시지는 다시 부르지 않는다. */
    private fun catchUpMoments() {
        if (!inTrip || gear != VehicleGear.GEAR_DRIVE || !Hub.enabled(this)) return
        val now = SystemClock.elapsedRealtime()
        val ongoing = buildList {
            if (wiperOnAt != 0L && now - wiperOnAt >= RAIN_HOLD_MS) add("rain" to "비가 옵니다.")
            energy()?.let { (pct, what) -> if (pct < BATTERY_LOW_PCT) add("battery" to lowLine(what)) }
            if (now - drivingSince >= LONG_DRIVE_MS) add("long" to "오래 달렸습니다.")
        }
        ongoing.forEach { (moment, intro) ->
            val fresh = pending(moment).filter { it.id !in Hub.occurredThisTrip && !Hub.occurred(this, it.id) }
            if (fresh.isEmpty()) return@forEach
            Hub.log("이미 와 있는 순간($moment)에 새 메시지 ${fresh.size}개")
            Hub.markOccurred(this, fresh.map { it.id })
            pickEach(fresh).forEach { enqueue(it, intro) }
        }
    }

    /** 순간이 왔다: 지금 못 들어도 도착 때 '못 들은 메시지'가 되도록 먼저 기록하고 대기열로 보낸다. */
    private fun momentCame(moment: String, intro: String) {
        val list = pending(moment)
        Hub.markOccurred(this, list.map { it.id })
        // 서 있을 때(P, 운행 밖) 온 순간은 대기열에 넣지 않는다(11/09 버그: P에서 들어도 대기열에 남아 출발하면 같은 메시지를 또 알렸고, P 내내 1초마다 확인했다).
        // 바로 알리고(서 있으니 안전), 다른 게 나오는 중이면 주차 목록에만 남긴다
        if (gear == VehicleGear.GEAR_PARK && !inTrip) { pickEach(list).firstOrNull()?.let { offerParked(it, intro) }; Hub.changed(); return }
        pickEach(list).forEach { enqueue(it, intro) }
    }

    /** P에서 순간이 왔을 때 알림(차 탈 때 P 알림과 같은 틀): 띵동 + 안내 + 카드. 다른 게 나오는 중이면 알리지 않는다(주차 목록에 있다). */
    private fun offerParked(h: Hidden, intro: String) {
        if (!Hub.enabled(this) || gear != VehicleGear.GEAR_PARK || asking != null || playing || current != null || player != null || replayMode || Hub.arrivalLeft > 0) {
            Hub.log("정차 중 순간: ${h.sender} 메시지 → 주차 목록"); return
        }
        Hub.log("정차 중 순간: ${h.sender} 메시지 알림")
        intros[h.id] = intro
        playing = true; current = h; Hub.opened += h.id; Hub.changed()
        ask(h)
    }

    /** 한 사람이 같은 순간에 여러 개 남겨 두면 돌아가며 나온다(기획 '몰아서 남길지는 본인 자유'): 이번엔 사람마다 하나씩, 가장 먼저 남긴 것.
     *  다른 사람 것은 각자 하나씩 나온다(간격은 대기열이 지킨다). 나머지는 다음에 그 순간이 오거나 주차해서 이어 듣는다. */
    private fun pickEach(list: List<Hidden>): List<Hidden> =
        list.filter { h -> h.id !in Hub.opened && h.id !in deferredThisTrip && queue.none { it.id == h.id } && asking?.id != h.id }
            .groupBy { it.sender }.values.map { it.first() }

    // ---------- 차 신호 ----------

    /** 광장이 반응하는 차 신호(64번 27). 하나가 안 돼도 나머지는 받는다. 값이 바뀌면 화면을 다시 그린다. */
    private fun plazaSignals(v: Vehicle) {
        val driver = ai.pleos.playground.vehicle.api.model.area.SeatArea(ai.pleos.playground.vehicle.constant.area.SeatValue.ROW_1_LEFT)
        fun sub(name: String, f: () -> Unit) = runCatching(f).onFailure { Hub.log("$name 구독 불가: $it") }
        fun fail(name: String) = { e: Exception -> main.post { Hub.log("$name 구독 실패: $e") }; Unit }
        sub("등받이") {
            v.getSeat().registerSeatBackrestAnglePosition(driver, object : ai.pleos.playground.vehicle.listener.SeatBackrestAnglePositionListener {
                override fun onSeatBackrestAnglePositionUpdated(value: Int?) { main.post { if (Hub.backrest != value) { Hub.backrest = value; Hub.log("등받이 → $value"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("등받이")(e) }
            })
        }
        sub("안전벨트") {
            v.getSeat().registerSeatBeltBuckledState(driver, object : ai.pleos.playground.vehicle.listener.SeatBeltBuckledStateListener {
                override fun onSeatBeltBuckledStateUpdated(value: Boolean?) { main.post { if (Hub.beltOn != value) { Hub.beltOn = value; Hub.log("안전벨트 → $value"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("안전벨트")(e) }
            })
        }
        sub("운전석 문") {
            v.getDoor().registerDoorPosition(ai.pleos.playground.vehicle.api.model.area.DoorArea(ai.pleos.playground.vehicle.constant.area.DoorValue.ROW_1_LEFT),
                object : ai.pleos.playground.vehicle.listener.DoorPositionListener {
                    private var open = false
                    override fun onPositionUpdated(value: Int?) { main.post {
                        val now = (value ?: 0) > 0
                        if (now && !open) { Hub.doorOpenAt = SystemClock.elapsedRealtime(); Hub.log("운전석 문 열림"); Hub.changed() }
                        open = now
                    } }
                    override fun onFailed(e: Exception) { fail("운전석 문")(e) }
                })
        }
        sub("충전구") {
            v.getEvBattery().registerEvChargePortOpen(object : ai.pleos.playground.vehicle.listener.EvChargePortOpenListener {
                override fun onEvChargePortOpenUpdated(value: Boolean?) { main.post { val o = value == true; if (Hub.chargePort != o) { Hub.chargePort = o; Hub.log("충전구 → $o"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("충전구")(e) }
            })
        }
        sub("배터리") {
            v.getEvBattery().registerEvBatteryStateOfCharge(object : ai.pleos.playground.vehicle.listener.EvBatteryStateOfChargeListener {
                override fun onEvBatteryStateOfChargeUpdated(value: Int?) { main.post { if (Hub.soc != value) { Hub.soc = value; Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("배터리")(e) }
            })
        }
        sub("무드등 색") {
            v.getLight().registerAmbientLightBrightnessColorListener(driver, object : ai.pleos.playground.vehicle.listener.AmbientLightBrightnessColorListener {
                override fun onBrightnessColorUpdated(value: Int?) { main.post { if (Hub.ambientColor != value) { Hub.ambientColor = value; Hub.log("무드등 색 → ${value?.let { "#%06X".format(it and 0xFFFFFF) }}"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("무드등 색")(e) }
            })
        }
        sub("무드등 밝기") {
            v.getLight().registerAmbientLightBrightnessListener(driver, object : ai.pleos.playground.vehicle.listener.AmbientLightBrightnessListener {
                override fun onBrightnessUpdated(value: Int?) { main.post { if (Hub.ambientBright != value) { Hub.ambientBright = value; Hub.log("무드등 밝기 → $value"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("무드등 밝기")(e) }
            })
        }
        sub("풍량") {
            v.getHVAC().registerHvacFanSpeed(driver, object : ai.pleos.playground.vehicle.listener.HvacFanSpeedListener {
                override fun onHvacFanSpeedUpdated(value: Int?) { main.post { if (Hub.fan != value) { Hub.fan = value; Hub.log("풍량 → $value"); Hub.changed() } } }
                override fun onFailed(e: Exception) { fail("풍량")(e) }
            })
        }
    }

    private fun startVehicle() {
        // SDK가 없거나 권한이 빠져 만들다 죽으면 서비스가 다시 뜨며 같은 자리에서 또 죽는다: 감싸서 차 신호만 없이 대기한다
        val v = runCatching { Vehicle(this) }.getOrElse { Hub.log("Vehicle 만들기 실패: $it"); startHome(); return }
        vehicle = v
        runCatching { v.initialize() }.onFailure { Hub.log("Vehicle 연결 실패: $it"); return }
        // 권한이 빠진 신호 하나 때문에 대기 전체가 죽지 않게 따로 감싼다
        runCatching {
            v.getGear().registerGearSelection(object : GearSelectionListener {
                override fun onSelected(value: VehicleGear?) { main.post { onGear(value) } }
                override fun onFailed(e: Exception) { main.post { Hub.log("기어 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("기어 구독 불가: $it") }
        runCatching {
            v.getWiper().registerWiperState(WindowArea(WindowValue.FRONT_WINDSHIELD), object : WiperStateListener {
                override fun onWiperStateUpdated(value: WiperState?) { main.post { onWiper(value) } }
                override fun onFailed(e: Exception) { main.post { Hub.log("와이퍼 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("와이퍼 구독 불가: $it") }
        plazaSignals(v)
        runCatching {
            // 광장 가로등: 전조등을 켜면 켜진다(주간 주행등은 켜짐으로 보지 않는다)
            v.getLight().registerLowBeamLightState(object : ai.pleos.playground.vehicle.listener.LightStateListener {
                override fun onLightStateUpdated(value: ai.pleos.playground.vehicle.constant.control.LightState?) {
                    main.post { val on = value == ai.pleos.playground.vehicle.constant.control.LightState.ON; if (Hub.lowBeam != on) { Hub.lowBeam = on; Hub.log("전조등 → $value"); Hub.changed() } }
                }
                override fun onFailed(e: Exception) { main.post { Hub.log("전조등 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("전조등 구독 불가: $it") }
        runCatching {
            v.getSteeringWheel().registerSteeringWheelAngle(object : SteeringWheelAngleListener {
                override fun onSteeringWheelAngleUpdated(value: Float?) { value?.let { main.post { onSteer(it) } } }
                override fun onFailed(e: Exception) { main.post { Hub.log("조향 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("조향 구독 불가: $it") }
        readSteer()
        subscribeSpeed()
        // 방향지시등: 차로를 바꾸는 동안에는 들려주지 않는다
        runCatching {
            v.getTurnSignal().registerTurnSignalState(object : ai.pleos.playground.vehicle.listener.TurnSignalStateListener {
                override fun onTurnSignalStateUpdated(value: ai.pleos.playground.vehicle.constant.area.TurnSignalValue?) { main.post {
                    // 값이 안 오면(null) 켜진 것으로 치지 않는다: 계속 '방향지시등 켜짐'으로 재생이 막히지 않게
                    val on = value != null && value != ai.pleos.playground.vehicle.constant.area.TurnSignalValue.OFF
                    if (turnOn && !on) turnOffAt = SystemClock.elapsedRealtime()
                    turnOn = on; Hub.log("방향지시등 → $value")
                } }
                override fun onFailed(e: Exception) { main.post { Hub.log("방향지시등 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("방향지시등 구독 불가: $it") }
        // 배터리(전기차)·기름(내연기관) 잔량: 차종마다 하나만 지원되므로 둘 다 걸어 둔다
        runCatching {
            v.getEvBattery().registerEvBatteryStateOfCharge(object : ai.pleos.playground.vehicle.listener.EvBatteryStateOfChargeListener {
                override fun onEvBatteryStateOfChargeUpdated(value: Int?) { main.post { onEnergy(value, "배터리") } }
                override fun onFailed(e: Exception) { main.post { Hub.log("배터리 잔량 구독 실패: $e") } }
            })
        }.onFailure { Hub.log("배터리 잔량 구독 불가: $it") }
        runCatching {
            v.getFuel().registerFuelPercent(object : ai.pleos.playground.vehicle.listener.FuelPercentListener {
                override fun onFuelPercentUpdated(value: Int?) { main.post { onEnergy(value, "기름") } }
                override fun onFailed(e: Exception) {}
            })
        }.onFailure { Hub.log("기름 잔량 구독 불가: $it") }
        Hub.log("차 신호 구독: 기어·와이퍼·조향·속도·잔량")
        startHome()
    }

    /** 속도 구독. 처음엔 권한이 없어 실패할 수 있어 허용 뒤 다시 부른다(resubscribe). */
    private fun subscribeSpeed() {
        if (speedWatch != null) return
        runCatching {
            val c = car ?: android.car.Car.createCar(this).also { car = it }
            val pm = c.getCarManager(android.car.Car.PROPERTY_SERVICE) as android.car.hardware.property.CarPropertyManager
            val cb = object : android.car.hardware.property.CarPropertyManager.CarPropertyEventCallback {
                override fun onChangeEvent(v: android.car.hardware.CarPropertyValue<*>) { (v.value as? Float)?.let { mps -> main.post { onSpeed(mps * 3.6f) } } }
                override fun onErrorEvent(propId: Int, zone: Int) {}
            }
            if (pm.registerCallback(cb, android.car.VehiclePropertyIds.PERF_VEHICLE_SPEED, android.car.hardware.property.CarPropertyManager.SENSOR_RATE_ONCHANGE)) speedWatch = cb
            else Hub.log("속도 구독 거절됨")
        }.onFailure { Hub.log("속도 구독 불가: $it") }
    }

    /** 속도: 주차장을 벗어났는지, 서 있다가 막 출발했는지(출발 직후 5초는 새로 시작하지 않는다, C10). */
    private fun onSpeed(kph: Float) {
        if (speedKph < 1f && kph >= 1f) pullAwayAt = SystemClock.elapsedRealtime()
        speedKph = kph
        if (speedKph >= MIN_SPEED_KPH) leftLot = true
    }
    private var pullAwayAt = 0L

    /** 운전자가 나중에 속도·위치를 허용했다(앱 화면에서 부른다): 그때 못 건 구독만 다시 건다. */
    fun resubscribe() {
        val ok = { p: String -> checkSelfPermission(p) == android.content.pm.PackageManager.PERMISSION_GRANTED }
        if (speedWatch == null && ok("android.car.permission.CAR_SPEED")) { Hub.log("속도 권한 허용됨 → 다시 구독"); subscribeSpeed() }
        if (ok("pleos.car.permission.FUSED_LOCATION")) {
            if (homeAlertId == null) {
                homeTarget?.let { (lat, lon) -> watchHome(lat, lon, "권한 허용 뒤 다시", homeSource ?: "navi") }
                runCatching { navi?.getBookmarkInfo() }   // 내비 '집'을 그사이 못 받았으면 다시 묻는다
            }
            watchPlaces()
        }
    }

    /** 지금 쓰는 잔량: 전기차면 배터리, 아니면 기름. 지원하지 않는 쪽에서 오는 0은 버린 값이다. */
    private fun energy(): Pair<Int, String>? = evPct?.let { it to "배터리" } ?: fuelPct?.let { it to "기름" }
    private fun lowLine(what: String) = if (what == "기름") "기름이 부족합니다." else "배터리가 부족합니다."

    /** 잔량이 15% 아래로 내려가는 순간 한 번. 주행 중이면 대기열로, 아니면 다음 출발 때 안전 타이밍에. */
    private fun onEnergy(pct: Int?, what: String) {
        // 0은 그 차가 지원하지 않는 쪽(전기차의 기름 등)에서 오는 값이라 버린다
        if (pct == null || pct <= 0) return
        val before = energy()
        if (what == "배터리") evPct = pct else fuelPct = pct
        val after = energy() ?: return
        if (before != null && before.second == after.second && before.first >= BATTERY_LOW_PCT && after.first < BATTERY_LOW_PCT && Hub.enabled(this)) {
            Hub.log("${after.second} ${after.first}% → 부족 순간")
            momentCame("battery", lowLine(after.second))
        }
    }

    /** 이미 부족한 채로 출발해도 순간으로 친다. */
    private fun energyLowAtStart() {
        val (pct, what) = energy() ?: return
        if (pct < BATTERY_LOW_PCT && Hub.enabled(this)) momentCame("battery", lowLine(what))
    }

    // ---------- 집 근처 ----------

    /** 내비 즐겨찾기의 '집'을 찾아 반경 알림을 건다. 없으면 시연용 좌표. 위치 판단은 차 안에서만 하고 어디에도 보내지 않는다. */
    private fun startHome() {
        runCatching {
            val n = ai.pleos.playground.navi.helper.NaviHelper(this)
            navi = n
            n.initialize({
                n.addListener(object : ai.pleos.playground.navi.helper.listener.NaviHelperEventListener {
                    override fun onBookmarkInfo(list: List<ai.pleos.playground.navi.data.BookmarkInfo>) {
                        // 집 칸은 늘 있지만 등록 전엔 좌표가 0,0으로 온다(실측) → 등록 안 된 것으로 본다
                        val home = list.firstOrNull { it.category.toString().contains("HOME", ignoreCase = true) && (it.latitude != 0.0 || it.longitude != 0.0) }
                        main.post {
                            if (home != null) watchHome(home.latitude, home.longitude, "내비 '집'", "navi")
                            else { if (homeSource == "navi") unwatchHome("내비에서 집이 지워짐"); updateDemoHome() }
                        }
                    }
                    override fun onBookMarkChanged() { runCatching { n.getBookmarkInfo() } }
                })
                n.getBookmarkInfo()
            }, { e -> main.post { Hub.log("내비 연결 실패: $e"); updateDemoHome() } })
        }.onFailure { Hub.log("내비 연결 불가: $it"); updateDemoHome() }
    }

    /** 내비에 집이 없을 때 시연용 좌표는 시연(짧은 시간 도구·체험 메시지)에서만 쓴다. 평소엔 집이 없으면 집 근처를 보지 않는다. */
    private fun updateDemoHome() {
        if (homeSource == "navi" || homeSource == "test") return
        if (SHORT && homeSource == null) watchHome(DEMO_HOME_LAT, DEMO_HOME_LON, "내비에 집이 없어 시연용 좌표", "demo")
        else if (!SHORT && homeSource == "demo") unwatchHome("시연이 끝나 시연용 집 좌표 풂")
    }

    private fun unwatchHome(why: String) {
        homeAlertId?.let { id -> runCatching { location?.removeProximityAlert(id) } }
        homeAlertId = null; homeSource = null; homeTarget = null
        Hub.log("집 근처 감시 끝 ($why)")
    }

    private fun watchHome(lat: Double, lon: Double, from: String, source: String) {
        homeSource = source; homeTarget = lat to lon
        runCatching {
            val f = location ?: ai.pleos.playground.location.fused.FusedLocation(this).also { it.initialize(); location = it }
            homeAlertId?.let { id -> runCatching { f.removeProximityAlert(id) } }
            homeAlertId = null
            f.addProximityAlert(ai.pleos.playground.location.fused.model.ProximityAlertRequest(lat, lon, HOME_RADIUS_M, BOTH_WAYS),
                object : ai.pleos.playground.location.fused.listener.ProximityAlertListener {
                    override fun onRegistered(id: String) { main.post { homeAlertId = id; Hub.log("집 근처 ${HOME_RADIUS_M.toInt()}m 감시 ($from · %.4f, %.4f)".format(lat, lon)) } }
                    override fun onTransition(e: ai.pleos.playground.location.fused.model.ProximityAlertEvent) { main.post { if (cameBack("home", e)) onNearHome() } }
                    override fun onError(e: Exception) { main.post { Hub.log("집 근처 감시 오류: $e") } }
                })
        }.onFailure { Hub.log("집 근처 감시 불가: $it") }
    }

    /** 안 열린 특정 장소 메시지마다 반경 알림을 건다. 열렸거나 목록에서 빠지면 푼다. */
    private fun watchPlaces() {
        val f = runCatching { location ?: ai.pleos.playground.location.fused.FusedLocation(this).also { it.initialize(); location = it } }.getOrNull() ?: return
        val want = Hub.today.filter { it.place != null && it.id !in Hub.opened }.associateBy { it.id }
        (placeAlerts.keys - want.keys).toList().forEach { id -> runCatching { f.removeProximityAlert(placeAlerts.getValue(id)) }; placeAlerts.remove(id) }
        (want.keys - placeAlerts.keys).forEach { id ->
            val p = want.getValue(id).place!!
            placeAlerts[id] = ""   // 등록 응답을 기다리는 동안 두 번 걸지 않게 자리부터 잡는다
            runCatching {
                f.addProximityAlert(ai.pleos.playground.location.fused.model.ProximityAlertRequest(p.lat, p.lon, HOME_RADIUS_M, BOTH_WAYS),
                    object : ai.pleos.playground.location.fused.listener.ProximityAlertListener {
                        override fun onRegistered(alert: String) { main.post { placeAlerts[id] = alert; Hub.log("${p.name} 근처 ${HOME_RADIUS_M.toInt()}m 감시") } }
                        override fun onTransition(e: ai.pleos.playground.location.fused.model.ProximityAlertEvent) { main.post { if (cameBack(id, e)) onNearPlace(id) } }
                        override fun onError(e: Exception) { main.post { placeAlerts.remove(id); Hub.log("${p.name} 감시 오류: $e") } }
                    })
            }.onFailure { placeAlerts.remove(id); Hub.log("${p.name} 감시 불가: $it") }
        }
    }

    private val BOTH_WAYS = setOf(ai.pleos.playground.location.fused.model.ProximityTransition.ENTER, ai.pleos.playground.location.fused.model.ProximityTransition.EXIT)
    private val leftAt = mutableMapOf<String, Long>() // 반경을 나간 시각(집은 "home", 장소는 메시지 id)

    /**
     * 반경에 들어온 게 '돌아온' 것인지. 나가는 길에 경계에서 위치가 흔들려 나갔다 들어왔다 하면 들어온 걸로 치지 않는다.
     * 반경 안에서 출발해 그 안을 맴도는 동안에는 들어옴 신호가 오지 않으니 그대로 조용하다.
     */
    private fun cameBack(key: String, e: ai.pleos.playground.location.fused.model.ProximityAlertEvent): Boolean {
        val now = SystemClock.elapsedRealtime()
        if (e.transition == ai.pleos.playground.location.fused.model.ProximityTransition.EXIT) { leftAt[key] = now; return false }
        val left = leftAt[key] ?: return true
        if (now - left >= AWAY_MIN_MS) return true
        Hub.log("반경 경계에서 다시 들어옴(${(now - left) / 1000}초 전 나감) → 무시")
        return false
    }

    private fun onNearPlace(id: String) {
        val h = Hub.today.firstOrNull { it.id == id && it.id !in Hub.opened } ?: return
        Hub.log("${h.place?.name} 근처 들어옴")
        // 운행 중이면 R·N에서 들어와도 순간으로 친다(11/09 결정: 후진·중립으로 들어오는 귀가를 놓치지 않게). 소리는 D가 되면 대기열이 낸다
        if (!inTrip || !Hub.enabled(this)) return
        Hub.markOccurred(this, listOf(h.id))
        enqueue(h, "${h.place?.name} 근처입니다.")
    }

    private fun onNearHome() {
        Hub.log("집 근처 들어옴")
        if (!inTrip || !Hub.enabled(this)) return
        momentCame("home", "집 근처입니다.")
    }

    private fun onGear(value: VehicleGear?) {
        val before = gear
        gear = value
        if (value == null || value == before) return
        Hub.parked = value == VehicleGear.GEAR_PARK; Hub.driving = !Hub.parked; Hub.changed()
        Hub.log("기어 → ${value.name.removePrefix("GEAR_")}")
        // 정차 중 다시 듣기(일시정지 포함)는 출발하면 바로 끝낸다: 주행 화면에 재생 버튼이 남지 않게
        if (value != VehicleGear.GEAR_PARK && replayMode) { Hub.log("다시 듣기 중 출발 → 멈춤"); stopAudio(); releaseFocus() }
        // 한 번의 운행은 첫 D부터 P까지. 주차하며 R·N을 거쳐도 끊기지 않는다(D→R→P도 도착, R→D는 새 출발 아님)
        if (value == VehicleGear.GEAR_DRIVE && !inTrip) { inTrip = true; onDepart() }
        if (value == VehicleGear.GEAR_PARK && inTrip) { inTrip = false; onPark() }
        if (value == VehicleGear.GEAR_PARK && before == null) {
            later(3000) { offerStartParked() } // 시동 켜고 아직 P
            // 시동 켜고 아직 P: 답장 안 한 들은 메시지가 있으면 화면에 카드 한 장(C7). 화면이 정차 중일 때만 보여 준다
            if (Hub.unreplied(this).isNotEmpty()) { Hub.nudge = true; Hub.changed() }
        }
    }

    /**
     * '차 탈 때' 메시지는 출발 전(P)에 먼저 알린다: 띵동 → "출발 전에 들을 수 있어요" → [듣기]/[나중에]·핸들 가운데 버튼.
     * 서 있으니 위험이 없다. 안 들으면 그대로 두었다가 출발할 때 평소 방식대로. 하루 한 번만.
     */
    private fun offerStartParked() {
        if (!Hub.enabled(this) || gear != VehicleGear.GEAR_PARK || asking != null || playing) return
        Hub.rollDay()
        val today = LocalDate.now().toString()
        val p = getSharedPreferences("sim", MODE_PRIVATE)
        if (p.getString("startOffered", null) == today || Hub.lastStart(this) == today) return
        refresh {
            val h = pending("start").firstOrNull() ?: return@refresh
            if (gear != VehicleGear.GEAR_PARK || asking != null || playing) return@refresh
            p.edit().putString("startOffered", today).apply()
            Hub.markOccurred(this, listOf(h.id)) // 알리는 동안엔 열림 상태라 출발 때 pending에 안 잡힌다
            Hub.log("출발 전(P): 차 탈 때 메시지 알림")
            playing = true; current = h; Hub.opened += h.id; Hub.changed()
            parkedOffer = h.id
            ask(h)
        }
    }

    private fun onDepart() {
        parkChain++
        // 주차 때 띵동·안내("도착한 음성 메시지가 있습니다.")가 아직 나오는 중이면 끝낸다: 출발한 뒤에 주차 안내가 들리지 않게
        if (asking == null && current == null && Hub.arrivalLeft == 0) { cancelLater(); if (annDone != null) { annDone = null; stopAnn() } }
        if (Hub.arrivalLeft > 0) { current?.let { Hub.opened -= it.id }; current = null; stopAudio(); Hub.arrivalLeft = 0; Hub.log("주차 중 이어 듣다 출발 → 멈춤") }
        // 출발 전(P) 알림에 대답하기 전에 출발했으면 그 알림은 여기서 끝낸다. 대답 없음으로 넘어가 이번 주행의 '도착해서'로 빠지지 않고 평소 주행 방식대로 나온다
        asking?.takeIf { it.id == parkedOffer }?.let { h ->
            Hub.log("출발 전 알림 중 출발 → ${h.sender} 메시지는 주행 중 평소대로")
            annDone = null; stopAnn()
            endAsking()
        }
        parkedOffer = null
        // 정차 중 순간 알림(배터리 등)에 대답하기 전에 출발: 알림만 끝낸다. 메시지는 재생 예정에 남아 다음 주차 목록에 있다
        asking?.let { h -> Hub.log("정차 중 알림 중 출발 → ${h.sender} 메시지는 주차해서"); annDone = null; stopAnn(); endAsking() }
        arriveReady.clear()
        Hub.dropParkSeen(this).takeIf { it.isNotEmpty() }?.let { gone -> Hub.log("지난날 못 들은 메시지 ${gone.size}개: 새 날 첫 주차가 지나 목록에서 뺌"); refresh() }
        Hub.nudge = false   // 출발하면 답장 카드는 접는다(주행 중에 들은 게 있으면 주차할 때 다시)
        Hub.parkHeard = emptyList()
        Hub.rollDay()
        drivingSince = SystemClock.elapsedRealtime()
        if (!steerSeen) readSteer()
        rainFiredThisTrip = false
        leftLot = false
        deferredThisTrip.clear()
        cuts.clear()
        heardThisTrip.clear()
        wheelHintSaid = false
        Hub.occurredThisTrip.clear()
        main.removeCallbacks(longDrive); main.postDelayed(longDrive, LONG_DRIVE_MS)
        if (wiperOnAt != 0L) checkRainLater()
        if (!Hub.enabled(this)) { Hub.log("재생 기능이 꺼져 있음 (앱에서 켜기)"); return }
        val today = LocalDate.now().toString()
        val first = Hub.lastStart(this) != today
        refresh {
            if (!inTrip) return@refresh   // 목록을 받는 사이 다시 주차했으면 출발 일은 하지 않는다(P에서 대기열이 생기지 않게)
            energyLowAtStart()
            // 그날 첫 출발이 아니어도 '남긴 뒤 첫 출발'이면 들려준다
            if (!first) { Hub.markOccurred(this, pending("start").map { it.id }); pickEach(pending("start")).forEach { enqueue(it, "") }; return@refresh }
            Hub.setLastStart(this, today)
            // 개수 안내가 안전 타이밍을 기다리다 주차로 버려져도 '차 탈 때'는 왔던 순간으로 남긴다
            Hub.markOccurred(this, pending("start").map { it.id })
            // 예약된 것(순간이 아직 안 온 것)만 센다. 방금 온 '차 탈 때'와 지난번에 온 못 들은 것은 도착한 메시지다(75번 A-2)
            val n = reservedCount()
            val startMoment = { pickEach(pending("start")).forEach { enqueue(it, "") }; Unit }
            // 주행 집중 모드(arrive)는 주행 중에 소리를 내지 않는다: 출발 안내도 하지 않는다
            val arriveMode = Hub.listenMode(this) == "arrive"
            if (n > 0 && !arriveMode) whenSafe("첫 출발 안내") {
                // 안내하는 동안은 재생 중으로 친다: 대기열이 같은 때에 띵동을 울리지 않게. 숫자는 말하지 않는다(녹음 고정 문장, 75번 B-2)
                playing = true
                announce(Ann.DEPART) { playing = false; lastPlayAt = SystemClock.elapsedRealtime(); startMoment() }
            }
            else if (gear == VehicleGear.GEAR_DRIVE) startMoment() // 들어 본 반복 메시지만 남은 날·차 탈 때 하나뿐인 날: 개수 안내 없이 순간만
        }
    }

    private fun onPark() {
        parkChain++
        wheelHintSaid = false
        cancelLater()   // 주행 중 기다리던 재생·다시 시도 예약이 주차 뒤에 소리 내지 않게
        main.removeCallbacks(longDrive)
        val drove = SystemClock.elapsedRealtime() - drivingSince
        queue.clear()
        // 안내·재생 중에 멈췄으면 못 들은 것으로 되돌린다
        current?.let { Hub.opened -= it.id; Hub.log("${it.sender}의 메시지가 끊겨 못 들은 것으로 남김") }
        current = null
        annDone = null
        stopAnn()   // 주행 중 안내가 주차 뒤까지 이어지지 않게
        Hub.waiting = null
        parkedOffer = null
        endAsking()
        stopAudio()
        if (!Hub.enabled(this)) return   // 받기를 꺼 뒀으면 도착해도 틀지 않는다
        Hub.lastTripMs = drove
        Hub.log("도착 (주행 ${drove / 1000}초)")
        // 주행 중에 들은 메시지가 있으면 주차 화면에 답장 안 한 메시지 카드(C7)
        if (heardThisTrip.isNotEmpty() && Hub.unreplied(this).any { it.id in heardThisTrip }) Hub.nudge = true
        Hub.parkHeard = emptyList()
        // '주차했을 때' 메시지(충분히 달렸을 때)는 이번 주차에서 받은 메시지다: 주차 목록에 이 주차 시각으로
        val arrive = if (drove >= ARRIVE_MIN_DRIVE_MS) pending("arrive") else emptyList()
        Hub.parkedAt = System.currentTimeMillis()
        arriveReady.clear(); arriveReady += arrive.map { it.id }
        Hub.markParkSeen(this)   // 지난날 못 들은 것은 새 날 첫 주차를 지나면(출발할 때) 뺀다
        val list = parkList()   // 받은 차례(먼저 온 것부터)
        // 주행 집중 모드(arrive)는 '주차하면 들려준다'가 그 방식이라 예전처럼 이어서 들려준다(주차했을 때 것 먼저).
        // 나머지(11/08 C8 · 11/09): 1개이고 그게 '주차했을 때' 메시지면 바로 틀고, 2개 이상이면 띵동 + 개수만 알리고 화면 목록에서 고른다.
        // 못 들은 것 하나뿐이면 지금처럼 알리지 않는다(화면 [듣기]). 새로 생긴 게 없으면(지난번에 이미 알린 목록) 다시 알리지 않는다
        val arriveMode = Hub.listenMode(this) == "arrive"
        val fresh = arrive.isNotEmpty() || list.any { it.id in Hub.occurredThisTrip }
        val play = when {
            arriveMode -> arrive + list.filter { it.moment != "arrive" }
            list.size == 1 && arrive.size == 1 -> arrive
            else -> emptyList()
        }
        if (!arriveMode && list.isNotEmpty()) Hub.log("주차 목록 ${list.size}개${if (play.isEmpty()) " → 자동 재생 안 함(화면에서 골라 듣기)" else ""}")
        // 녹음 고정 문장(75번 B-2): 이름·개수를 말하지 않는다. 바로 틀 때는 '도착했습니다', 목록에서 고를 때는 '도착한 … 있습니다'
        val text = when {
            play.size == 1 -> Ann.ARRIVE
            play.isNotEmpty() -> Ann.PARKED
            list.size >= 2 && fresh -> Ann.PARKED
            else -> null
        }
        val chain = parkChain
        if (text != null) chimeThen { announce(text) { if (play.isNotEmpty()) playParked(play, chain) else { notifyReply(); askRepeats() } } }
        else { notifyReply(); askRepeats() }
        Hub.changed()
    }

    private fun onPowerDown() {
        if (Hub.quiet) { Hub.quiet = false; Hub.log("시동 끔 → 앱 닫음 풀림") }
        Hub.log("화면 꺼짐(시동 끔) → 재생 중단, 소리 권한 반납")
        // 이어 듣기·띵동→안내·다시 시도 예약을 모두 버린다: 꺼진 뒤 아무것도 나오지 않게
        parkChain++
        cancelLater()
        endAsking()
        current?.let { Hub.opened -= it.id }
        current = null; annDone = null; queue.clear(); Hub.waiting = null; parkedOffer = null
        Hub.arrivalLeft = 0
        stopAnn()
        stopAudio()
        Hub.changed()
    }

    private var listDay = LocalDate.now().toString() // 지금 Hub.today가 어느 날 목록인지
    private var parkChain = 0 // 주차·출발할 때마다 바뀐다. 지난 주차의 이어 듣기 예약이 새 운행에서 이어지지 않게

    /** 정차 중에는 안전 대기 없이 차례로 들려준다. */
    private var parkList: List<Hidden> = emptyList()   // 주차해서 이어 듣는 남은 메시지(지금 것 포함). [다음]에 쓴다
    private fun playParked(all: List<Hidden>, chain: Int = parkChain) {
        // 지난 이어 듣기 예약: 이어 듣기를 끝낸 쪽(출발·멈춤·시동 끔)이 이미 정리했다. 지금 이어 듣는 것의 개수를 건드리지 않는다
        if (chain != parkChain) return
        // 끝낼 때는 끝까지 들었을 때처럼 소리 권한도 돌려준다(다른 재생이 잡고 있으면 그대로)
        if (gear != VehicleGear.GEAR_PARK || !Hub.enabled(this)) { Hub.arrivalLeft = 0; chainFocus = false; if (player == null && !playing) releaseFocus(); Hub.changed(); return }
        // 그사이 목록에서 빠진 것(남긴 사람이 지움·신고로 막힘)은 건너뛴다
        val list = all.filter { h -> Hub.today.any { it.id == h.id } }
        if (list.size < all.size) Hub.log("이어 듣기에서 지워진 메시지 ${all.size - list.size}개 뺌")
        Hub.arrivalLeft = list.size
        parkList = list
        val h = list.firstOrNull() ?: run { Hub.arrivalLeft = 0; chainFocus = false; if (player == null && !playing) releaseFocus(); Hub.changed(); notifyReply(); askRepeats(); return }
        importantSound()?.let { busy ->
            Hub.waiting = "$busy 중"; Hub.changed()
            later(1000) { playParked(list, chain) }; return
        }
        Hub.waiting = null
        Hub.opened += h.id
        current = h   // 시동을 꺼 끊기면 못 들은 것으로 되돌린다
        Hub.changed()
        chainFocus = true
        playAudio(h, onFail = { current = null; chainFocus = false; later(3000) { playParked(if (gaveUp(h)) list.drop(1) else list, chain) } }) {
            current = null
            Hub.markHeard(this, h)
            heardThisTrip += h.id; lastSender = h.sender
            Hub.parkHeard = Hub.parkHeard + h
            updateWaitNote()
            if (!Hub.demo && !h.example) bg { runCatching { Api.markPlayed(h.id, h.day) } }
            Hub.log("${h.sender} 메시지 재생 끝 (정차 중)")
            Hub.changed()
            val rest = list.drop(1)
            if (rest.isEmpty()) { Hub.arrivalLeft = 0; chainFocus = false; releaseFocus(); notifyReply(); askRepeats(); Hub.changed() }
            else later(600) { playParked(rest, chain) }
        }
    }

    /** 이번 주차에서 받은 '주차했을 때' 메시지(충분히 달린 뒤 주차). 출발하면 비운다. */
    private val arriveReady = mutableSetOf<String>()

    /** 못 들은 메시지: 순간이 왔는데 끝까지 못 들은 것(날이 바뀌어도 다음 첫 주차까지) + 이번 주차에서 받은 '주차했을 때' 메시지. */
    fun missed(): List<Hidden> = Hub.today.filter { it.id !in Hub.opened && it.id !in Hub.heard &&
        if (it.moment == "arrive") it.id in arriveReady else (Hub.occurred(this, it.id) || it.id in Hub.occurredThisTrip) }

    /** 메시지를 받은 시각(순간이 온 때). '주차했을 때' 메시지는 이번 주차를 시작한 때. */
    fun receivedAt(h: Hidden): Long? = if (h.moment == "arrive" && h.id in arriveReady) Hub.parkedAt.takeIf { it > 0 } else Hub.occurredAt(this, h.id)

    /** 예약된 음성 메시지(75번 A-2): 아직 안 들은 것 중 순간이 아직 안 온 것. 순간이 온 것(주차 목록 · 주행 중 놓친 것)은 뺀다. */
    fun reservedCount(): Int = Hub.waitingCount(this, missed().map { it.id }.toSet() - waitingNow())

    /** 주행 중 '도착한 메시지 N개 · 주차 후 듣기' 줄의 N: 순간이 왔는데 못 들은 것 중 지금 알리려고 기다리거나 알리는 중인 것은 뺀다(곧 카드가 뜬다). */
    fun arrivedLater(): Int = missed().count { it.id !in waitingNow() }

    /** 지금 대기열에 있거나 알리는 중·재생 중인 메시지(아직 예약된 쪽으로 센다: 카드가 끝날 때 숫자가 한 번만 바뀌게). */
    private fun waitingNow(): Set<String> = queue.map { it.id }.toSet() + listOfNotNull(asking?.id, current?.id)

    /** 주차 목록(11/09): 받은 차례대로(먼저 온 것 위). 화면 줄과 [모두 듣기]가 같은 차례를 쓴다. */
    fun parkList(): List<Hidden> = missed().sortedBy { receivedAt(it) ?: Long.MAX_VALUE }

    /** 주차 화면에서 눌러 듣는다(C8): only가 있으면 그 메시지만, 없으면 목록 차례대로 이어서. 기어 P이고 다른 것이 안 나올 때만. 눌러서 고른 것이라 띵동·안내 없이 바로. */
    fun playMissed(only: String? = null): Boolean {
        val list = parkList().filter { only == null || it.id == only }
        if (list.isEmpty() || gear != VehicleGear.GEAR_PARK || !Hub.enabled(this) || player != null || replayMode || playing || asking != null || Hub.arrivalLeft > 0 || current != null) return false
        Hub.log("화면 [${if (only != null) "목록 줄" else "모두 듣기"}] → ${list.size}개 이어 듣기")
        Hub.parkHeard = emptyList()
        val chain = ++parkChain
        playParked(list, chain)
        return true
    }

    /** 화면이 주행으로 바뀌었다(플랫폼 제한 상태, C3): 정차 중 다시 듣기는 끝낸다(기어가 P가 아닌 정차에서 시작한 다시 듣기도). */
    fun stopReplay() { if (replayMode) { Hub.log("다시 듣기 중 주행 → 멈춤"); stopAudio(); releaseFocus() } }

    /** 주차해서 이어 듣는 중 [다음]: 지금 것은 넘긴 것으로 두고(들은 메시지 화면에서 골라 들을 수 있다) 다음 메시지로. */
    fun skipToNext() {
        val h = Hub.nowPlaying ?: return
        if (Hub.arrivalLeft <= 1 || replayMode || current?.id != h.id) return
        val rest = parkList.dropWhile { it.id != h.id }.drop(1)
        if (rest.isEmpty()) return
        Hub.log("[다음] → ${h.sender} 메시지 넘김")
        Hub.markSkipped(this, h)
        current = null
        finishAudio()   // 이어 듣는 중이라 소리 권한은 그대로 잡고 있다
        playing = false
        val chain = parkChain
        later(0) { playParked(rest, chain) }
    }

    /** 넘긴 메시지를 정차 중 화면에서 끝까지 들었다: 이제 들은 것으로 친다. */
    fun heardNow(h: Hidden) {
        Hub.markHeard(this, h)
        updateWaitNote()
        if (!Hub.demo && !h.example) bg { runCatching { Api.markPlayed(h.id, h.day) } }
        Hub.log("${h.sender} 메시지(넘긴 것) 끝까지 들음")
        Hub.changed()
    }

    /** 주행 화면 대기 개수 아래 한 줄(63번 4장). 깜빡임·숫자 없이.
     *  버튼을 누르고 안전할 때를 기다릴 때만 '잠시 후 들려드립니다', 주행 집중 모드로 주차까지 미뤘을 때만 '주차하면 들려드립니다'. 그냥 기다리는 중이면 없음.
     *  주차하면 저절로 나오는 건 주행 집중 모드뿐이라(C8) 다른 방식에서는 '주차하면'을 쓰지 않는다. */
    fun driveNote(): String? {
        if (gear != VehicleGear.GEAR_DRIVE || asking != null || Hub.nowPlaying != null) return null
        val pressed = current != null && Hub.waiting?.startsWith("누른 메시지") == true
        if (pressed) return "잠시 후 들려드립니다"
        if (Hub.listenMode(this) != "arrive") return null
        val later = Hub.today.any { it.id !in Hub.opened && it.id !in Hub.heard && it.id in Hub.occurredThisTrip }
        return if (later) "주차하면 들려드립니다" else null
    }

    /** 이번 운행에 들은 메시지 중 답장하지 않은 것이 있을 때만, 정차 중 화면에서 답장할 수 있다고 알림 센터에 남긴다(팝업 없음).
     *  제목은 확정 문구 꼴 '답장하지 않은 ○○님의 음성 메시지'(가장 최근 것, 이름을 숨길 때는 '답장하지 않은 음성 메시지'). 63번 4장. */
    private fun notifyReply() {
        if (heardThisTrip.isEmpty()) return   // 이번 운행에 새로 들은 게 없으면 같은 알림을 또 띄우지 않는다
        val m = Hub.unreplied(this).firstOrNull { it.id in heardThisTrip } ?: return
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).putExtra("open", "heard"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        nm.notify(2, Notification.Builder(this, "reply")
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(if (hideName()) "답장하지 않은 음성 메시지" else "답장하지 않은 ${nim(m.sender)}의 음성 메시지")
            .setContentIntent(open).setAutoCancel(true).build())
    }

    /** 반복 메시지를 오늘 들었으면 다음에도 들을지 묻는다(주행 중엔 묻지 않음). 알림은 따로 띄우지 않고
     *  주차 알림 한 장(notifyReply → 들은 메시지 화면)의 맨 위 카드로 묻는다. */
    private fun askRepeats() {
        nm.cancel(4)   // 예전 빌드가 남긴 '다음에도 들으시겠습니까?' 알림
        if (gear != VehicleGear.GEAR_PARK) return
        val ask = Hub.heardToday().filter { it.repeat == "each" && !it.example && !Hub.repeatAsked(this, it.id) } // 예시 메시지는 묻지 않는다
        if (ask.isEmpty()) return
        Hub.askRepeat = ask
        Hub.changed()
        Hub.log("주차: 반복 메시지 ${ask.size}개 계속 들을지 물어봄 (들은 메시지 화면 카드)")
    }

    private fun onWiper(value: WiperState?) {
        Hub.raining = value == WiperState.ON   // 광장 유리 돔(로그가 화면을 다시 그리므로 먼저 둔다)
        Hub.log("와이퍼 → $value")
        if (value == WiperState.ON) {
            if (wiperOnAt == 0L) wiperOnAt = SystemClock.elapsedRealtime()
            checkRainLater()
        } else wiperOnAt = 0L
    }

    /** 와이퍼가 일정 시간 넘게 켜져 있고 주행 중이면 '비' 순간 (출발 전부터 켜져 있던 경우도 포함). */
    private fun checkRainLater() = main.postDelayed({
        if (wiperOnAt != 0L && SystemClock.elapsedRealtime() - wiperOnAt >= RAIN_HOLD_MS - 50 && !rainFiredThisTrip &&
            gear == VehicleGear.GEAR_DRIVE && Hub.enabled(this)) {
            rainFiredThisTrip = true
            momentCame("rain", "비가 옵니다.")
        }
    }, RAIN_HOLD_MS)

    /** 지금 핸들 각도를 한 번 읽는다(바뀔 때만 오는 신호라 가만히 있으면 값이 안 올 수 있다). */
    private fun readSteer() {
        val v = vehicle ?: return
        runCatching { v.getSteeringWheel().getCurrentSteeringWheelAngle({ a: Float? -> a?.let { main.post { onSteer(it) } } }, { e: Exception -> main.post { Hub.log("조향 지금 값 못 읽음: $e") } }) }
            .onFailure { Hub.log("조향 지금 값 불가: $it") }
    }

    private fun onSteer(angle: Float) {
        val calmNow = abs(angle) <= STEER_CALM_DEG
        val calmBefore = abs(steerAngle) <= STEER_CALM_DEG
        if (calmNow && !calmBefore) steerCalmSince = SystemClock.elapsedRealtime()
        if (!steerSeen) { steerSeen = true; steerCalmSince = SystemClock.elapsedRealtime() }
        steerAngle = angle
    }

    // ---------- 안전 타이밍 ----------

    private val intros = mutableMapOf<String, String>()   // 순간 말("비가 옵니다."). 안내는 녹음 고정 문장이라 소리로는 쓰지 않는다(75번 B-2)
    /** 이번 운행에서 버튼 듣기 안내에 긴 녹음('들으시려면 핸들 가운데 버튼을 눌러 주세요')을 이미 썼는지(출발·주차 때 다시 처음부터). */
    private var wheelHintSaid = false

    private fun enqueue(h: Hidden, intro: String) {
        if (h.id in Hub.opened || h.id in deferredThisTrip || queue.any { it.id == h.id } || asking?.id == h.id) return
        if (Hub.listenMode(this) == "arrive") { Hub.log("순간 도착: ${h.sender} 메시지 → 주행 집중 모드라 주차해서"); Hub.changed(); return }
        intros[h.id] = intro
        if (queue.isEmpty()) waitingLogged = false   // 새로 기다리기 시작: 이유 한 줄을 다시 남긴다(지난 운행에서 기다리다 끝난 표시가 남아 기록이 빠지던 것)
        queue.addLast(h)
        Hub.log("순간 도착: ${h.sender} 메시지 대기열에 넣음")
        schedulePump(0)
    }

    /** 대기열 확인은 하나만 돈다(11/09 버그: 넣을 때·미룰 때마다 1초 확인을 새로 걸어 여러 개가 겹쳐 돌았다). */
    private val pumpTick = Runnable { pump() }
    private fun schedulePump(ms: Long = 1000) { main.removeCallbacks(pumpTick); main.postAtTime(pumpTick, playToken, SystemClock.uptimeMillis() + ms) }
    private var steerWaitSince = 0L

    /** 대기열이 있을 때만 1초마다 확인한다(대기열이 비면 멈춤). */
    private fun pump() {
        // 그사이 들었거나(정차 중 화면에서 들음·다시 듣기) 지워진 것은 꺼내지 않는다(11/09 버그: 같은 메시지를 또 알림)
        queue.removeAll { q -> q.id in Hub.opened || q.id in Hub.heard || Hub.today.none { it.id == q.id } }
        if (queue.isEmpty()) return
        if (!Hub.enabled(this)) { queue.clear(); Hub.waiting = null; Hub.changed(); return }   // 앱을 닫았거나 껐으면 틀지 않는다
        val reason = unsafeReason()
        // 핸들 각도 신호가 3초 넘게 안 오면 이번 운행엔 기다리지 않는다: 재생 예정에 남겨 주차해서 듣는다(11/09 결정)
        if (reason == NO_STEER) {
            val now = SystemClock.elapsedRealtime()
            if (steerWaitSince == 0L) steerWaitSince = now
            else if (now - steerWaitSince >= STEER_WAIT_MS) {
                Hub.log("핸들 각도 신호가 ${STEER_WAIT_MS / 1000}초 넘게 없음 → ${queue.size}개는 주차해서")
                queue.forEach { deferredThisTrip += it.id }; queue.clear(); steerWaitSince = 0L; waitingLogged = false
                Hub.waiting = null; Hub.changed(); return
            }
        } else steerWaitSince = 0L
        if (reason == null) {
            waitingLogged = false
            play(queue.removeFirst())
        } else {
            if (!waitingLogged) { Hub.log("잠시 후: $reason"); waitingLogged = true }
            Hub.waiting = reason
            Hub.changed()
        }
        if (queue.isNotEmpty()) schedulePump()
    }

    private fun unsafeReason(): String? {
        val now = SystemClock.elapsedRealtime()
        return when {
            playing || asking != null -> "다른 메시지 재생 중"
            importantSound() != null -> "${importantSound()} 중"
            gear != VehicleGear.GEAR_DRIVE -> "주행 중이 아님"
            !leftLot -> "주차장을 벗어나는 중 (${speedKph.toInt()}km/h)"
            roadReason() != null -> roadReason()
            else -> null
        }
    }

    /** 지금 소리를 내도 되는 도로 상황인지. D가 아니면(서 있으면) 보지 않는다. 버튼을 누른 뒤 재생 직전에도 다시 본다. */
    private val NO_STEER = "핸들 신호 없음"
    private var pressedSteerSince = 0L
    private fun roadReason(): String? {
        val now = SystemClock.elapsedRealtime()
        return when {
            importantSound() != null -> "${importantSound()} 중"
            gear != VehicleGear.GEAR_DRIVE -> null
            !steerSeen -> NO_STEER   // 신호가 안 오면 직진으로 치지 않는다(3초 넘으면 주차해서, pump)
            abs(steerAngle) > STEER_CALM_DEG -> "조향 중 (${steerAngle.toInt()}°)"
            now - steerCalmSince < STEER_CALM_MS -> "직진 확인 중"
            // 서 있어도(좌회전 신호 대기) 방향지시등이 켜져 있으면 기다린다: 신호가 바뀌는 순간과 겹치지 않게(11/08 C10, 예전엔 서 있으면 안 봄)
            turnOn -> "방향지시등 켜짐"
            turnOffAt != 0L && now - turnOffAt < TURN_CALM_MS -> "방향지시등 꺼진 뒤 대기"
            // 서 있다가 출발한 직후 5초는 새로 시작하지 않는다(C10)
            pullAwayAt != 0L && speedKph >= 1f && now - pullAwayAt < PULL_AWAY_MS -> "출발 직후"
            else -> null
        }
    }

    /** 버튼을 눌렀어도 그사이 핸들을 꺾었거나 깜빡이를 켰으면 풀릴 때까지 기다렸다 튼다. 주차하면 도착 재생으로 넘어간다. */
    private fun startWhenRoadClear(h: Hidden) {
        if (current?.id != h.id) return
        // 기다리는 사이 앱을 닫았거나 껐으면 틀지 않고 못 들은 것으로 남긴다
        if (!Hub.enabled(this)) { Hub.opened -= h.id; current = null; playing = false; Hub.waiting = null; Hub.changed(); return }
        val r = roadReason() ?: run { Hub.waiting = null; pressedSteerSince = 0L; return startVoice(h) }
        if (r == NO_STEER) {
            val now = SystemClock.elapsedRealtime()
            if (pressedSteerSince == 0L) pressedSteerSince = now
            else if (now - pressedSteerSince >= STEER_WAIT_MS) {
                // 버튼을 눌렀어도 직진인지 알 수 없으면 주행 중엔 틀지 않는다: 재생 예정에 남겨 주차해서
                Hub.log("누른 메시지 · 핸들 각도 신호가 ${STEER_WAIT_MS / 1000}초 넘게 없음 → ${h.sender} 메시지는 주차해서")
                pressedSteerSince = 0L
                Hub.opened -= h.id; deferredThisTrip += h.id; current = null; playing = false; Hub.waiting = null
                if (player == null && !chainFocus) releaseFocus()
                Hub.changed(); if (queue.isNotEmpty()) schedulePump()
                return
            }
        } else pressedSteerSince = 0L
        // 길이 트이길 기다리는 동안은 소리 권한을 쥐고 있지 않는다(음악이 오래 멈춰 있지 않게). 틀 때 다시 받는다
        if (player == null && !chainFocus) releaseFocus()
        val note = "누른 메시지 · $r"
        if (Hub.waiting != note) Hub.log("대기: $note")
        Hub.waiting = note; Hub.changed()
        later(1000) { startWhenRoadClear(h) }
    }

    /** 주행 중 안전할 때 한 번 실행(대기열과 같은 조건). 주차하면 버린다. */
    private fun whenSafe(what: String, block: () -> Unit) {
        val reason = if (playing) "다른 메시지 재생 중" else unsafeReason()
        if (gear != VehicleGear.GEAR_DRIVE) return
        if (!Hub.enabled(this)) { if (Hub.waiting?.startsWith(what) == true) { Hub.waiting = null; Hub.changed() }; return }   // 앱을 닫았거나 껐으면 안내도 하지 않는다
        if (reason == null) { Hub.waiting = null; block() }
        else {
            val note = "$what · $reason"
            if (Hub.waiting != note) Hub.log("대기: $note")
            Hub.waiting = note; Hub.changed(); later(1000) { whenSafe(what, block) }
        }
    }

    // ---------- 재생 ----------

    private var player: MediaPlayer? = null
    /** 기본은 잠깐 멈추기(음악이 3초 쉬었다 이어짐). 덕킹은 차마다 HAL 설정에 달려 있어 에뮬레이터에선 적용 안 됨. */
    var focusGain = AudioManager.AUDIOFOCUS_GAIN_TRANSIENT
    private var focus = buildFocus()
    private fun buildFocus() = AudioFocusRequest.Builder(focusGain)
        .setAudioAttributes(AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        .setOnAudioFocusChangeListener { change -> main.post { onFocusLost(change) } }.build()

    /** 다른 소리가 끼어들었다(줄여서 같이 내 달라는 경우도 바로 멈춘다: 기획 '다른 소리가 끼어들면 바로 멈춤'). */
    private fun onFocusLost(change: Int) {
        if (change != AudioManager.AUDIOFOCUS_LOSS && change != AudioManager.AUDIOFOCUS_LOSS_TRANSIENT && change != AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK) return
        // 띵동·안내·버튼 기다림 동안(아직 목소리 재생 전)은 권한만 놓친 것으로 본다: 안내 음성이 권한을 잠깐 가져가도 흐름을 끊지 않게. 재생 직전에 다시 받는다
        if (player == null) { focusHeld = false; return }
        chainFocus = false   // 아래 멈춤에서 소리 권한도 바로 돌려준다(되찾는 신호를 기다리지 않고 다시 틀 때 새로 받는다)
        val cut = current
        if (Hub.arrivalLeft > 0) {
            // 주차해서 이어 듣던 중: 이어 듣기를 여기서 끝낸다. 끊긴 것은 못 들은 것으로 남겨 다음 주차 때 다시(주행 대기열로는 보내지 않는다)
            Hub.log("다른 소리가 끼어들어 이어 듣기 멈춤 → 다음 주차 때")
            parkChain++; Hub.arrivalLeft = 0
            cut?.let { Hub.opened -= it.id }
            current = null
            stopAudio(); releaseFocus()
            Hub.changed()
            return
        }
        if (cut == null) { if (player != null) stopAudio(); releaseFocus(); return }   // 다시 듣기: 멈추기만
        Hub.log("다른 소리가 끼어들어 멈춤 → 끝나면 다시")
        stopAudio(); releaseFocus()
        current = null; Hub.opened -= cut.id
        if (gear == VehicleGear.GEAR_PARK) { Hub.changed(); return }   // 서 있을 때 끊긴 것은 그 순간 규칙대로 다시 기다린다
        // 다른 소리(내비 안내 등)에 두 번 끊기면 이번 주행엔 다시 틀지 않고 주차 후로(C10)
        val n = (cuts[cut.id] ?: 0) + 1
        cuts[cut.id] = n
        if (n >= MAX_CUTS) {
            Hub.log("${cut.sender} 메시지가 ${n}번 끊겨 주차 후로 미룸")
            deferredThisTrip += cut.id; playing = false; lastPlayAt = SystemClock.elapsedRealtime()
            Hub.changed(); if (queue.isNotEmpty()) schedulePump()
            return
        }
        // 이미 버튼을 눌러(또는 안내를 다 듣고) 듣던 것: 끼어든 소리가 끝나면 띵동·안내·버튼 묻기 없이 바로 이어 튼다
        retryDirect(cut, 1000)
    }

    /** 이미 듣기로 한 메시지를 다시 묻지 않고 튼다. 기다리는 동안은 재생 중으로 쳐서 다른 메시지가 끼어들지 않게. */
    private fun retryDirect(h: Hidden, ms: Long) {
        current = h; playing = true; Hub.opened += h.id
        later(ms) { startWhenRoadClear(h) }
    }

    private fun play(h: Hidden) {
        playing = true
        Hub.waiting = null
        Hub.opened += h.id
        Hub.changed()
        current = h
        if (Hub.listenMode(this) == "button") return ask(h)
        // 버튼 누르지 않아도 자동 재생: 띵동 → 한 줄 → 재생. 이름이 무엇이든(숫자·영문 포함) 조사가 틀리지 않는 말투
        // 띵동·안내가 나오는 사이 핸들을 꺾었거나 깜빡이를 켰을 수 있다: 버튼 듣기처럼 재생 직전에 다시 본다
        chimeThen { announce(Ann.ARRIVE) { startWhenRoadClear(h) } }
    }

    /** 버튼 듣기: 띵동 → 녹음 안내 → 안내가 끝난 뒤 8초 안에 핸들 가운데 버튼·알림 [듣기]면 재생. 묻지 않고 알리기만 한다. */
    private fun ask(h: Hidden) {
        asking = h
        Hub.askEndsAt = 0L; Hub.askWindowMs = LISTEN_WINDOW_MS   // 안내 음성이 나오는 동안 막대는 꽉 찬 채로
        Hub.offered = h; Hub.changed()
        Hub.log("버튼 듣기: ${h.sender} 메시지 알림")
        wheel().open { key -> Hub.log("핸들 버튼($key) → 듣기"); accept("핸들 버튼") }
        showAskCard(h)
        // 안내(75번 B-2): 녹음 고정 문장. 핸들 버튼 설명은 같은 운행에서 처음 한 번만(그 뒤는 짧은 것)
        val ann = if (wheelHintSaid) Ann.ARRIVE else Ann.ARRIVE_FIRST
        wheelHintSaid = true
        chimeThen {
            if (asking?.id != h.id) return@chimeThen
            announce(ann) {
                if (asking?.id == h.id) {
                    // 안내가 끝난 때부터 8초: 화면 카드의 남은 시간 막대가 이 시각을 보고 줄어든다
                    Hub.askEndsAt = SystemClock.elapsedRealtime() + LISTEN_WINDOW_MS
                    Hub.log("핸들 버튼 기다림 ${LISTEN_WINDOW_MS / 1000}초(남은 시간 막대)")
                    wheel().closeAfter(LISTEN_WINDOW_MS) { defer(h) }
                }
            }
        }
    }

    /** 운전자가 듣기를 골랐다(핸들 버튼·알림 버튼). 안내가 아직 나오는 중이면 끊고 바로 재생. */
    private fun accept(how: String) {
        val h = asking ?: return
        Hub.log("$how → ${h.sender} 메시지 재생")
        asking = null; Hub.offered = null; Hub.askEndsAt = 0L
        nm.cancel(3)
        annDone = null
        stopAnn()
        current = h
        startWhenRoadClear(h)
        wheel().close("듣기") // 목소리가 소리 권한을 먼저 잡은 뒤 닫아야 음악이 사이에 튀지 않는다
    }

    /** 정차 중 화면의 도착 장면 [듣기]/[나중에]. */
    fun listenNow() = accept("화면 [듣기]")
    fun later() = asking?.let { Hub.log("화면 [나중에]"); defer(it) }

    /** 대답이 없으면 조용히 끝내고 도착해서 들려준다. 이번 주행엔 다시 묻지 않는다. */
    private fun defer(h: Hidden) {
        if (asking?.id != h.id) return
        Hub.log(when {
            gear != VehicleGear.GEAR_PARK -> "대답 없음 → ${h.sender} 메시지는 재생 예정에 남김(주차해서)"
            h.moment == "start" -> "나중에 → ${h.sender} 메시지는 출발한 뒤 그 순간에"
            else -> "나중에 → ${h.sender} 메시지는 주차 목록에"
        })
        endAsking()
        Hub.opened -= h.id
        deferredThisTrip += h.id
        current = null
        playing = false
        if (player == null && !chainFocus) releaseFocus()   // 띵동 때 잡은 소리 권한(듣지 않았으니 바로 돌려준다)
        lastPlayAt = SystemClock.elapsedRealtime()
        Hub.changed()
        if (queue.isNotEmpty()) schedulePump()
    }

    private fun endAsking() {
        val h = asking ?: return
        asking = null; Hub.offered = null; Hub.askEndsAt = 0L
        nm.cancel(3)
        wheel?.close("끝")
        if (current?.id == h.id) { Hub.opened -= h.id; current = null; playing = false }
        if (player == null && !chainFocus && current == null) releaseFocus()
    }

    private fun showAskCard(h: Hidden) {
        if (Hub.visible) return // 앱이 보이면 화면의 큰 듣기 버튼이 대신한다
        val listen = PendingIntent.getForegroundService(this, 3, Intent(this, CarService::class.java).putExtra("cmd", "listen"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        nm.notify(3, Notification.Builder(this, "ask")
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(whose(h))
            .setContentText("핸들 가운데 버튼으로 듣기")
            .setCategory(Notification.CATEGORY_MESSAGE)
            .setTimeoutAfter(LISTEN_WINDOW_MS + 6_000)
            .setContentIntent(listen)   // 본문을 눌러도 듣기(운전 중엔 큰 본문이 작은 버튼보다 쉽다)
            .addAction(Notification.Action.Builder(null, "듣기", listen).build())
            .apply {
                // 차가 서 있을 때(출발 전)는 [나중에]도 준다. 주행 중엔 버튼 하나만(안 누르면 저절로 나중에).
                if (gear == VehicleGear.GEAR_PARK) addAction(Notification.Action.Builder(null, "나중에",
                    PendingIntent.getForegroundService(this@CarService, 4, Intent(this@CarService, CarService::class.java).putExtra("cmd", "later"), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)).build())
            }
            .setAutoCancel(true).build())
    }

    private fun wheel() = wheel ?: WheelWindow(this).also { wheel = it }

    /** 이름을 숨길 때. 동승자 이름 숨기기(프라이빗 모드)는 11/10에 뺐다: 운전에 맞춘 건 주행 집중 모드 하나로 둔다. */
    fun hideName() = false
    fun whose(h: Hidden) = if (hideName()) "음성 메시지" else "${nim(h.sender)} 메시지"

    /** 띵동을 울리고 끝나면 다음으로. */
    private fun chimeThen(then: () -> Unit) {
        importantSound()?.let { busy -> Hub.waiting = "$busy 중"; Hub.changed(); later(1000) { chimeThen(then) }; return }
        // 띵동부터 소리 권한을 잡고 재생이 끝날 때까지 쥔다(Pleos: 재생 전에 포커스 요청, 11/08 C10). 못 받아도 흐름은 그대로(재생 직전에 다시 받는다)
        if (!focusHeld) focusHeld = am.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        Hub.log("띵동")
        Chime.play()
        later(Chime.LENGTH_MS + 200, then)
    }

    private fun startVoice(h: Hidden) {
        playing = true
        current = h
        Hub.opened += h.id
        // 출발 전(P)에 들은 차 탈 때 메시지는 주행 중 하루 5개에 넣지 않는다
        val inDrive = gear != VehicleGear.GEAR_PARK
        playAudio(h, onFail = {
            current = null
            if (gaveUp(h)) { playing = false; Hub.changed(); schedulePump(0) }
            else if (gear == VehicleGear.GEAR_PARK) { Hub.opened -= h.id; playing = false; Hub.changed() }   // 서 있을 때 못 튼 것은 그 순간 규칙대로 다시 기다린다
            else retryDirect(h, 3000)   // 이미 누른 것: 다시 묻지 않고 3초 뒤 바로
        }, onDone = {
            lastPlayAt = SystemClock.elapsedRealtime()
            playing = false
            current = null
            if (inDrive) { drivePlayed += LocalDate.now().toString() to h.id; saveDrivePlayed() }
            heardThisTrip += h.id; lastSender = h.sender
            Hub.markHeard(this, h)
            updateWaitNote()
            if (!Hub.demo && !h.example) bg { runCatching { Api.markPlayed(h.id, h.day) } }
            Hub.log("${h.sender} 메시지 재생 끝")
            Hub.changed()
        })
    }

    /** 정차 중 화면에서 들은 메시지를 다시 들을 때. onFail: 못 틀었을 때(인터넷 없음·파일 없음) 화면이 이유를 알리게.
     *  다른 것이 나오는 중(재생·알림·이어 듣기·다시 듣기 준비)이면 겹쳐 틀지 않는다. 틀었으면 true. */
    fun replay(h: Hidden, onFail: (() -> Unit)? = null, onDone: () -> Unit): Boolean {
        if (player != null || replayMode || playing || asking != null || Hub.arrivalLeft > 0 || current != null) { Hub.log("다른 메시지가 나오는 중이라 다시 듣기 안 함"); return false }
        replayMode = true; replayFail = onFail; playAudio(h, onDone = onDone); return true
    }
    private var replayMode = false   // 정차 중 다시 듣기(출발하면 바로 끝낸다)
    private var replayFail: (() -> Unit)? = null
    private var wheelForStop = false // 듣는 동안 핸들 버튼을 '멈춤'으로 받는 중

    /** 듣는 중에 멈춤(화면 멈춤 버튼·핸들 버튼 한 번 더·뒤로). 처음 듣던 메시지는 못 들은 것으로 남겨 주차할 때 다시 들려준다. */
    fun stopListening(why: String) {
        val h = Hub.nowPlaying ?: current ?: return
        Hub.log("$why → ${h.sender} 메시지 멈춤")
        // 멈춘 뒤 어떻게 되는지 화면 아래 토스트로(주행 중엔 화면이 '주차하면 들려드립니다'로 대신 알린다)
        // 63번 4장: 주행 집중 모드나 주차해서 이어 듣던 주차했을 때 메시지만 '주차하면 다시 들려드립니다'. 나머지는 토스트 없음
        // (다음 주차 때 저절로 나오는 건 주차했을 때 메시지와 주행 집중 모드뿐, C8. 나머지는 주차 화면에서 다시 눌러 듣는다)
        Hub.stopNote = when {
            replayMode -> null
            Hub.listenMode(this) == "arrive" || (Hub.arrivalLeft > 0 && h.moment == "arrive") -> "주차하면 다시 들려드립니다"
            else -> null
        }
        if (Hub.arrivalLeft > 0) { parkChain++; Hub.arrivalLeft = 0 }   // 주차해서 이어 듣던 것도 여기서 그만
        if (!replayMode) {
            Hub.opened -= h.id
            if (gear == VehicleGear.GEAR_DRIVE) deferredThisTrip += h.id   // 주행 중이면 도착해서
        }
        current = null
        replayFail = null   // 멈춘 다시 듣기는 실패가 아니다
        stopAudio(); releaseFocus()
        lastPlayAt = SystemClock.elapsedRealtime()
        Hub.changed()
    }

    private var focusHeld = false
    private var chainFocus = false
    private fun releaseFocus() { if (focusHeld) am.abandonAudioFocusRequest(focus); focusHeld = false }

    private fun playAudio(h: Hidden, onFail: (() -> Unit)? = null, onDone: () -> Unit) {
        val r = if (focusHeld) AudioManager.AUDIOFOCUS_REQUEST_GRANTED else am.requestAudioFocus(focus)
        focusHeld = r == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        if (r != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            Hub.log("소리 권한 못 받음($r) → 3초 뒤 다시")
            playing = false; Hub.opened -= h.id
            if (onFail == null) { replayMode = false; replayFail?.also { replayFail = null }?.invoke() } // 다시 듣기
            onFail?.invoke(); return
        }
        Hub.log("${h.sender} 메시지 재생 (음악은 잠깐 멈춤)")
        later(PREROLL_MS) {
            runCatching {
                // 앞 재생기가 남아 있으면 먼저 푼다(두 목소리가 겹치거나 재생기가 새지 않게)
                player?.let { old -> Hub.log("앞 재생기 정리"); runCatching { old.release() }; player = null; prepared = false }
                player = MediaPlayer().apply {
                    setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    val local = Store.audioFile(this@CarService, h)
                    if (local.exists() && local.length() > 0) setDataSource(local.absolutePath) else setDataSource(Api.audioUrl(h.audioPath))
                    setOnPreparedListener {
                        it.start(); prepared = true; Hub.nowPlaying = h; Hub.paused = false
                        if (h.id != "test") Hub.setLen(this@CarService, h.id, it.duration)
                        showPlaying(h)
                        Hub.changed()
                        // 듣는 동안 핸들 가운데 버튼을 한 번 더 누르면 멈춘다
                        wheelForStop = true; wheel().open { stopListening("핸들 버튼") }
                    }
                    setOnCompletionListener { replayFail = null; finishAudio(); onDone() }
                    setOnErrorListener { _, what, extra -> Hub.log("재생 오류 $what/$extra"); finishAudio(); failed(h, onFail, onDone); true }
                    prepareAsync()
                }
            }.onFailure { Hub.log("재생 실패: $it"); finishAudio(); failed(h, onFail, onDone) }
        }
    }

    private val playFails = mutableMapOf<String, Int>()
    private val cuts = mutableMapOf<String, Int>()   // 메시지별로 다른 소리에 끊긴 횟수(C10)
    /** 재생이 깨지면 들은 걸로 치지 않는다. 같은 메시지가 두 번 깨지면 오늘은 건너뛴다(목록에는 남아 다음 날·다시 받기 때 다시 시도). */
    private fun failed(h: Hidden, onFail: (() -> Unit)?, onDone: () -> Unit) {
        playing = false
        // 정차 중 다시 듣기: 화면이 이유를 알리게 하고(그 메시지 화면에 남음), 없으면 화면만 되돌린다
        if (onFail == null) { val f = replayFail; replayFail = null; return if (f != null) f() else onDone() }
        val n = (playFails[h.id] ?: 0) + 1
        playFails[h.id] = n
        if (n >= 2) Hub.log("${h.sender} 메시지 재생이 두 번 깨져 오늘은 건너뜀") else Hub.opened -= h.id
        onFail()
    }
    private fun gaveUp(h: Hidden) = (playFails[h.id] ?: 0) >= 2

    /** 정차 중 화면의 재생 막대: (지금 ms, 전체 ms). */
    // 준비가 끝나기 전에 위치를 물으면 MediaPlayer가 오류(-38)를 내고 재생이 끊긴다(실측) → 준비된 뒤에만
    fun progress(): Pair<Int, Int>? = player?.takeIf { prepared }?.let { p -> runCatching { p.currentPosition to p.duration }.getOrNull() }
    private var prepared = false

    /** 정차 중 화면의 일시정지 버튼. */
    fun togglePause() {
        val p = player?.takeIf { prepared } ?: return
        runCatching { if (p.isPlaying) { p.pause(); Hub.paused = true } else { p.start(); Hub.paused = false } }
        Hub.changed()
    }

    /** 재생하는 동안만 알림 줄에 [멈추기](앱이 안 보일 때 화면으로도 멈출 수 있게). 끝나면 지운다. */
    private fun showPlaying(h: Hidden) {
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val stop = PendingIntent.getForegroundService(this, 5, Intent(this, CarService::class.java).putExtra("cmd", "stop"), flags)
        val open = PendingIntent.getActivity(this, 5, Intent(this, MainActivity::class.java), flags)
        nm.notify(5, Notification.Builder(this, "playing")
            .setSmallIcon(R.drawable.ic_notify)
            .setContentTitle(if (hideName()) "음성 메시지 재생 중" else "${nim(h.sender)} 메시지 재생 중")
            .setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(null, "멈추기", stop).build())
            .build())
    }

    private fun finishAudio() {
        nm.cancel(5)
        if (wheelForStop) { wheelForStop = false; wheel?.close("재생 끝") }
        replayMode = false
        prepared = false
        runCatching { player?.release() }
        player = null
        if (Hub.nowPlaying != null) { Hub.nowPlaying = null; Hub.paused = false; Hub.changed() }
        if (!chainFocus) releaseFocus()
    }

    private fun stopAudio() {
        if (player != null) Hub.log("재생 중단")
        chainFocus = false
        finishAudio()
        playing = false
    }

    // ---------- 안내 녹음 (75번 B-2) ----------
    // 실시간 TTS는 쓰지 않는다: 이름을 제대로 못 읽고, 에뮬레이터 TTS는 소리도 안 난다(11/10 사용자 결정).
    // 이름·순간·숫자 없는 고정 문장 4개를 미리 녹음해 res/raw/ann_*.m4a로 넣는다. 파일이 없으면 띵동만(그 뒤 할 일은 그대로 이어진다).

    private var ann: MediaPlayer? = null
    private var annFocus = false   // 이 안내가 소리 권한을 새로 잡았는지(출발 안내처럼 띵동 없이 나올 때). 끝나면 돌려준다

    private fun announce(a: Ann, then: (() -> Unit)? = null) {
        importantSound()?.let { busy ->
            Hub.waiting = "$busy 중"; Hub.changed()
            later(1000) { announce(a, then) }; return
        }
        // 앞 안내가 아직 끝나지 않았으면 끝날 때까지 기다린다: 덮어쓰면 앞 안내 뒤에 할 일이 사라진다
        if (annDone != null) { later(300) { announce(a, then) }; return }
        val id = resources.getIdentifier(a.raw, "raw", packageName)
        // 출발 안내는 원래 띵동이 없다: 녹음이 없으면 조용히 넘어간다
        if (id == 0) { Hub.log("안내: \"${a.text}\" (${a.raw} 녹음 없음 → ${if (a == Ann.DEPART) "조용히 넘어감" else "띵동만"})"); then?.invoke(); return }
        Hub.log("안내: \"${a.text}\" (${a.raw})")
        if (!focusHeld) { focusHeld = am.requestAudioFocus(focus) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED; annFocus = focusHeld }
        val token: () -> Unit = then ?: {}
        annDone = token
        runCatching {
            val fd = resources.openRawResourceFd(id)
            ann = MediaPlayer().apply {
                setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                setDataSource(fd.fileDescriptor, fd.startOffset, fd.length); fd.close()
                setOnCompletionListener { main.post { annFinished() } }
                setOnErrorListener { _, w, e -> Hub.log("안내 녹음 오류 $w/$e"); main.post { annFinished() }; true }
                prepare(); start()
            }
        }.onFailure { Hub.log("안내 녹음 실패: $it"); annFinished() }
        // 끝 신호가 안 오면(오디오 장치 없음 등) 가장 긴 녹음(약 6초)보다 넉넉히 기다렸다가 다음으로
        later(9000) { if (annDone === token) { Hub.log("안내 끝 신호 없음 → 다음으로"); annFinished() } }
    }

    private fun annFinished() {
        ann?.let { runCatching { it.release() } }; ann = null
        if (annFocus) { annFocus = false; if (player == null && !chainFocus && asking == null && current == null) releaseFocus() }
        val cb = annDone; annDone = null; cb?.invoke()
    }

    /** 안내를 끊는다(뒤에 할 일은 부르지 않는다: 부르는 쪽이 annDone을 먼저 비운다). */
    private fun stopAnn() {
        ann?.let { runCatching { it.stop() }; runCatching { it.release() } }; ann = null
        annFocus = false
    }

    /** 뒤에서 대기 알림 한 장. 대기 개수는 제목 줄에만 쓴다: 이 차의 알림판(어두운 목록)은 앱 알림의 본문을 어두운 글씨로 그려 보이지 않는다.
     *  제목 줄은 흰 글씨라 보인다. 위에 뜨는 알림(흰 카드)의 본문은 보인다(에뮬레이터 실측 11/06, 앱 테마를 바꿔도 같았다). */
    private fun waitNotification(text: String?) = Notification.Builder(this, "wait")
        .setSmallIcon(R.drawable.ic_notify)
        .setContentTitle(text ?: "도담도담")
        .setOngoing(true)
        .build()
}
