package com.ggotai.hp.db

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CallHistoryDaoTest {

    private lateinit var db: AppDatabase
    private lateinit var dao: CallHistoryDao

    @Before
    fun setup() {
        val ctx = ApplicationProvider.getApplicationContext<android.content.Context>()
        db = Room.inMemoryDatabaseBuilder(ctx, AppDatabase::class.java)
            .allowMainThreadQueries()
            .build()
        dao = db.callHistoryDao()
    }

    @After
    fun teardown() = db.close()

    private fun sample(sync: Int, transfer: String, retry: Int) = CallHistory(
        userPhoneNumber = "01058921670",
        callDate = "2026-06-10",
        callTime = "10:00:00",
        phoneNumber = "01011112222",
        customerName = "신규",
        transferStatus = transfer,
        audioFileName = "f.wav",
        audioFilePath = "/tmp/f.wav",
        durationSeconds = 1,
        syncStatus = sync,
        retryCount = retry
    )

    @Test
    fun getRetryable_returnsOnlyFailedUnsyncedUnderCap() = runBlocking {
        dao.insert(sample(sync = 0, transfer = "실패", retry = 0))   // 포함
        dao.insert(sample(sync = 1, transfer = "성공", retry = 0))   // 제외: 전송완료
        dao.insert(sample(sync = 0, transfer = "전송중", retry = 0)) // 제외: 진행중
        dao.insert(sample(sync = 2, transfer = "실패", retry = 10))  // 제외: 영구실패
        dao.insert(sample(sync = 0, transfer = "실패", retry = 10))  // 제외: 상한 도달

        val result = dao.getRetryable(10)

        assertEquals(1, result.size)
        assertEquals("실패", result[0].transferStatus)
        assertEquals(0, result[0].syncStatus)
    }
}
