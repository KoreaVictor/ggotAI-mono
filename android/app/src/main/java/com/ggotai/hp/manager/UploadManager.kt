package com.ggotai.hp.manager

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import com.ggotai.hp.api.RetrofitClient
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
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

    suspend fun uploadCallHistory(context: Context, historyId: Int) {
        withContext(Dispatchers.IO) {
            val db = AppDatabase.getDatabase(context)
            val dao = db.callHistoryDao()
            
            // Wait a moment for DB insertion to complete just in case
            delay(500)
            
            val histories = dao.getAll()
            val history = histories.find { it.id == historyId } ?: return@withContext

            val file = File(history.audioFilePath)
            if (!file.exists()) {
                markFailed(dao, history, "FILE_NOT_FOUND", "오디오 파일이 존재하지 않습니다.")
                playTtsError(context)
                return@withContext
            }

            var attempt = 0
            var success = false

            while (attempt < MAX_RETRIES && !success) {
                try {
                    Log.d(TAG, "Upload attempt ${attempt + 1}")
                    
                    val userPhoneRb = history.userPhoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
                    val phoneRb = history.phoneNumber.toRequestBody("text/plain".toMediaTypeOrNull())
                    val nameRb = history.customerName.toRequestBody("text/plain".toMediaTypeOrNull())
                    val dateRb = history.callDate.toRequestBody("text/plain".toMediaTypeOrNull())
                    val timeRb = history.callTime.toRequestBody("text/plain".toMediaTypeOrNull())
                    val durationRb = (history.durationSeconds?.toString() ?: "0").toRequestBody("text/plain".toMediaTypeOrNull())
                    
                    val reqFile = file.asRequestBody("audio/mpeg".toMediaTypeOrNull()) // mp3 or m4a
                    val audioPart = MultipartBody.Part.createFormData("audio_file", file.name, reqFile)

                    val response = RetrofitClient.instance.uploadCall(
                        userPhoneRb, phoneRb, nameRb, dateRb, timeRb, durationRb, audioPart
                    )

                    if (response.isSuccessful && response.body()?.status == "success") {
                        success = true
                        history.transferStatus = "성공"
                        history.syncStatus = 1
                        history.errorCode = null
                        history.errorMessage = null
                        dao.update(history)
                        Log.d(TAG, "Upload success")
                    } else {
                        throw Exception(response.body()?.message ?: "서버 업로드 실패")
                    }
                } catch (e: Exception) {
                    attempt++
                    Log.e(TAG, "Upload failed: ${e.message}")
                    if (attempt < MAX_RETRIES) {
                        delay(RETRY_DELAY_MS)
                    } else {
                        markFailed(dao, history, "SERVER_500", e.message ?: "알 수 없는 오류")
                        playTtsError(context)
                    }
                }
            }
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
}
