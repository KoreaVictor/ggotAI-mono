package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import com.ggotai.hp.worker.MmsScanWorker

/**
 * 긴 문자(LMS) 도착 감지.
 *
 * 70자를 넘는 문자는 MMS 로 오고, MMS 는 SMS_RECEIVED 가 아니라 WAP_PUSH_RECEIVED 로
 * 도착한다. 여기서는 아무 판단도 하지 않고 스캔만 예약한다 — 정책을 방송 안에 넣으면
 * 에뮬레이터 없이 테스트할 수 없다(KakaoMessageListenerService 와 같은 이유).
 */
class MmsReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "MmsReceiver"
        private const val MMS_MIME = "application/vnd.wap.mms-message"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.WAP_PUSH_RECEIVED_ACTION) return
        if (intent.type != MMS_MIME) return

        Log.d(TAG, "MMS 도착 — 스캔 예약")
        MmsScanWorker.schedule(context)
    }
}
