package com.ggotai.hp.manager

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.work.WorkManager
import com.ggotai.hp.worker.ResendWorker

/**
 * 기기 승인취소(서버가 upload-call에서 401 AUTH_ERR 반환) 상태를 관리한다.
 * 승인취소가 확정되면 백그라운드 수집을 멈추고 사용자에게 1회 안내한다.
 */
object DeviceStatus {
    private const val TAG = "DeviceStatus"
    private const val PREFS = "app_prefs"
    private const val KEY_REVOKED = "DEVICE_REVOKED"
    private const val CHANNEL_ID = "DeviceRevokeChannel"
    private const val NOTIFICATION_ID = 2

    fun isRevoked(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_REVOKED, false)

    fun clearRevoked(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(KEY_REVOKED, false).apply()
        Log.d(TAG, "revoked 플래그 해제")
    }

    /**
     * 승인취소를 기록한다. false→true 전이일 때만 주기 워커 취소 + 1회 안내를 수행한다.
     * @return 이번 호출로 새로 취소 상태가 된 경우 true, 이미 취소 상태였으면 false.
     */
    fun markRevoked(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getBoolean(KEY_REVOKED, false)) return false  // 이미 취소 → 반복 안내 방지

        prefs.edit().putBoolean(KEY_REVOKED, true).apply()
        Log.d(TAG, "기기 승인취소 감지 → 수집 중단")

        // 주기 재전송 워커 취소
        WorkManager.getInstance(context).cancelUniqueWork(ResendWorker.UNIQUE_NAME)

        // use_notification=N이면 음성/알림 모두 생략 (playTtsError와 동일 정책)
        if (prefs.getString("USE_NOTIFICATION", "Y") != "N") {
            UploadManager.speak("이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다.")
            notifyUser(context)
        }
        return true
    }

    private fun notifyUser(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "기기 승인 안내", NotificationManager.IMPORTANCE_HIGH)
            )
        }
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle("녹음 수집 중단")
            .setContentText("이 기기는 승인이 취소되어 녹음 수집이 중단되었습니다. 관리자에게 문의하세요.")
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setAutoCancel(true)
            .build()
        nm.notify(NOTIFICATION_ID, notification)
    }
}
