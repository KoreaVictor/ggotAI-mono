package com.ggotai.hp.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.util.Log
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.MessageBuffer
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.policy.MessageGroupDecider
import com.ggotai.hp.policy.OrderTextFilter
import com.ggotai.hp.util.ContactLookup
import com.ggotai.hp.util.CustomerResolver
import com.ggotai.hp.worker.MessageFlushWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 문자 주문 수집.
 *
 * 받은 문자를 바로 올리지 않고 버퍼에 쌓은 뒤 확정 워커를 예약한다. 주문이 여러 통으로
 * 나뉘어 오기 때문이다(예: "근조화환 부탁해요" → "10만원짜리로" → "받는분은 김철수").
 *
 * [OrderTextFilter]를 통과하지 못한 메시지는 버퍼에도 남기지 않는다 — 사장님 사생활이
 * 서버는커녕 앱 DB에도 쌓이지 않게 한다.
 */
class SmsReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "SmsReceiver"
        const val CHANNEL_SMS = "문자"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return
        if (DeviceStatus.isRevoked(context)) {
            Log.d(TAG, "기기 승인취소 — 문자 수집 건너뜀")
            return
        }

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (messages.isNullOrEmpty()) return

        // 장문은 여러 PDU로 쪼개져 도착한다 — 한 통으로 되붙인다.
        val sender = messages.firstOrNull()?.originatingAddress ?: return
        val body = messages.joinToString("") { it.messageBody ?: "" }

        val received = System.currentTimeMillis()
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val dao = AppDatabase.getDatabase(context).messageBufferDao()

                // 진행 중인 주문 대화면 키워드 없는 후속 문자도 받는다 — 가격·배송일·
                // 받는분이 뒷 통에 담겨 오기 때문이다. 스티키 창이 지나면 업로드가 밀려
                // 버퍼가 남아 있어도 풀린다(사생활 보호).
                val active = dao.countRecentBySender(
                    CHANNEL_SMS, sender, MessageGroupDecider.stickySince(received)
                ) > 0
                if (!OrderTextFilter.shouldCollect(sender, body, active)) {
                    Log.d(TAG, "주문 후보 아님 — 폐기 (서버 전송 안 함)")
                    return@launch
                }

                // 문자는 발신번호만 온다 — 주소록에 있으면 그 이름을 고객명으로 쓴다.
                // 없으면 통화와 같은 기본값("신규"). 묶음 키(senderKey)는 번호 그대로 둔다
                // — 주소록 등록 여부가 바뀌어도 대화방이 갈라지지 않게.
                val senderName = CustomerResolver.resolveName(
                    null, ContactLookup.nameFor(context, sender)
                )

                dao.insert(
                    MessageBuffer(
                        channelOrder = CHANNEL_SMS,
                        senderKey = sender,
                        senderName = senderName,
                        phoneNumber = sender,
                        body = body,
                        receivedAt = received
                    )
                )
                // 카톡과 같은 기준: 수집된 건만 남긴다(본문은 길이만 — 내용은 로그에 안 남김).
                Log.d(TAG, "버퍼 적재 sender=$sender bodyLen=${body.length} active=$active parts=${messages.size}")
                // 새 메시지가 올 때마다 확정 시각을 뒤로 미룬다(디바운스).
                MessageFlushWorker.schedule(context)
            } catch (e: Exception) {
                Log.e(TAG, "문자 버퍼 적재 실패: ${e.message}")
            } finally {
                pending.finish()
            }
        }
    }
}
