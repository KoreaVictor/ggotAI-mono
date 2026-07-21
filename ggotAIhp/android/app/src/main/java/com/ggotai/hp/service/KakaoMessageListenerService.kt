package com.ggotai.hp.service

import android.app.Notification
import android.content.Context
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.MessageBuffer
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.policy.KakaoNotice
import com.ggotai.hp.policy.KakaoNotificationPolicy
import com.ggotai.hp.worker.MessageFlushWorker
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * 카톡 주문 수집.
 *
 * 개인 카카오톡은 공식 API가 없어 알림을 읽는 것이 유일한 경로다. 여기서는 알림에서 값만
 * 꺼내고, 수집 여부 판단은 전부 [KakaoNotificationPolicy]에 맡긴다(그쪽은 단위테스트 대상).
 *
 * 알림 접근 권한은 사용자가 시스템 설정에서 직접 허용해야 한다 — [isEnabled]로 확인한다.
 */
class KakaoMessageListenerService : NotificationListenerService() {

    companion object {
        private const val TAG = "KakaoListener"
        const val CHANNEL_KAKAO = "카톡"

        /** 이 앱에 알림 접근 권한이 허용돼 있는지. 꺼져 있으면 카톡을 통째로 놓친다. */
        fun isEnabled(context: Context): Boolean {
            val enabled = Settings.Secure.getString(
                context.contentResolver, "enabled_notification_listeners"
            ) ?: return false
            return enabled.split(":").any { it.contains(context.packageName) }
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName != KakaoNotificationPolicy.KAKAO_PACKAGE) return
        if (DeviceStatus.isRevoked(applicationContext)) {
            Log.d(TAG, "승인취소 — 수집 스킵")
            return
        }

        val notice = toNotice(sbn)
        val senderKey = notice.sender?.trim().orEmpty()
        if (senderKey.isEmpty()) return  // 묶음 요약 알림 — 개별 메시지가 아니다.

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val dao = AppDatabase.getDatabase(applicationContext).messageBufferDao()

                // 같은 대화방에 이미 주문 메시지가 쌓여 있으면 후속 메시지는 키워드 없이도
                // 받는다 — 가격·배송일·받는분이 뒷 통에 담겨 오기 때문이다.
                val active = dao.countBySender(CHANNEL_KAKAO, senderKey) > 0
                // 거절은 로그로 남기지 않는다 — 사장님 카톡은 남의 단톡·요약 알림이 하루
                // 수백 건이라 로그를 채우기만 하고 진단 가치가 없다.
                val candidate = KakaoNotificationPolicy.collectible(notice, active) ?: return@launch

                // 카톡은 같은 알림을 갱신·재게시한다 — 같은 내용이 두 번 쌓이지 않게 한다.
                val already = dao.countDuplicate(
                    CHANNEL_KAKAO, candidate.senderKey, candidate.body, candidate.receivedAt
                )
                if (already > 0) {
                    Log.d(TAG, "중복 알림 — 스킵 sender=${candidate.senderKey}")
                    return@launch
                }

                dao.insert(
                    MessageBuffer(
                        channelOrder = CHANNEL_KAKAO,
                        senderKey = candidate.senderKey,
                        senderName = candidate.senderName,
                        // 카톡 알림은 번호를 알려주지 않는다.
                        phoneNumber = "",
                        body = candidate.body,
                        receivedAt = candidate.receivedAt
                    )
                )
                // 수집된 건만 남긴다. "주문이 들어오긴 했나"를 확인하는 유일한 단서라
                // 발신자는 함께 기록한다(본문은 길이만 — 대화 내용은 로그에 남기지 않는다).
                Log.d(
                    TAG,
                    "버퍼 적재 sender=${candidate.senderKey} " +
                        "bodyLen=${candidate.body.length} active=$active"
                )
                // 새 메시지가 올 때마다 확정 시각을 뒤로 미룬다(디바운스).
                MessageFlushWorker.schedule(applicationContext)
            } catch (e: Exception) {
                Log.e(TAG, "카톡 버퍼 적재 실패: ${e.message}")
            }
        }
    }

    /** 알림 extras 를 프레임워크 비의존 값으로 옮긴다. 판단은 하지 않는다. */
    private fun toNotice(sbn: StatusBarNotification): KakaoNotice {
        val extras = sbn.notification.extras
        return KakaoNotice(
            packageName = sbn.packageName,
            sender = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString(),
            body = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString(),
            conversationTitle = extras
                .getCharSequence(Notification.EXTRA_CONVERSATION_TITLE)?.toString(),
            isGroupConversation = extras.getBoolean(Notification.EXTRA_IS_GROUP_CONVERSATION, false),
            // 알림에 실린 시각이 실제 수신 시각에 가장 가깝다(없으면 지금).
            postedAt = if (sbn.notification.`when` > 0) sbn.notification.`when` else sbn.postTime
        )
    }
}
