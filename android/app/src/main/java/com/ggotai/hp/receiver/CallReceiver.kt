package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.telephony.TelephonyManager
import android.util.Log
import com.ggotai.hp.service.RecordingService
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.worker.CallSyncWorker
import java.util.concurrent.TimeUnit

class CallReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CallReceiver"
        private var lastState = TelephonyManager.CALL_STATE_IDLE
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == TelephonyManager.ACTION_PHONE_STATE_CHANGED) {
            val stateStr = intent.extras?.getString(TelephonyManager.EXTRA_STATE)

            var state = 0
            when (stateStr) {
                TelephonyManager.EXTRA_STATE_IDLE -> state = TelephonyManager.CALL_STATE_IDLE
                TelephonyManager.EXTRA_STATE_OFFHOOK -> state = TelephonyManager.CALL_STATE_OFFHOOK
                TelephonyManager.EXTRA_STATE_RINGING -> state = TelephonyManager.CALL_STATE_RINGING
            }

            onCallStateChanged(context, state)
        }
    }

    private fun onCallStateChanged(context: Context, state: Int) {
        if (
            lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_RINGING) {
            // Incoming call ringing
        } else if (lastState == TelephonyManager.CALL_STATE_RINGING && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Incoming call answered
        } else if (lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Outgoing call started
        } else if (state == TelephonyManager.CALL_STATE_IDLE) {
            // Call ended (either incoming or outgoing)
            if (lastState == TelephonyManager.CALL_STATE_OFFHOOK) {
                // 통화가 방금 끝났으므로 파일 스캔 워커 예약 (번호는 워커가 CallLog로 확보)
                scheduleCallSyncWork(context)
            }
        }

        lastState = state
    }

    private fun stateStrToInt(stateStr: String): Int {
        return when (stateStr) {
            TelephonyManager.EXTRA_STATE_IDLE -> TelephonyManager.CALL_STATE_IDLE
            TelephonyManager.EXTRA_STATE_OFFHOOK -> TelephonyManager.CALL_STATE_OFFHOOK
            TelephonyManager.EXTRA_STATE_RINGING -> TelephonyManager.CALL_STATE_RINGING
            else -> TelephonyManager.CALL_STATE_IDLE
        }
    }

    private fun stateIntToStr(stateInt: Int): String {
         return when (stateInt) {
            TelephonyManager.CALL_STATE_IDLE -> TelephonyManager.EXTRA_STATE_IDLE
            TelephonyManager.CALL_STATE_OFFHOOK -> TelephonyManager.EXTRA_STATE_OFFHOOK
            TelephonyManager.CALL_STATE_RINGING -> TelephonyManager.EXTRA_STATE_RINGING
            else -> TelephonyManager.EXTRA_STATE_IDLE
        }
    }

    private fun scheduleCallSyncWork(context: Context) {
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — 통화 동기화 예약 건너뜀")
            return
        }

        Log.d(TAG, "Scheduling call sync work via WorkManager")

        val workRequest = OneTimeWorkRequestBuilder<CallSyncWorker>()
            .setInitialDelay(8, TimeUnit.SECONDS) // 파일 쓰기/CallLog 기록 시간을 고려
            .build()

        WorkManager.getInstance(context).enqueue(workRequest)
    }
}
