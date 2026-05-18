package com.ggotai.hp.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.ggotai.hp.db.AppDatabase
import com.ggotai.hp.db.CallHistory
import com.ggotai.hp.manager.UploadManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class RecordingService : Service() {

    companion object {
        private const val TAG = "RecordingService"
        const val ACTION_START_RECORDING = "ACTION_START_RECORDING"
        const val ACTION_STOP_RECORDING = "ACTION_STOP_RECORDING"
        const val EXTRA_CUSTOMER_NUMBER = "EXTRA_CUSTOMER_NUMBER"
        
        private const val CHANNEL_ID = "RecordingServiceChannel"
        private const val NOTIFICATION_ID = 1
    }

    private var mediaRecorder: MediaRecorder? = null
    private var currentOutputFile: File? = null
    private var isRecording = false
    private var recordingStartTime: Long = 0
    private var currentCustomerNumber: String = ""

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        UploadManager.initTts(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        when (action) {
            ACTION_START_RECORDING -> {
                val customerNumber = intent.getStringExtra(EXTRA_CUSTOMER_NUMBER) ?: "Unknown"
                startRecording(customerNumber)
            }
            ACTION_STOP_RECORDING -> {
                stopRecording()
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun startRecording(customerNumber: String) {
        if (isRecording) return

        startForeground(NOTIFICATION_ID, createNotification())

        val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
        val userPhoneNumber = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"

        val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
        val fileName = "${userPhoneNumber}_${customerNumber}_${timeStamp}.mp3"
        
        val outputDir = getExternalFilesDir(android.os.Environment.DIRECTORY_MUSIC)
        if (outputDir != null && !outputDir.exists()) {
            outputDir.mkdirs()
        }
        currentOutputFile = File(outputDir, fileName)

        try {
            mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(this)
            } else {
                MediaRecorder()
            }

            mediaRecorder?.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setOutputFile(currentOutputFile?.absolutePath)
                prepare()
                start()
            }
            isRecording = true
            recordingStartTime = System.currentTimeMillis()
            currentCustomerNumber = customerNumber
            Log.d(TAG, "Recording started: ${currentOutputFile?.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start recording", e)
            stopSelf()
        }
    }

    private fun stopRecording() {
        if (!isRecording) return

        try {
            mediaRecorder?.apply {
                stop()
                release()
            }
            mediaRecorder = null
            isRecording = false
            Log.d(TAG, "Recording stopped: ${currentOutputFile?.absolutePath}")
            
            val durationMs = System.currentTimeMillis() - recordingStartTime
            val durationSeconds = (durationMs / 1000).toInt()

            val prefs = getSharedPreferences("app_prefs", Context.MODE_PRIVATE)
            val userPhoneNumber = prefs.getString("USER_PHONE_NUMBER", "Unknown") ?: "Unknown"

            val currentDate = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).format(Date())
            val currentTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())

            val callHistory = CallHistory(
                userPhoneNumber = userPhoneNumber,
                callDate = currentDate,
                callTime = currentTime,
                phoneNumber = currentCustomerNumber,
                transferStatus = "전송중", // or "대기중" if we will upload later
                audioFileName = currentOutputFile?.name ?: "",
                audioFilePath = currentOutputFile?.absolutePath ?: "",
                durationSeconds = durationSeconds,
                syncStatus = 0
            )

            // Save to DB in IO Thread
            CoroutineScope(Dispatchers.IO).launch {
                val db = AppDatabase.getDatabase(applicationContext)
                val id = db.callHistoryDao().insert(callHistory)
                Log.d(TAG, "Saved call history to Room DB with id $id")
                
                // 서버 전송 로직 호출
                UploadManager.uploadCallHistory(applicationContext, id.toInt())
            }
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to stop recording", e)
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val serviceChannel = NotificationChannel(
                CHANNEL_ID,
                "통화 녹음 서비스",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(serviceChannel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("ggotAIhp 통화 녹음 중")
            .setContentText("통화 내용을 안전하게 기록하고 있습니다.")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now) // TODO: 커스텀 아이콘으로 변경
            .build()
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isRecording) {
            stopRecording()
        }
    }
}
