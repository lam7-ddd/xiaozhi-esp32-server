import time
import json
import random
import asyncio
from core.utils.dialogue import Message
from core.utils.util import audio_to_data
from core.handle.sendAudioHandle import sendAudioMessage, send_stt_message
from core.utils.util import remove_punctuation_and_length, opus_datas_to_wav_bytes
from core.providers.tts.dto.dto import ContentType, SentenceType
from core.providers.tools.device_mcp import (
    MCPClient,
    send_mcp_initialize_message,
    send_mcp_tools_list_request,
)
from core.utils.wakeup_word import WakeupWordsConfig

TAG = __name__

WAKEUP_CONFIG = {
    "refresh_time": 5,
    "words": ["こんにちは", "やあ", "ねえ、こんにちは", "ハイ"],
}

# グローバルなウェイクアップワード設定マネージャーを作成
wakeup_words_config = WakeupWordsConfig()

# wakeupWordsResponseの同時呼び出しを防ぐためのロック
_wakeup_response_lock = asyncio.Lock()


async def handleHelloMessage(conn, msg_json):
    """helloメッセージを処理します"""
    audio_params = msg_json.get("audio_params")
    if audio_params:
        format = audio_params.get("format")
        conn.logger.bind(tag=TAG).info(f"クライアントのオーディオ形式: {format}")
        conn.audio_format = format
        conn.welcome_msg["audio_params"] = audio_params
    features = msg_json.get("features")
    if features:
        conn.logger.bind(tag=TAG).info(f"クライアントの機能: {features}")
        conn.features = features
        if features.get("mcp"):
            conn.logger.bind(tag=TAG).info("クライアントはMCPをサポートしています")
            conn.mcp_client = MCPClient()
            # 初期化を送信
            asyncio.create_task(send_mcp_initialize_message(conn))
            # mcpメッセージを送信して、toolsリストを取得
            asyncio.create_task(send_mcp_tools_list_request(conn))

    await conn.websocket.send(json.dumps(conn.welcome_msg))


async def checkWakeupWords(conn, text):
    enable_wakeup_words_response_cache = conn.config[
        "enable_wakeup_words_response_cache"
    ]

    if not enable_wakeup_words_response_cache or not conn.tts:
        return False

    _, filtered_text = remove_punctuation_and_length(text)
    if filtered_text not in conn.config.get("wakeup_words"):
        return False

    conn.just_woken_up = True
    await send_stt_message(conn, text)

    # 現在の音色を取得
    voice = getattr(conn.tts, "voice", "default")
    if not voice:
        voice = "default"

    # ウェイクアップワードの応答設定を取得
    response = wakeup_words_config.get_wakeup_response(voice)
    if not response or not response.get("file_path"):
        response = {
            "voice": "default",
            "file_path": "config/assets/wakeup_words.wav",
            "time": 0,
            "text": "こんにちは、私はシャオジーです。あなたの声が聞けてうれしいです。最近何をしていますか？何か面白い話があったら教えてくださいね。",
        }

    # ウェイクアップワードの応答を再生
    conn.client_abort = False
    opus_packets, _ = audio_to_data(response.get("file_path"))

    conn.logger.bind(tag=TAG).info(f"ウェイクアップワードの応答を再生: {response.get('text')}")
    await sendAudioMessage(conn, SentenceType.FIRST, opus_packets, response.get("text"))
    await sendAudioMessage(conn, SentenceType.LAST, [], None)

    # 対話を補足
    conn.dialogue.put(Message(role="assistant", content=response.get("text")))

    # ウェイクアップワードの応答を更新する必要があるか確認
    if time.time() - response.get("time", 0) > WAKEUP_CONFIG["refresh_time"]:
        if not _wakeup_response_lock.locked():
            asyncio.create_task(wakeupWordsResponse(conn))
    return True


async def wakeupWordsResponse(conn):
    if not conn.tts or not conn.llm or not conn.llm.response_no_stream:
        return

    try:
        # ロックの取得を試み、取得できない場合は戻る
        if not await _wakeup_response_lock.acquire():
            return

        # ウェイクアップワードの応答を生成
        wakeup_word = random.choice(WAKEUP_CONFIG["words"])
        question = (
            "現在、ユーザーはあなたに\""
            + wakeup_word
            + "\"と言っています。
このユーザーの内容に基づいて、20〜30語で応答してください。システム設定の役割の感情と態度に合わせ、ロボットのように話さないでください。
"
            + "この内容自体についての説明や応答はしないでください。絵文字は返さず、ユーザーの内容に対する応答のみを返してください。"
        )

        result = conn.llm.response_no_stream(conn.config["prompt"], question)
        if not result or len(result) == 0:
            return

        # TTS音声を生成
        tts_result = await asyncio.to_thread(conn.tts.to_tts, result)
        if not tts_result:
            return

        # 現在の音色を取得
        voice = getattr(conn.tts, "voice", "default")

        wav_bytes = opus_datas_to_wav_bytes(tts_result, sample_rate=16000)
        file_path = wakeup_words_config.generate_file_path(voice)
        with open(file_path, "wb") as f:
            f.write(wav_bytes)
        # 設定を更新
        wakeup_words_config.update_wakeup_response(voice, file_path, result)
    finally:
        # どのような状況でも必ずロックを解放
        if _wakeup_response_lock.locked():
            _wakeup_response_lock.release()