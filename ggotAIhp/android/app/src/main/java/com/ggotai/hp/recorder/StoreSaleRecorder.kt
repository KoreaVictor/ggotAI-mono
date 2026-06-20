package com.ggotai.hp.recorder

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import java.io.File

/**
 * 매장판매 인앱 음성 녹음기. MediaRecorder(AAC/.m4a)로 녹음하며 200ms 주기로 진폭을 폴링해
 * 무음 지속/최대 길이에 도달하면 자동종료 콜백을 부른다. 종료 판정 자체는 RecordingStopDecider.
 */
class StoreSaleRecorder(private val context: Context) {

    data class Result(val file: File, val elapsedMs: Long, val hadSpeech: Boolean)

    companion object { private const val TAG = "StoreSaleRecorder"; private const val POLL_MS = 200L }

    private var recorder: MediaRecorder? = null
    private var outFile: File? = null
    private var startedAt = 0L
    private var lastSpeechAt = 0L
    private var hadSpeech = false
    private val handler = Handler(Looper.getMainLooper())
    private var onAutoStop: ((StopReason) -> Unit)? = null

    /** 녹음 시작. 성공 true. (호출 전 RECORD_AUDIO 권한이 있어야 함) */
    fun start(onAutoStop: (StopReason) -> Unit): Boolean {
        this.onAutoStop = onAutoStop
        val dir = File(context.filesDir, "store_sale").apply { mkdirs() }
        val file = File(dir, "store_${System.currentTimeMillis()}.m4a")
        outFile = file
        val rec = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else @Suppress("DEPRECATION") MediaRecorder()
        return try {
            rec.setAudioSource(MediaRecorder.AudioSource.MIC)
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            rec.setAudioEncodingBitRate(96000)
            rec.setAudioSamplingRate(44100)
            rec.setOutputFile(file.absolutePath)
            rec.prepare()
            rec.start()
            recorder = rec
            startedAt = SystemClock.elapsedRealtime()
            lastSpeechAt = startedAt
            hadSpeech = false
            handler.postDelayed(pollRunnable, POLL_MS)
            true
        } catch (e: Exception) {
            Log.e(TAG, "녹음 시작 실패", e)
            runCatching { rec.release() }
            recorder = null
            false
        }
    }

    private val pollRunnable = object : Runnable {
        override fun run() {
            val rec = recorder ?: return
            val now = SystemClock.elapsedRealtime()
            val amp = runCatching { rec.maxAmplitude }.getOrDefault(0)
            if (amp >= RecordingStopDecider.SILENCE_AMPLITUDE_THRESHOLD) {
                hadSpeech = true
                lastSpeechAt = now
            }
            val elapsed = now - startedAt
            val silence = now - lastSpeechAt
            val reason = RecordingStopDecider.decide(elapsed, silence)
            if (reason != null) {
                onAutoStop?.invoke(reason)
                return
            }
            handler.postDelayed(this, POLL_MS)
        }
    }

    /** 녹음 종료. 결과(파일/경과/발화여부) 반환, 실패 시 null. */
    fun stop(): Result? {
        handler.removeCallbacks(pollRunnable)
        val rec = recorder ?: return null
        val file = outFile ?: return null
        val elapsed = SystemClock.elapsedRealtime() - startedAt
        recorder = null
        return try {
            rec.stop(); rec.release()
            Result(file, elapsed, hadSpeech)
        } catch (e: Exception) {
            Log.e(TAG, "녹음 종료 실패", e)
            runCatching { rec.release() }
            runCatching { file.delete() }
            null
        }
    }

    /** 취소: 녹음 폐기 + 파일 삭제. */
    fun cancel() {
        handler.removeCallbacks(pollRunnable)
        recorder?.let { runCatching { it.stop() }; runCatching { it.release() } }
        recorder = null
        outFile?.let { runCatching { it.delete() } }
    }
}
