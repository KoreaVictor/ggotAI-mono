package com.ggotai.hp.manager

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.ggotai.hp.api.RetrofitClient
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.util.NetworkUtil
import com.ggotai.hp.worker.ResendWorker
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.Locale

object UploadManager {
    private const val TAG = "UploadManager"
    private const val MAX_RETRIES = 3
    private const val RETRY_DELAY_MS = 2000L

    private var tts: TextToSpeech? = null

    fun initTts(context: Context) {
        if (tts == null) {
            tts = TextToSpeech(context.applicationContext) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    tts?.language = Locale.KOREAN
                }
            }
        }
    }

    /**
     * 통화 직후 즉시 업로드. 최대 3회 재시도하고, 최종 실패 시 '실패' 처리 + TTS 알림.
     * (워커가 아닌 즉시 경로 전용)
     */
    suspend fun uploadCallHistory(context: Context, historyId: Int) {
        withContext(Dispatchers.IO) {
            val db = AppDatabase.getDatabase(context)
            val dao = db.callHistoryDao()

            // DB insert 완료를 잠깐 대기
            delay(500)

            val history = dao.getAll().find { it.id == historyId } ?: return@withContext

            val file = File(history.audioFilePath)
            if (!file.exists()) {
                markFailed(dao, history, "FILE_NOT_FOUND", "오디오 파일이 존재하지 않습니다.")
                playTtsError(context)
                return@withContext
            }

            // 통화 직후 네트워크 미복구(예: VoLTE 직후 IMS 망만 살아있는 순간)면
            // 헛된 '실패' 음성 없이 자동 재전송에 위임하고, 망 복구 즉시 올라가도록 예약한다.
            if (!NetworkUtil.isOnline(context)) {
                markFailed(dao, history, "OFFLINE", "네트워크 연결 시 자동 전송됩니다.")
                enqueueResendOnReconnect(context)
                Log.d(TAG, "오프라인 — 즉시 업로드 보류, 네트워크 복구 시 자동 전송 예약 id=$historyId")
                return@withContext
            }

            var attempt = 0
            var success = false
            while (attempt < MAX_RETRIES && !success) {
                success = uploadOnce(context, historyId)
                if (!success) {
                    attempt++
                    if (attempt < MAX_RETRIES) delay(RETRY_DELAY_MS)
                }
            }

            if (!success) {
                val fresh = dao.getAll().find { it.id == historyId }
                if (fresh != null) {
                    markFailed(
                        dao,
                        fresh,
                        fresh.errorCode ?: "SERVER_500",
                        fresh.errorMessage ?: "알 수 없는 오류"
                    )
                }
                // 시도 도중 네트워크가 끊겼을 수 있다 → 온라인일 때만 '실패' 음성,
                // 오프라인이면 음성 없이 자동 재전송 예약(헛된 알림 방지).
                if (NetworkUtil.isOnline(context)) {
                    playTtsError(context)
                } else {
                    enqueueResendOnReconnect(context)
                    Log.d(TAG, "업로드 실패 후 오프라인 — 음성 생략, 자동 전송 예약 id=$historyId")
                }
            }
        }
    }

    /**
     * 1건을 1회만 업로드 시도한다.
     * 성공 → transfer_status='성공', sync_status=1 로 갱신하고 true.
     * 실패 → error_code/error_message 만 기록하고 false (transfer_status/sync_status/retry_count는 호출자가 관리).
     */
    suspend fun uploadOnce(context: Context, historyId: Int): Boolean = withContext(Dispatchers.IO) {
        val dao = AppDatabase.getDatabase(context).callHistoryDao()
        val history = dao.getAll().find { it.id == historyId } ?: return@withContext false

        val file = File(history.audioFilePath)
        if (!file.exists()) {
            history.errorCode = "FILE_NOT_FOUND"
            history.errorMessage = "오디오 파일이 존재하지 않습니다."
            dao.update(history)
            return@withContext false
        }

        try {
            val userPhoneRb = history.userPhoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
            val phoneRb = history.phoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
            val nameRb = history.customerName.toRequestBody("text/plain".toMediaTypeOrNull())
            val dateRb = history.callDate.toRequestBody("text/plain".toMediaTypeOrNull())
            val timeRb = history.callTime.toRequestBody("text/plain".toMediaTypeOrNull())
            val durationRb = (history.durationSeconds?.toString() ?: "0").toRequestBody("text/plain".toMediaTypeOrNull())

            val reqFile = file.asRequestBody("audio/mpeg".toMediaTypeOrNull())
            val audioPart = MultipartBody.Part.createFormData("audio_file", file.name, reqFile)

            val response = RetrofitClient.instance.uploadCall(
                userPhoneRb, phoneRb, nameRb, dateRb, timeRb, durationRb, audioPart
            )

            if (response.isSuccessful && response.body()?.status == "success") {
                history.transferStatus = "성공"
                history.syncStatus = 1
                history.errorCode = null
                history.errorMessage = null
                dao.update(history)
                Log.d(TAG, "Upload success (uploadOnce) id=$historyId")
                true
            } else {
                history.errorCode = "SERVER_500"
                history.errorMessage = response.body()?.message ?: "서버 업로드 실패"
                dao.update(history)
                Log.e(TAG, "Upload failed (uploadOnce) id=$historyId: ${history.errorMessage}")
                false
            }
        } catch (e: Exception) {
            history.errorCode = "SERVER_500"
            history.errorMessage = e.message ?: "알 수 없는 오류"
            dao.update(history)
            Log.e(TAG, "Upload exception (uploadOnce) id=$historyId: ${e.message}")
            false
        }
    }

    private suspend fun markFailed(dao: com.ggotai.hp.db.CallHistoryDao, history: CallHistory, code: String, msg: String) {
        history.transferStatus = "실패"
        history.errorCode = code
        history.errorMessage = msg
        dao.update(history)
    }

    private fun playTtsError(context: Context) {
        // 서버 환경설정(use_notification)이 'N'이면 알림 생략. 미조회 시 기본 'Y'(알림 ON).
        val prefs = context.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        if (prefs.getString("USE_NOTIFICATION", "Y") == "N") {
            Log.d(TAG, "use_notification=N: TTS 실패 알림 생략")
            return
        }
        tts?.speak("전송에 실패했습니다. 수동으로 재전송을 눌러주세요.", TextToSpeech.QUEUE_FLUSH, null, "UploadError")
    }

    fun speak(message: String) {
        tts?.speak(message, TextToSpeech.QUEUE_FLUSH, null, "UploadMessage")
    }

    /**
     * 네트워크 복구 즉시 1회 재전송을 수행하도록 CONNECTED 제약의 일회성 ResendWorker를 예약한다.
     * 주기(15분) 워커보다 빠르게 올리기 위함. 이미 예약돼 있으면 유지(KEEP)한다.
     */
    private fun enqueueResendOnReconnect(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = OneTimeWorkRequestBuilder<ResendWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            "resend-on-reconnect",
            ExistingWorkPolicy.KEEP,
            request
        )
    }
}
