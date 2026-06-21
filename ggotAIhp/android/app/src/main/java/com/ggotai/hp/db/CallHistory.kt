package com.ggotai.hp.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "call_history")
data class CallHistory(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    @ColumnInfo(name = "user_phone_number") val userPhoneNumber: String,
    @ColumnInfo(name = "call_date") val callDate: String,
    @ColumnInfo(name = "call_time") val callTime: String,
    @ColumnInfo(name = "phone_number") val phoneNumber: String,
    @ColumnInfo(name = "customer_name") val customerName: String = "신규",
    @ColumnInfo(name = "transfer_status") var transferStatus: String,
    @ColumnInfo(name = "audio_file_name") val audioFileName: String,
    @ColumnInfo(name = "audio_file_path") val audioFilePath: String,
    @ColumnInfo(name = "duration_seconds") val durationSeconds: Int? = null,
    // 통화 종류: Android CallLog.Calls.TYPE 값 (1=수신, 2=발신, 3=부재중 …). 레거시 행은 null.
    @ColumnInfo(name = "call_type") val callType: Int? = null,
    // 수집 채널: '핸드폰'(통화녹음, 기본) / '가게음성'(매장판매 인앱 녹음).
    @ColumnInfo(name = "channel_order") val channelOrder: String = "핸드폰",
    @ColumnInfo(name = "error_code") var errorCode: String? = null,
    @ColumnInfo(name = "error_message") var errorMessage: String? = null,
    @ColumnInfo(name = "sync_status") var syncStatus: Int = 0,
    @ColumnInfo(name = "retry_count") var retryCount: Int = 0
)
