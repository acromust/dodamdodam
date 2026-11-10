package ai.simeodum.car

import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import java.io.File
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.max

/**
 * 목소리 파일에서 높낮이(막대 N개, 0~1)를 뽑는다. 튜닝 눈금이 '그 사람 목소리 모양'으로 솟을 때 쓴다.
 * 파일을 끝까지 PCM으로 풀어 구간별 최대값을 잰다(5초짜리라 금방 끝남). 백그라운드 스레드에서 부른다.
 */
object Peaks {
    private val cache = mutableMapOf<String, FloatArray>()

    fun cached(id: String) = synchronized(cache) { cache[id] }

    fun of(id: String, file: File, n: Int = 28): FloatArray? {
        cached(id)?.let { return it }
        val r = runCatching { decode(file, n) }.getOrNull() ?: return null
        synchronized(cache) { cache[id] = r }
        return r
    }

    private fun decode(file: File, n: Int): FloatArray {
        val ex = MediaExtractor().apply { setDataSource(file.absolutePath) }
        val track = (0 until ex.trackCount).first { ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }
        ex.selectTrack(track)
        val fmt = ex.getTrackFormat(track)
        val codec = MediaCodec.createDecoderByType(fmt.getString(MediaFormat.KEY_MIME)!!)
        codec.configure(fmt, null, null, 0); codec.start()
        val samples = ArrayList<Short>(200_000)
        val info = MediaCodec.BufferInfo()
        var inDone = false; var outDone = false
        while (!outDone) {
            if (!inDone) {
                val i = codec.dequeueInputBuffer(5_000)
                if (i >= 0) {
                    val buf = codec.getInputBuffer(i)!!
                    val size = ex.readSampleData(buf, 0)
                    if (size < 0) { codec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM); inDone = true }
                    else { codec.queueInputBuffer(i, 0, size, ex.sampleTime, 0); ex.advance() }
                }
            }
            val o = codec.dequeueOutputBuffer(info, 5_000)
            if (o >= 0) {
                val out = codec.getOutputBuffer(o)!!.order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                // 채널이 둘이어도 높낮이 모양만 보면 되므로 그대로 섞어 읽는다
                var k = 0
                while (out.hasRemaining()) { val s = out.get(); if (k++ % 4 == 0) samples += s }
                codec.releaseOutputBuffer(o, false)
                if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outDone = true
            }
        }
        codec.stop(); codec.release(); ex.release()
        if (samples.isEmpty()) return FloatArray(n) { 0.2f }
        val step = max(1, samples.size / n)
        val peaks = FloatArray(n) { b ->
            var m = 0
            for (j in b * step until minOf(samples.size, (b + 1) * step)) m = max(m, abs(samples[j].toInt()))
            m.toFloat()
        }
        val top = peaks.maxOrNull()?.takeIf { it > 0 } ?: 1f
        // 너무 낮은 막대는 살짝 올려 모양이 보이게
        return FloatArray(n) { 0.12f + 0.88f * (peaks[it] / top) }
    }
}
