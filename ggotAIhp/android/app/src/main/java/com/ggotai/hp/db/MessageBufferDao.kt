package com.ggotai.hp.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query

@Dao
interface MessageBufferDao {
    @Insert
    suspend fun insert(message: MessageBuffer): Long

    /** 대화방별 마지막 수신 시각. 확정 대상을 고르기 위한 요약. */
    @Query(
        "SELECT channel_order AS channelOrder, sender_key AS senderKey, " +
            "MAX(received_at) AS lastReceivedAt FROM message_buffer " +
            "GROUP BY channel_order, sender_key"
    )
    suspend fun getGroups(): List<BufferGroup>

    /** 한 대화방의 미전송 메시지를 받은 순서대로. */
    @Query(
        "SELECT * FROM message_buffer WHERE channel_order = :channelOrder " +
            "AND sender_key = :senderKey ORDER BY received_at ASC"
    )
    suspend fun getGroupMessages(channelOrder: String, senderKey: String): List<MessageBuffer>

    @Query("DELETE FROM message_buffer WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<Int>)

    @Query("SELECT COUNT(*) FROM message_buffer")
    suspend fun count(): Int

    /** 이 대화방에 아직 안 올린 주문 메시지가 있는지(=주문 대화 진행 중). */
    @Query(
        "SELECT COUNT(*) FROM message_buffer WHERE channel_order = :channelOrder " +
            "AND sender_key = :senderKey"
    )
    suspend fun countBySender(channelOrder: String, senderKey: String): Int

    /**
     * 같은 메시지가 이미 버퍼에 있는지. 카톡은 알림을 갱신·재게시하므로 같은 내용이
     * 여러 번 들어올 수 있다.
     */
    @Query(
        "SELECT COUNT(*) FROM message_buffer WHERE channel_order = :channelOrder " +
            "AND sender_key = :senderKey AND body = :body AND received_at = :receivedAt"
    )
    suspend fun countDuplicate(
        channelOrder: String,
        senderKey: String,
        body: String,
        receivedAt: Long
    ): Int
}
