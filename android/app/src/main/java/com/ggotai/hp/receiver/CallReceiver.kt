package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.telephony.TelephonyManager
import android.util.Log
import com.ggotai.hp.service.RecordingService
import androidx.work.Data
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.ggotai.hp.worker.CallSyncWorker
import java.util.concurrent.TimeUnit

class CallReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CallReceiver"
        private var lastState = TelephonyManager.CALL_STATE_IDLE
        private var savedNumber: String? = null
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == TelephonyManager.ACTION_PHONE_STATE_CHANGED) {
            val stateStr = intent.extras?.getString(TelephonyManager.EXTRA_STATE)
            val number = intent.extras?.getString(TelephonyManager.EXTRA_INCOMING_NUMBER)
            
            if (number != null && number.isNotEmpty()) {
                savedNumber = number
            }

            var state = 0
            when (stateStr) {
                TelephonyManager.EXTRA_STATE_IDLE -> state = TelephonyManager.CALL_STATE_IDLE
                TelephonyManager.EXTRA_STATE_OFFHOOK -> state = TelephonyManager.CALL_STATE_OFFHOOK
                TelephonyManager.EXTRA_STATE_RINGING -> state = TelephonyManager.CALL_STATE_RINGING
            }

            onCallStateChanged(context, state, savedNumber)
        }
    }

    private fun onCallStateChanged(context: Context, state: Int, number: String?) {
        if (lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_RINGING) {
            // Incoming call ringing
        } else if (lastState == TelephonyManager.CALL_STATE_RINGING && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Incoming call answered
        } else if (lastState == TelephonyManager.CALL_STATE_IDLE && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Outgoing call started
        } else if (state == TelephonyManager.CALL_STATE_IDLE) {
            // Call ended (either incoming or outgoing)
            if (lastState == TelephonyManager.CALL_STATE_OFFHOOK) {
                // 통화가 방금 끝났으므로 파일 스캔 워커 예약
                scheduleCallSyncWork(context, savedNumber)
            }
            savedNumber = null // Reset the number
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

    private fun scheduleCallSyncWork(context: Context, customerNumber: String?) {
        Log.d(TAG, "Scheduling call sync work via WorkManager for number: $customerNumber")
        
        val inputData = Data.Builder()
            .putString(CallSyncWorker.KEY_CUSTOMER_NUMBER, customerNumber ?: "Unknown")
            .build()
            
        val workRequest = OneTimeWorkRequestBuilder<CallSyncWorker>()
            .setInitialDelay(8, TimeUnit.SECONDS) // 파일 쓰기 시간을 고려하여 5초에서 8초로 늘려 줌
            .setInputData(inputData)
            .build()
            
        WorkManager.getInstance(context).enqueue(workRequest)
    }
}
