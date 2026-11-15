package ai.simeodum.car

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.URL
import java.time.LocalDate

/** 오프라인 대비: 오늘 메시지 목록과 목소리 파일을 차에 저장한다. */
object Store {
    private fun dir(c: Context) = File(c.filesDir, "voices").apply { mkdirs() }
    /** 파일 이름에 녹음 이름까지 넣는다: 같은 메시지를 다시 녹음하면(id는 그대로, 녹음 이름이 바뀜) 새로 받는다. */
    fun audioFile(c: Context, h: Hidden) = File(dir(c), "${h.id}_${audioKey(h)}.${h.audioPath.substringAfterLast('.', "bin")}")
    private fun audioKey(h: Hidden) = h.audioPath.substringAfterLast('/').substringBeforeLast('.').filter { it.isLetterOrDigit() }.take(40)

    /** 남긴 사람 사진(판 번호마다 한 장). 사진을 바꾸면 판 번호가 바뀌어 새로 받는다. */
    private fun photoDir(c: Context) = File(c.filesDir, "photos").apply { mkdirs() }
    fun photoFile(c: Context, v: String) = File(photoDir(c), "${v.filter { it.isLetterOrDigit() }}.jpg")

    /** 캐릭터 얼굴 그림(판 번호마다 한 장). 캐릭터를 바꾸면 판 번호가 바뀌어 새로 받는다. */
    private fun bustDir(c: Context) = File(c.filesDir, "busts").apply { mkdirs() }
    fun bustFile(c: Context, v: String) = File(bustDir(c), "${v.filter { it.isLetterOrDigit() }}.img")
    /** 얼굴 그림을 받아 두고, 목록에 없는 그림(바꿈·끊음)은 지운다. 백그라운드 스레드에서 부른다. */
    fun syncBusts(c: Context, invites: List<Invite>) {
        invites.forEach { i ->
            val v = i.bust ?: return@forEach
            val f = bustFile(c, v)
            if (f.exists()) return@forEach
            runCatching {
                val part = File(f.path + ".part")
                part.writeBytes(Api.bust(i.code, v))
                part.renameTo(f) || run { part.delete(); false }
            }.onFailure { File(f.path + ".part").delete() }
        }
        val keep = invites.mapNotNull { it.bust?.let { v -> bustFile(c, v).name } }.toSet()
        bustDir(c).listFiles()?.filter { it.name !in keep }?.forEach { it.delete() }
    }

    /** 사진을 받아 둔다(이미 있으면 그대로). 백그라운드 스레드에서 부른다. 받았으면 true. */
    fun fetchPhoto(c: Context, invite: String?, v: String?): Boolean {
        if (invite == null || v == null) return false
        val f = photoFile(c, v)
        if (f.exists()) return false
        return runCatching {
            val part = File(f.path + ".part")
            part.writeBytes(Api.photo(invite, v))
            part.renameTo(f) || run { part.delete(); false }
        }.getOrElse { File(f.path + ".part").delete(); false }
    }

    /** 이 차의 초대 링크 목록을 막 받았을 때: 거기 없는 사진(지웠거나 바꿨거나 끊은 사람)은 차에서도 지운다. */
    fun keepPhotos(c: Context, invites: List<Invite>) {
        val keep = invites.mapNotNull { it.photo?.let { v -> photoFile(c, v).name } }.toSet()
        photoDir(c).listFiles()?.filter { it.name !in keep }?.forEach { it.delete() }
    }

    /** 백그라운드 스레드에서 부른다. */
    fun saveToday(c: Context, list: List<Hidden>) {
        list.map { it.invite to it.photo }.distinct().forEach { (i, v) -> fetchPhoto(c, i, v) }
        list.filter { !it.done }.forEach { h ->
            val f = audioFile(c, h)
            // 다시 녹음되기 전의 파일(같은 id, 예전 녹음 이름)은 바로 지운다
            dir(c).listFiles()?.filter { (it.name.startsWith("${h.id}_") || it.name.startsWith("${h.id}.")) && it.name != f.name && !it.name.endsWith(".part") }?.forEach { it.delete() }
            // 끊기면 반쪽 파일이 남지 않게 임시 파일로 받은 뒤 이름을 바꾼다. 오래 매달리지 않게 시간 제한
            if (!f.exists()) runCatching {
                val part = File(f.path + ".part")
                val con = URL(Api.audioUrl(h.audioPath)).openConnection().apply { connectTimeout = 5_000; readTimeout = 10_000 }
                con.getInputStream().use { i -> part.outputStream().use { i.copyTo(it) } }
                if (!part.renameTo(f)) part.delete()
            }.onFailure { File(f.path + ".part").delete() }
        }
        val arr = JSONArray(list.map {
            JSONObject().put("id", it.id).put("sender", it.sender).put("moment", it.moment)
                .put("audio", it.audioPath).put("played", it.played).put("done", it.done).put("repeat", it.repeat).put("date", it.pickedDate)
                .put("invite", it.invite).put("photo", it.photo).put("stopped", it.stopped)
                .put("place", it.place?.let { p -> JSONObject().put("lat", p.lat).put("lon", p.lon).put("name", p.name) })
        })
        c.getSharedPreferences("sim", Context.MODE_PRIVATE).edit()
            .putString("cacheDate", list.firstOrNull()?.day ?: LocalDate.now().toString()).putString("cache", arr.toString()).apply()
        // 지난 날 파일 정리
        val keep = list.map { audioFile(c, it).name }.toSet()
        dir(c).listFiles()?.filter { it.name !in keep && System.currentTimeMillis() - it.lastModified() > 2 * 86_400_000L }?.forEach { it.delete() }
    }

    fun loadToday(c: Context): List<Hidden>? {
        val p = c.getSharedPreferences("sim", Context.MODE_PRIVATE)
        val day = p.getString("cacheDate", null)
        if (day != LocalDate.now().toString()) return null
        val arr = JSONArray(p.getString("cache", "[]"))
        return (0 until arr.length()).map { arr.getJSONObject(it) }.map {
            Hidden(it.getString("id"), it.getString("sender"), it.getString("moment"), it.getString("audio"), it.getBoolean("played"), it.getBoolean("done"), it.optString("repeat", "once"), it.optString("date").ifEmpty { null }, placeOf(it.optJSONObject("place")),
                stopped = it.optBoolean("stopped"), invite = it.str("invite"), photo = it.str("photo"), day = day)
        }
    }
}
