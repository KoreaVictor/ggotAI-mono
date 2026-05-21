package com.ggotai.hp.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface CallHistoryDao {
    @Insert
    suspend fun insert(callHistory: CallHistory): Long

    @Update
    suspend fun update(callHistory: CallHistory)

    @Query("SELECT * FROM call_history ORDER BY call_date DESC, call_time DESC")
    suspend fun getAll(): List<CallHistory>

    @Query("SELECT * FROM call_history WHERE call_date = :date ORDER BY call_date DESC, call_time DESC")
    suspend fun getByDate(date: String): List<CallHistory>

    @Query("SELECT * FROM call_history WHERE sync_status = 0")
    suspend fun getUnsynced(): List<CallHistory>

    @Query("UPDATE call_history SET transfer_status = '실패', error_code = 'APP_KILLED' WHERE transfer_status = '전송중'")
    suspend fun markPendingAsFailed()

    @androidx.room.Delete
    suspend fun delete(callHistory: CallHistory)
}
