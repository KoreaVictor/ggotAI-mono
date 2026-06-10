package com.ggotai.hp.worker

import android.media.MediaMetadataRetriever
import android.content.Context
import android.provider.MediaStore
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import com.ggotai.hp.util.CallLogReader
import com.ggotai.hp.util.CustomerResolver
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class CallSyncWorker(
    private val context: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(context, workerParams) {

    companion object {
        private const val TAG = "CallSyncWorker"
    }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val isAutoSyncEnabled = prefs.getBoolean("AUTO_SYNC_ENABLED", true)
        
        if (!isAutoSyncEnabled) {
            Log.d(TAG, "CallSyncWorker 중단 - 환경설정에서 자동 연동이 꺼져 있습니다.")
            return@withContext Result.success()
        }

        // CallLog에서 가장 최근 통화 번호/연락처명 확보 (EXTRA_INCOMING_NUMBER는 Android 10+ 일반앱에 null)
        val callLog = CallLogReader.latestCall(context)
        val customerNumber = CustomerResolver.resolveNumber(callLog?.number)
        Log.d(TAG, "CallSyncWorker 시작 - 대상 번호: $customerNumber (CallLog name=${callLog?.cachedName})")

        try {
            UploadManager.initTts(context)
            
            val recordFilePath = findLatestCallRecordFile()
            
            val prefs = context.getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
            val userPhoneNumber = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"
            val currentDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
            val currentTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

            val audioFileName = if (recordFilePath != null) File(recordFilePath).name else ""
            val durationSeconds = if (recordFilePath != null) getAudioDuration(recordFilePath) else 0
            
            val contactName = if (customerNumber != CustomerResolver.UNKNOWN_NUMBER) {
                getContactName(context, customerNumber)
            } else null
            val matchedName = CustomerResolver.resolveName(callLog?.cachedName, contactName)

            val callHistory = CallHistory(
                userPhoneNumber = userPhoneNumber,
                callDate = currentDate,
                callTime = currentTime,
                phoneNumber = customerNumber,
                customerName = matchedName,
                transferStatus = if (recordFilePath != null) "전송중" else "실패(녹음파일없음)",
                audioFileName = audioFileName,
                audioFilePath = recordFilePath ?: "",
                durationSeconds = durationSeconds,
                syncStatus = 0
            )

            val db = AppDatabase.getDatabase(context)
            val id = db.callHistoryDao().insert(callHistory)
            Log.d(TAG, "DB 저장 완료 - ID: $id, 경로: ${recordFilePath ?: "없음"}")
            
            if (recordFilePath != null) {
                UploadManager.uploadCallHistory(context, id.toInt())
            } else {
                Log.e(TAG, "삼성 기본 녹음 파일을 찾을 수 없어 업로드를 실패 처리합니다.")
                UploadManager.speak("통화 녹음 파일을 찾을 수 없습니다. 기본 녹음 설정이 켜져 있는지 확인해 주세요.")
            }
            
            // 작업 완료 후 메인 화면(MainActivity) 목록 새로고침 알림 발송
            val intent = android.content.Intent("com.ggotai.hp.ACTION_UPDATE_HISTORY")
            context.sendBroadcast(intent)
            
            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "CallSyncWorker 실행 중 에러 발생", e)
            Result.failure()
        }
    }

    private fun findLatestCallRecordFile(): String? {
        var latestFilePath: String? = null
        var latestTime = 0L
        val timeThreshold = System.currentTimeMillis() - (10 * 60 * 1000)

        val possibleDirs = listOf(
            File(android.os.Environment.getExternalStorageDirectory(), "Call"),
            File(android.os.Environment.getExternalStorageDirectory(), "Music/Call"),
            File(android.os.Environment.getExternalStorageDirectory(), "Recordings/Call"),
            File(android.os.Environment.getExternalStorageDirectory(), "통화"),
            File(android.os.Environment.getExternalStorageDirectory(), "통화 녹음"),
            File(android.os.Environment.getExternalStorageDirectory(), "Recordings/통화"),
            File(android.os.Environment.getExternalStorageDirectory(), "Recordings/통화 녹음"),
            File(android.os.Environment.getExternalStorageDirectory(), "Voice Recorder"),
            File(android.os.Environment.getExternalStorageDirectory(), "Recordings/Voice Recorder"),
            File(android.os.Environment.getExternalStoragePublicDirectory(android.os.Environment.DIRECTORY_MUSIC), "Call")
        )

        for (dir in possibleDirs) {
            try {
                if (dir.exists() && dir.isDirectory) {
                    val files = dir.listFiles()
                    if (files != null) {
                        for (file in files) {
                            if (file.isFile && (file.name.endsWith(".m4a") || file.name.endsWith(".amr") || file.name.endsWith(".mp3") || file.name.endsWith(".wav"))) {
                                if (file.lastModified() > latestTime && file.lastModified() > timeThreshold) {
                                    latestTime = file.lastModified()
                                    latestFilePath = file.absolutePath
                                }
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Directory scan failed: ${dir.absolutePath}", e)
            }
        }

        if (latestFilePath != null) {
            Log.d(TAG, "폴더 직접 스캔으로 최신 파일 찾음: $latestFilePath")
            return latestFilePath
        }

        Log.d(TAG, "폴더 스캔 실패, MediaStore 백업 검색 시도...")
        val projection = arrayOf(MediaStore.Audio.Media.DATA, MediaStore.Audio.Media.DATE_ADDED)
        val sortOrder = "${MediaStore.Audio.Media.DATE_ADDED} DESC"
        
        try {
            context.contentResolver.query(
                MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                projection,
                null,
                null,
                sortOrder
            )?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val dataColumn = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATA)
                    latestFilePath = cursor.getString(dataColumn)
                    Log.d(TAG, "MediaStore에서 찾은 최신 오디오 파일: $latestFilePath")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "미디어 파일 검색 중 에러 발생", e)
        }
        return latestFilePath
    }

    private fun getContactName(context: Context, phoneNumber: String): String {
        val uri = android.net.Uri.withAppendedPath(
            android.provider.ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
            android.net.Uri.encode(phoneNumber)
        )
        val projection = arrayOf(android.provider.ContactsContract.PhoneLookup.DISPLAY_NAME)
        var contactName = "신규"

        try {
            context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIndex = cursor.getColumnIndex(android.provider.ContactsContract.PhoneLookup.DISPLAY_NAME)
                    if (nameIndex >= 0) {
                        contactName = cursor.getString(nameIndex)
                        Log.d(TAG, "주소록에서 이름 매칭 성공: $contactName")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "주소록 조회 실패 (권한이 없거나 오류 발생)", e)
        }
        return contactName
    }

    private fun getAudioDuration(filePath: String): Int {
        var duration = 0
        var attempts = 0
        val maxAttempts = 3
        val sleepTimeMs = 500L // 0.5초 대기
        
        while (attempts < maxAttempts) {
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(filePath)
                val time = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                val durationMs = time?.toLongOrNull() ?: 0L
                duration = (durationMs / 1000).toInt()
                
                if (duration > 0) {
                    Log.d(TAG, "오디오 재생 시간 성공적으로 추출: $duration 초 (시도 횟수: ${attempts + 1})")
                    try {
                        retriever.release()
                    } catch (e: Exception) {}
                    break
                }
            } catch (e: Exception) {
                Log.w(TAG, "오디오 재생 시간 추출 시도 ${attempts + 1} 실패: $filePath", e)
            } finally {
                try {
                    retriever.release()
                } catch (e: Exception) {}
            }
            
            attempts++
            if (attempts < maxAttempts) {
                try {
                    Thread.sleep(sleepTimeMs) // 파일 쓰기 마무리를 기다리기 위해 0.5초 대기
                } catch (ie: InterruptedException) {
                    Thread.currentThread().interrupt()
                    break
                }
            }
        }
        
        if (duration <= 0) {
            Log.e(TAG, "최종적으로 오디오 재생 시간 추출 실패 (0초 반환): $filePath")
        }
        return duration
    }
}
