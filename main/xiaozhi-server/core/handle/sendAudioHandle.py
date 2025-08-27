import json
import asyncio
import time
from core.providers.tts.dto.dto import SentenceType
from core.utils.util import get_string_no_punctuation_or_emoji, analyze_emotion
from loguru import logger

TAG = __name__

emoji_map = {
    "neutral": "😶",
    "happy": "🙂",
    "laughing": "😆",
    "funny": "😂",
    "sad": "😔",
    "angry": "😠",
    "crying": "😭",
    "loving": "😍",
    "embarrassed": "😳",
    "surprised": "😲",
    "shocked": "😱",
    "thinking": "🤔",
    "winking": "😉",
    "cool": "😎",
    "relaxed": "😌",
    "delicious": "🤤",
    "kissy": "😘",
    "confident": "😏",
    "sleepy": "😴",
    "silly": "😜",
    "confused": "🙄",
}


async def sendAudioMessage(conn, sentenceType, audios, text):
    # 文の開始メッセージを送信
    conn.logger.bind(tag=TAG).info(f"オーディオメッセージを送信: {sentenceType}, {text}")
    if text is not None:
        emotion = analyze_emotion(text)
        emoji = emoji_map.get(emotion, "🙂")  # デフォルトでスマイリーを使用
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "llm",
                    "text": emoji,
                    "emotion": emotion,
                    "session_id": conn.session_id,
                }
            )
        )
    pre_buffer = False
    if conn.tts.tts_audio_first_sentence and text is not None:
        conn.logger.bind(tag=TAG).info(f"最初の音声セグメントを送信: {text}")
        conn.tts.tts_audio_first_sentence = False
        pre_buffer = True

    await send_tts_message(conn, "sentence_start", text)

    await sendAudio(conn, audios, pre_buffer)

    await send_tts_message(conn, "sentence_end", text)

    # 終了メッセージを送信（最後のテキストの場合）
    if conn.llm_finish_task and sentenceType == SentenceType.LAST:
        await send_tts_message(conn, "stop", None)
        conn.client_is_speaking = False
        if conn.close_after_chat:
            await conn.close()


# オーディオを再生
async def sendAudio(conn, audios, pre_buffer=True):
    if audios is None or len(audios) == 0:
        return
    # フロー制御パラメータの最適化
    frame_duration = 60  # フレーム時間（ミリ秒）、Opusエンコーディングに一致
    start_time = time.perf_counter()
    play_position = 0
    last_reset_time = time.perf_counter()  # 最後のリセット時間を記録

    # 最初の文の場合のみプリバッファリングを実行
    if pre_buffer:
        pre_buffer_frames = min(3, len(audios))
        for i in range(pre_buffer_frames):
            await conn.websocket.send(audios[i])
        remaining_audios = audios[pre_buffer_frames:]
    else:
        remaining_audios = audios

    # 残りのオーディオフレームを再生
    for opus_packet in remaining_audios:
        if conn.client_abort:
            break

        # 音声がない状態をリセット
        conn.last_activity_time = time.time() * 1000

        # 期待される送信時間を計算
        expected_time = start_time + (play_position / 1000)
        current_time = time.perf_counter()
        delay = expected_time - current_time
        if delay > 0:
            await asyncio.sleep(delay)

        await conn.websocket.send(opus_packet)

        play_position += frame_duration


async def send_tts_message(conn, state, text=None):
    """TTS状態メッセージを送信"""
    message = {"type": "tts", "state": state, "session_id": conn.session_id}
    if text is not None:
        message["text"] = text

    # TTS再生終了
    if state == "stop":
        # プロンプト音を再生
        tts_notify = conn.config.get("enable_stop_tts_notify", False)
        if tts_notify:
            stop_tts_notify_voice = conn.config.get(
                "stop_tts_notify_voice", "config/assets/tts_notify.mp3"
            )
            audios, _ = conn.tts.audio_to_opus_data(stop_tts_notify_voice)
            await sendAudio(conn, audios)
        # サーバーサイドの話す状態をクリア
        conn.clearSpeakStatus()

    # メッセージをクライアントに送信
    await conn.websocket.send(json.dumps(message))


async def send_stt_message(conn, text):
    end_prompt_str = conn.config.get("end_prompt", {}).get("prompt")
    if end_prompt_str and end_prompt_str == text:
        await send_tts_message(conn, "start")
        return

    """STT状態メッセージを送信"""
    stt_text = get_string_no_punctuation_or_emoji(text)
    await conn.websocket.send(
        json.dumps({"type": "stt", "text": stt_text, "session_id": conn.session_id})
    )
    conn.client_is_speaking = True
    await send_tts_message(conn, "start")