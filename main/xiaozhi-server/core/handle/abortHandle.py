import json

TAG = __name__


async def handleAbortMessage(conn):
    conn.logger.bind(tag=TAG).info("中断メッセージを受信しました")
    # 中断状態に設定すると、llm、ttsタスクが自動的に中断されます
    conn.client_abort = True
    conn.clear_queues()
    # クライアントの話す状態を中断します
    await conn.websocket.send(
        json.dumps({"type": "tts", "state": "stop", "session_id": conn.session_id})
    )
    conn.clearSpeakStatus()
    conn.logger.bind(tag=TAG).info("中断メッセージの受信が完了しました")