package com.ggotai.hp.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.provider.MediaStore
import android.util.Log
import androidx.core.app.NotificationCompat
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import com.ggotai.hp.util.CallLogReader
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class RecordingService : Service() {

    companion object {
        private const val TAG = "RecordingService"
        const val ACTION_SYNC_FILE = "ACTION_SYNC_FILE"
        const val EXTRA_CUSTOMER_NUMBER = "EXTRA_CUSTOMER_NUMBER"
        
        private const val CHANNEL_ID = "RecordingServiceChannel"
        private const val NOTIFICATION_ID = 1
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        UploadManager.initTts(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_SYNC_FILE) {
            val customerNumber = intent.getStringExtra(EXTRA_CUSTOMER_NUMBER) ?: "Unknown"
            
            // 안드로이드 14 이상 백그라운드 서비스 제한 회피를 위해 명시적 타입 전달
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, createNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
            } else {
                startForeground(NOTIFICATION_ID, createNotification())
            }
            
            syncSamsungRecordFile(customerNumber)
        }
        return START_NOT_STICKY
    }

    private fun syncSamsungRecordFile(customerNumber: String) {
        CoroutineScope(Dispatchers.IO).launch {
            Log.d(TAG, "통화 종료 감지. 5초 대기 후 삼성 기본 녹음 파일 검색 시작...")
            
            // 삼성 폰이 녹음 파일을 저장하고 닫을 때까지 넉넉한 시간을 벌어줌 (5초)
            delay(5000)
            
            val recordFilePath = findLatestCallRecordFile()
            
            val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
            val userPhoneNumber = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"

            val currentDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
            val currentTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

            val audioFileName = if (recordFilePath != null) File(recordFilePath).name else ""
            
            // 실제 앱에서는 MediaMetadataRetriever 등으로 길이를 추출할 수 있으나 임시로 0 처리
            val durationSeconds = 0

            // 최근 통화기록에서 수신/발신 종류 확보 (CallLog.Calls.TYPE)
            val callType = CallLogReader.latestCall(applicationContext)?.type

            val callHistory = CallHistory(
                userPhoneNumber = userPhoneNumber,
                callDate = currentDate,
                callTime = currentTime,
                phoneNumber = customerNumber,
                transferStatus = if (recordFilePath != null) "전송중" else "실패(녹음파일없음)",
                audioFileName = audioFileName,
                audioFilePath = recordFilePath ?: "",
                durationSeconds = durationSeconds,
                callType = callType,
                syncStatus = 0
            )

            val db = AppDatabase.getDatabase(applicationContext)
            val id = db.callHistoryDao().insert(callHistory)
            Log.d(TAG, "DB 저장 완료 - ID: $id, 경로: ${recordFilePath ?: "없음"}")
            
            if (recordFilePath != null) {
                // 서버 전송 로직 호출
                UploadManager.uploadCallHistory(applicationContext, id.toInt())
            } else {
                Log.e(TAG, "삼성 기본 녹음 파일을 찾을 수 없어 업로드를 실패 처리합니다.")
                UploadManager.speak("통화 녹음 파일을 찾을 수 없습니다. 기본 녹음 설정이 켜져 있는지 확인해 주세요.")
            }
            
            // 작업 완료 후 서비스 종료
            stopSelf()
        }
    }

    private fun findLatestCallRecordFile(): String? {
        var latestFilePath: String? = null
        var latestTime = 0L
        val timeThreshold = System.currentTimeMillis() - (10 * 60 * 1000) // 최근 10분 내

        // 1. 직접 삼성 녹음 폴더 스캔 시도 (MediaStore 인덱싱 지연 회피)
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

        // 폴더 스캔으로 찾았다면 즉시 반환
        if (latestFilePath != null) {
            Log.d(TAG, "폴더 직접 스캔으로 최신 파일 찾음: $latestFilePath")
            return latestFilePath
        }

        // 2. 실패 시 MediaStore 백업 스캔 시도
        Log.d(TAG, "폴더 스캔 실패, MediaStore 백업 검색 시도...")
        val projection = arrayOf(MediaStore.Audio.Media.DATA, MediaStore.Audio.Media.DATE_ADDED)
        val sortOrder = "${MediaStore.Audio.Media.DATE_ADDED} DESC"
        
        try {
            contentResolver.query(
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

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "통화 녹음 연동 서비스",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(serviceChannel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("ggotAIhp 파일 연동 중")
            .setContentText("통화 종료 후 기본 녹음 파일을 찾고 있습니다.")
            .setSmallIcon(android.R.drawable.ic_popup_sync) 
            .build()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }
}
