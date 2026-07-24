package com.ggotai.hp.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * 아직 서버로 올리지 않은 카톡·문자 메시지 한 줄.
 *
 * 주문이 여러 메시지로 쪼개져 오므로 바로 올리지 않고 여기 쌓아 둔다. 같은 대화방
 * (channel_order + sender_key)의 메시지가 일정 시간 조용해지면 묶어서 한 건으로 올린다.
 * 업로드에 성공하면 해당 행들은 삭제된다.
 */
@Entity(tableName = "message_buffer")
data class MessageBuffer(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    // 수집 채널: '카톡' / '문자'.
    @ColumnInfo(name = "channel_order") val channelOrder: String,
    // 대화방 키. 문자는 발신번호, 카톡은 발신자 표시명(번호를 알 수 없다).
    @ColumnInfo(name = "sender_key") val senderKey: String,
    @ColumnInfo(name = "sender_name") val senderName: String,
    // 카톡은 번호를 알 수 없어 빈 문자열.
    @ColumnInfo(name = "phone_number") val phoneNumber: String,
    @ColumnInfo(name = "body") val body: String,
    @ColumnInfo(name = "received_at") val receivedAt: Long
)

/** 대화방별 마지막 수신 시각 — 어느 묶음을 확정할지 고르는 데 쓴다. */
data class BufferGroup(
    val channelOrder: String,
    val senderKey: String,
    val lastReceivedAt: Long
)
