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
        val tvCustomerName: TextView = view.findViewById(R.id.tvCustomerName)
        val tvPhoneNumber: TextView = view.findViewById(R.id.tvPhoneNumber)
        val tvCallTime: TextView = view.findViewById(R.id.tvCallTime)
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

        holder.tvCustomerName.text = item.customerName
        holder.tvPhoneNumber.text = item.phoneNumber
        holder.tvCallTime.text = "${item.callDate} ${item.callTime}"
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
