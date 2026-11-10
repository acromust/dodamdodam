package ai.simeodum.car

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * 띵동: 0.5초짜리 부드러운 두 음(올라가는 E5 → A5). 천천히 커지고 천천히 줄어서 경고음·초인종처럼 들리지 않게.
 * 질문할 때도 재생할 때도 같은 소리 하나만 쓴다.
 */
object Chime {
    const val LENGTH_MS = 520L
    private const val SR = 22050

    private val pcm: ShortArray by lazy {
        val notes = listOf(659.25 to 0.22, 880.0 to 0.30) // (Hz, 초)
        val out = ArrayList<Short>()
        notes.forEach { (hz, sec) ->
            val n = (SR * sec).toInt()
            val fade = (SR * 0.06).toInt() // 60ms에 걸쳐 커지고 줄어든다
            for (i in 0 until n) {
                val env = min(1.0, min(i / fade.toDouble(), (n - i) / (fade * 2.0)))
                out += (sin(2 * PI * hz * i / SR) * env * 0.35 * Short.MAX_VALUE).toInt().toShort()
            }
        }
        out.toShortArray()
    }

    /** 알림 용도로 재생한다. 끝나는 시각은 호출한 쪽이 LENGTH_MS로 맞춘다(오디오 장치가 없어도 흐름이 멈추지 않게). */
    fun play() = runCatching {
        val t = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(SR).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
            .setBufferSizeInBytes(pcm.size * 2).setTransferMode(AudioTrack.MODE_STATIC).build()
        t.write(pcm, 0, pcm.size)
        t.setNotificationMarkerPosition(pcm.size)
        t.setPlaybackPositionUpdateListener(object : AudioTrack.OnPlaybackPositionUpdateListener {
            override fun onMarkerReached(track: AudioTrack) { track.release() }
            override fun onPeriodicNotification(track: AudioTrack) {}
        })
        t.play()
        // 오디오 장치가 없어 끝 표시가 안 와도 풀어 준다
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({ runCatching { t.release() } }, LENGTH_MS + 1500)
    }.onFailure { Hub.log("띵동 재생 실패: $it") }
}
