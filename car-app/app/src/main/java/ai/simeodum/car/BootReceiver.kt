package ai.simeodum.car

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** 차가 켜지면(부팅) 운전자가 앱을 열지 않아도 뒤에서 대기를 시작한다. 재생 기능을 켠 경우에만. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!Hub.enabled(context)) return
        context.startForegroundService(Intent(context, CarService::class.java))
    }
}
