package ai.simeodum.car

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import kotlin.concurrent.thread

/**
 * '버튼 듣기': 띵동이 울린 뒤 잠깐 동안만 핸들 가운데 버튼을 받는다.
 * 핸들 버튼은 '지금 소리 내는 앱'으로 가므로, 창이 열린 동안 알림 용도 무음을 흘려 우리 앱으로 오게 한다.
 * 미디어 세션 상태는 PLAYING으로 두면 안 된다: 시스템이 원래 음악을 멈추고, 닫은 뒤 핸들 버튼이 아무 데도 안 간다(실측 10/29).
 */
class WheelWindow(private val ctx: Context) {
    private val main = Handler(Looper.getMainLooper())
    private val am = ctx.getSystemService(AudioManager::class.java)
    private var session: MediaSession? = null
    private var track: AudioTrack? = null
    private var focus: AudioFocusRequest? = null
    @Volatile private var running = false
    private var onPress: ((String) -> Unit)? = null
    private var onTimeout: (() -> Unit)? = null

    val isOpen get() = session != null

    private companion object {
        val CENTER_KEYS = setOf(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PAUSE,
            KeyEvent.KEYCODE_HEADSETHOOK, KeyEvent.KEYCODE_DPAD_CENTER)
    }

    /** 창을 연다. 닫는 시각은 closeAfter로 정한다(안내가 끝난 뒤부터 센다). */
    fun open(onPress: (String) -> Unit) {
        close("다시 열기")
        this.onPress = onPress
        startSilence()
        session = MediaSession(ctx, "simeodum-wheel").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onMediaButtonEvent(i: Intent): Boolean {
                    @Suppress("DEPRECATION") val e = i.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT) ?: return false
                    // 가운데 버튼(재생/정지 계열)만 받는다. 다음·이전 곡 같은 다른 핸들 버튼은 듣기로 치지 않는다(연습 화면도 같은 키: 실측 KEYCODE_MEDIA_PLAY_PAUSE)
                    if (e.keyCode !in CENTER_KEYS) return false
                    // 한 번 누르면 듣기. 길게 눌러 반복되는 신호는 무시
                    if (e.action == KeyEvent.ACTION_DOWN && e.repeatCount == 0) {
                        val cb = this@WheelWindow.onPress
                        // 목소리가 소리 권한을 먼저 잡은 뒤 닫아야 음악이 사이에 튀지 않는다
                        main.post { cb?.invoke(KeyEvent.keyCodeToString(e.keyCode)); close("버튼 받음") }
                    }
                    return true
                }
            })
            setPlaybackState(PlaybackState.Builder()
                .setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_PAUSE)
                .setState(PlaybackState.STATE_NONE, 0, 1f).build())
            isActive = true
        }
        Hub.log("핸들 가운데 버튼 받는 중")
    }

    fun closeAfter(ms: Long, onTimeout: () -> Unit) {
        if (!isOpen) return
        this.onTimeout = onTimeout
        main.removeCallbacksAndMessages(null)
        main.postDelayed({ val cb = this.onTimeout; close("${ms / 1000}초 지남"); cb?.invoke() }, ms)
    }

    fun close(why: String) {
        main.removeCallbacksAndMessages(null)
        onPress = null; onTimeout = null
        val had = session != null
        session?.run { isActive = false; release() }
        session = null
        running = false
        track?.let { runCatching { it.stop(); it.release() } }
        track = null
        focus?.let { am.abandonAudioFocusRequest(it) }
        focus = null
        if (had) Hub.log("핸들 버튼 받기 끝 ($why)")
    }

    private fun startSilence() {
        val attrs = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
        focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK).setAudioAttributes(attrs).build().also { am.requestAudioFocus(it) }
        val sr = 22050
        val buf = AudioTrack.getMinBufferSize(sr, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val t = AudioTrack.Builder().setAudioAttributes(attrs)
            .setAudioFormat(AudioFormat.Builder().setSampleRate(sr).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setBufferSizeInBytes(buf * 2).setTransferMode(AudioTrack.MODE_STREAM).build()
        track = t
        t.play()
        running = true
        thread(name = "wheel-silence") {
            val silence = ShortArray(buf)
            while (running) t.write(silence, 0, silence.size)
        }
    }
}
