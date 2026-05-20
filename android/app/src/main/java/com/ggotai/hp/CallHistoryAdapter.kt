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

    class ViewHolder(view: View) : RecyclerView.ViewHolder(view) {
        val tvNo: TextView = view.findViewById(R.id.tvNo)
        val tvCustomerName: TextView = view.findViewById(R.id.tvCustomerName)
        val tvPhoneNumber: TextView = view.findViewById(R.id.tvPhoneNumber)
        val tvCallDate: TextView = view.findViewById(R.id.tvCallDate)
        val tvCallTimeShort: TextView = view.findViewById(R.id.tvCallTimeShort)
        val tvStatus: TextView = view.findViewById(R.id.tvStatus)
        val btnPlay: ImageView = view.findViewById(R.id.btnPlay)
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
        holder.tvPhoneNumber.text = "${item.phoneNumber} ($durationText)"

        val formattedDate = item.callDate.replace("-", ".")
        holder.tvCallDate.text = formattedDate

        val timeShort = if (timeParts.size >= 2) "${timeParts[0]}:${timeParts[1]}" else item.callTime
        holder.tvCallTimeShort.text = timeShort

        holder.tvStatus.text = item.transferStatus

        when (item.transferStatus) {
            "성공" -> holder.tvStatus.setTextColor(Color.parseColor("#212121")) // Black
            "실패" -> holder.tvStatus.setTextColor(Color.parseColor("#D50000")) // Red
            else -> holder.tvStatus.setTextColor(Color.parseColor("#757575")) // Gray
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
