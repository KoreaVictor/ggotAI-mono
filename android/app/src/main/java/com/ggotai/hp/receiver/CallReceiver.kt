package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.telephony.TelephonyManager
import android.util.Log
import com.ggotai.hp.service.RecordingService

class CallReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CallReceiver"
        private var lastState = TelephonyManager.EXTRA_STATE_IDLE
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
        if (lastState == stateStrToInt(TelephonyManager.EXTRA_STATE_IDLE) && state == TelephonyManager.CALL_STATE_RINGING) {
            // Incoming call ringing
        } else if (lastState == stateStrToInt(TelephonyManager.EXTRA_STATE_RINGING) && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Incoming call answered
            startRecordingService(context, number)
        } else if (lastState == stateStrToInt(TelephonyManager.EXTRA_STATE_IDLE) && state == TelephonyManager.CALL_STATE_OFFHOOK) {
            // Outgoing call started
            startRecordingService(context, number)
        } else if (state == TelephonyManager.CALL_STATE_IDLE) {
            // Call ended (either incoming or outgoing)
            if (lastState == TelephonyManager.CALL_STATE_OFFHOOK) {
                stopRecordingService(context)
            }
            savedNumber = null // Reset the number
        }
        
        lastState = stateStrToInt(stateIntToStr(state))
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

    private fun startRecordingService(context: Context, customerNumber: String?) {
        Log.d(TAG, "Starting recording service for number: $customerNumber")
        val serviceIntent = Intent(context, RecordingService::class.java).apply {
            action = RecordingService.ACTION_START_RECORDING
            putExtra(RecordingService.EXTRA_CUSTOMER_NUMBER, customerNumber ?: "Unknown")
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }

    private fun stopRecordingService(context: Context) {
        Log.d(TAG, "Stopping recording service")
        val serviceIntent = Intent(context, RecordingService::class.java).apply {
            action = RecordingService.ACTION_STOP_RECORDING
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(serviceIntent)
        } else {
            context.startService(serviceIntent)
        }
    }
}
