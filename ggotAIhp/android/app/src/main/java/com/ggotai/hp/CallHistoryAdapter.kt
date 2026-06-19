package com.ggotai.hp

import android.graphics.Color
import android.media.MediaPlayer
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.recyclerview.widget.RecyclerView
import com.ggotai.hp.db.CallHistory
import java.io.IOException

class CallHistoryAdapter(private var historyList: List<CallHistory>) :
    RecyclerView.Adapter<CallHistoryAdapter.ViewHolder>() {

    private var mediaPlayer: MediaPlayer? = null
    private var playingUrl: String? = null

    interface OnItemLongClickListener {
        fun onItemLongClick(item: CallHistory)
    }

    private var longClickListener: OnItemLongClickListener? = null

    fun setOnItemLongClickListener(listener: OnItemLongClickListener) {
        this.longClickListener = listener
    }

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvNo: TextView = view.findViewById(R.id.tvNo)
        val tvCustomerName: TextView = view.findViewById(R.id.tvCustomerName)
        val tvPhoneNumber: TextView = view.findViewById(R.id.tvPhoneNumber)
        val tvCallDate: TextView = view.findViewById(R.id.tvCallDate)
        val tvCallTimeShort: TextView = view.findViewById(R.id.tvCallTimeShort)
        val tvStatus: TextView = view.findViewById(R.id.tvStatus)
        val btnPlay: ImageView = view.findViewById(R.id.btnPlay)
        val tvInitial: TextView = view.findViewById(R.id.tvInitial)
        val tvDuration: TextView = view.findViewById(R.id.tvDuration)
        val tvCallDateTime: TextView = view.findViewById(R.id.tvCallDateTime)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_call_history, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = historyList[position]

        holder.tvNo.text = (position + 1).toString()
        holder.tvCustomerName.text = item.customerName
        
        // 좌측 아바타에 수신/발신 종류 표시 (발신='발', 그 외 수신·부재중 등='수')
        // callType이 없는 레거시 행은 기존처럼 고객명 첫 글자로 대체한다.
        holder.tvInitial.text = when (item.callType) {
            null -> if (!item.customerName.isNullOrEmpty()) item.customerName.substring(0, 1) else "신"
            android.provider.CallLog.Calls.OUTGOING_TYPE -> "발"
            else -> "수"
        }
        
        val timeParts = item.callTime.split(":")
        
        // 실제 통화 시간(초)을 가독성 높게 포맷팅 (예: 37초, 1분 15초)
        val durationSec = item.durationSeconds ?: 0
        val durationText = when {
            durationSec <= 0 -> "0초"
            durationSec >= 60 -> {
                val min = durationSec / 60
                val sec = durationSec % 60
                if (sec > 0) "${min}분 ${sec}초" else "${min}분"
            }
            else -> "${durationSec}초"
        }
        holder.tvDuration.text = " ($durationText)"
        holder.tvPhoneNumber.text = item.phoneNumber

        val formattedDate = item.callDate.replace("-", ".")
        holder.tvCallDate.text = formattedDate

        val timeShort = if (timeParts.size >= 2) "${timeParts[0]}:${timeParts[1]}" else item.callTime
        holder.tvCallTimeShort.text = timeShort

        // 통합 통화일시 바인딩 (예: "2026.05.21 · 15:25")
        holder.tvCallDateTime.text = "$formattedDate · $timeShort"

        holder.tvStatus.text = item.transferStatus

        // 상태별 뱃지 배경색과 텍스트 컬러 지정 (알약 모양 뱃지)
        val context = holder.itemView.context
        when (item.transferStatus) {
            "성공" -> {
                holder.tvStatus.setBackgroundResource(R.drawable.bg_badge_success)
                holder.tvStatus.setTextColor(androidx.core.content.ContextCompat.getColor(context, R.color.badge_success_text))
            }
            "실패" -> {
                holder.tvStatus.setBackgroundResource(R.drawable.bg_badge_failed)
                holder.tvStatus.setTextColor(androidx.core.content.ContextCompat.getColor(context, R.color.badge_failed_text))
            }
            else -> {
                holder.tvStatus.setBackgroundResource(R.drawable.bg_badge_pending)
                holder.tvStatus.setTextColor(androidx.core.content.ContextCompat.getColor(context, R.color.badge_pending_text))
            }
        }

        holder.btnPlay.setOnClickListener {
            playAudio(item.audioFilePath, holder)
        }
        
        holder.itemView.setOnClickListener {
            if (item.transferStatus == "실패") {
                val intent = android.content.Intent(holder.itemView.context, ResendActivity::class.java)
                intent.putExtra("HISTORY_ID", item.id)
                holder.itemView.context.startActivity(intent)
            }
        }

        holder.itemView.setOnLongClickListener {
            longClickListener?.onItemLongClick(item)
            true
        }
    }

    override fun getItemCount() = historyList.size

    fun updateData(newList: List<CallHistory>) {
        historyList = newList
        notifyDataSetChanged()
    }

    private fun playAudio(filePath: String, holder: ViewHolder) {
        if (playingUrl == filePath && mediaPlayer?.isPlaying == true) {
            mediaPlayer?.pause()
            holder.btnPlay.setImageResource(android.R.drawable.ic_media_play)
            return
        }

        if (mediaPlayer == null) {
            mediaPlayer = MediaPlayer()
        }

        try {
            mediaPlayer?.reset()
            mediaPlayer?.setDataSource(filePath)
            mediaPlayer?.prepare()
            mediaPlayer?.start()
            playingUrl = filePath

            holder.btnPlay.setImageResource(android.R.drawable.ic_media_pause)

            mediaPlayer?.setOnCompletionListener {
                holder.btnPlay.setImageResource(android.R.drawable.ic_media_play)
                playingUrl = null
            }

        } catch (e: IOException) {
            Log.e("CallHistoryAdapter", "Audio play failed", e)
            Toast.makeText(holder.itemView.context, "파일을 재생할 수 없습니다.", Toast.LENGTH_SHORT).show()
        }
    }
}
