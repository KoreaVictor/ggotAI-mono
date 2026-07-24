package com.ggotai.hp.worker

import android.content.Context
import android.util.Log
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkerParameters
import androidx.work.WorkManager
import com.ggotai.hp.api.RetrofitClient
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.MessageBuffer
import com.ggotai.hp.manager.DeviceStatus
import com.ggotai.hp.policy.MessageGroupDecider
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

/**
 * 버퍼에 쌓인 카톡·문자 메시지를 대화방 단위로 묶어 서버에 올린다.
 *
 * 마지막 메시지로부터 디바운스 시간이 지난 대화방만 확정한다. 아직 대화가 진행 중인
 * 방은 그대로 두고 워커를 다시 예약한다.
 */
class MessageFlushWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "MessageFlushWorker"
        private const val WORK_NAME = "message-flush"

        /**
         * 확정 워커를 예약한다. 이미 예약돼 있으면 교체(REPLACE)해 타이머를 다시 시작한다 —
         * 새 메시지가 올 때마다 확정이 뒤로 밀리는 디바운스가 이걸로 성립한다.
         */
        fun schedule(context: Context, delayMillis: Long = MessageGroupDecider.DEBOUNCE_MILLIS) {
            val request = OneTimeWorkRequestBuilder<MessageFlushWorker>()
                .setInitialDelay(delayMillis, TimeUnit.MILLISECONDS)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME, ExistingWorkPolicy.REPLACE, request
            )
        }
    }

    override suspend fun doWork(): Result {
        if (DeviceStatus.isRevoked(applicationContext)) {
            Log.d(TAG, "기기 승인취소 — 확정 중단")
            return Result.success()
        }

        val dao = AppDatabase.getDatabase(applicationContext).messageBufferDao()
        val prefs = applicationContext.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val userPhoneNumber = prefs.getString("USER_PHONE_NUMBER", null)
        if (userPhoneNumber.isNullOrBlank()) {
            Log.w(TAG, "기기 번호 미확인 — 다음 기회에 재시도")
            return Result.retry()
        }

        val now = System.currentTimeMillis()
        var hasPendingGroup = false
        var hasFailure = false

        for (group in dao.getGroups()) {
            if (!MessageGroupDecider.shouldFlush(group.lastReceivedAt, now)) {
                // 아직 대화 중 — 다음 예약에서 다시 본다.
                hasPendingGroup = true
                continue
            }

            val messages = dao.getGroupMessages(group.channelOrder, group.senderKey)
            if (messages.isEmpty()) continue

            if (upload(userPhoneNumber, messages)) {
                dao.deleteByIds(messages.map { it.id })
                Log.d(TAG, "묶음 업로드 성공 ${group.channelOrder}/${messages.size}건")
            } else {
                hasFailure = true
            }
        }

        return when {
            // 업로드 실패는 WorkManager 백오프에 맡긴다(버퍼는 그대로 남아 다음에 재시도).
            hasFailure -> Result.retry()
            else -> {
                if (hasPendingGroup) schedule(applicationContext)
                Result.success()
            }
        }
    }

    /** 대화 묶음 하나를 upload-text 로 전송한다. 성공 시 true. */
    private suspend fun upload(userPhoneNumber: String, messages: List<MessageBuffer>): Boolean {
        val first = messages.first()
        val last = messages.last()
        // 수신일시는 마지막 메시지 기준 — 멱등성 키(가게+발신자+일시)의 일부다.
        val at = Date(last.receivedAt)
        val date = SimpleDateFormat("yyyy-MM-dd", Locale.KOREA).format(at)
        val time = SimpleDateFormat("HH:mm:ss", Locale.KOREA).format(at)
        val text = messages.joinToString("\n") { it.body }

        return try {
            val plain = "text/plain".toMediaTypeOrNull()
            val response = RetrofitClient.instance.uploadText(
                userPhoneNumber.toRequestBody(plain),
                first.phoneNumber.toRequestBody(plain),
                first.senderName.toRequestBody(plain),
                date.toRequestBody(plain),
                time.toRequestBody(plain),
                first.channelOrder.toRequestBody(plain),
                text.toRequestBody(plain)
            )

            if (response.isSuccessful && response.body()?.status == "success") {
                true
            } else {
                if (response.code() == 401) {
                    // 서버가 명시적으로 거부 → 승인취소 확정. 재시도해도 동일하다.
                    DeviceStatus.markRevoked(applicationContext)
                }
                Log.e(TAG, "묶음 업로드 실패 code=${response.code()} ${response.body()?.message}")
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "묶음 업로드 예외: ${e.message}")
            false
        }
    }
}
