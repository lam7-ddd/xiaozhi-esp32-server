import json
from core.handle.abortHandle import handleAbortMessage
from core.handle.helloHandle import handleHelloMessage
from core.providers.tools.device_mcp import handle_mcp_message
from core.utils.util import remove_punctuation_and_length, filter_sensitive_info
from core.handle.receiveAudioHandle import startToChat, handleAudioMessage
from core.handle.sendAudioHandle import send_stt_message, send_tts_message
from core.providers.tools.device_iot import handleIotDescriptors, handleIotStatus
from core.handle.reportHandle import enqueue_asr_report
import asyncio

TAG = __name__


async def handleTextMessage(conn, message):
    """テキストメッセージを処理します"""
    try:
        msg_json = json.loads(message)
        if isinstance(msg_json, int):
            conn.logger.bind(tag=TAG).info(f"テキストメッセージを受信しました：{message}")
            await conn.websocket.send(message)
            return
        if msg_json["type"] == "hello":
            conn.logger.bind(tag=TAG).info(f"helloメッセージを受信しました：{message}")
            await handleHelloMessage(conn, msg_json)
        elif msg_json["type"] == "abort":
            conn.logger.bind(tag=TAG).info(f"abortメッセージを受信しました：{message}")
            await handleAbortMessage(conn)
        elif msg_json["type"] == "listen":
            conn.logger.bind(tag=TAG).info(f"listenメッセージを受信しました：{message}")
            if "mode" in msg_json:
                conn.client_listen_mode = msg_json["mode"]
                conn.logger.bind(tag=TAG).debug(
                    f"クライアントのピックアップモード：{conn.client_listen_mode}"
                )
            if msg_json["state"] == "start":
                conn.client_have_voice = True
                conn.client_voice_stop = False
            elif msg_json["state"] == "stop":
                conn.client_have_voice = True
                conn.client_voice_stop = True
                if len(conn.asr_audio) > 0:
                    await handleAudioMessage(conn, b"")
            elif msg_json["state"] == "detect":
                conn.client_have_voice = False
                conn.asr_audio.clear()
                if "text" in msg_json:
                    original_text = msg_json["text"]  # 元のテキストを保持
                    filtered_len, filtered_text = remove_punctuation_and_length(
                        original_text
                    )

                    # ウェイクアップワードかどうかを認識
                    is_wakeup_words = filtered_text in conn.config.get("wakeup_words")
                    # ウェイクアップワードの応答を有効にするかどうか
                    enable_greeting = conn.config.get("enable_greeting", True)

                    if is_wakeup_words and not enable_greeting:
                        # ウェイクアップワードであり、ウェイクアップワードの応答が無効になっている場合は、応答しない
                        await send_stt_message(conn, original_text)
                        await send_tts_message(conn, "stop", None)
                        conn.client_is_speaking = False
                    elif is_wakeup_words:
                        conn.just_woken_up = True
                        # 純粋なテキストデータをレポート（ASRレポート機能を再利用するが、音声データは提供しない）
                        enqueue_asr_report(conn, "こんにちは", [])
                        await startToChat(conn, "こんにちは")
                    else:
                        # 純粋なテキストデータをレポート（ASRレポート機能を再利用するが、音声データは提供しない）
                        enqueue_asr_report(conn, original_text, [])
                        # それ以外の場合は、LLMにテキストコンテンツに応答させる必要がある
                        await startToChat(conn, original_text)
        elif msg_json["type"] == "iot":
            conn.logger.bind(tag=TAG).info(f"iotメッセージを受信しました：{message}")
            if "descriptors" in msg_json:
                asyncio.create_task(handleIotDescriptors(conn, msg_json["descriptors"]))
            if "states" in msg_json:
                asyncio.create_task(handleIotStatus(conn, msg_json["states"]))
        elif msg_json["type"] == "mcp":
            conn.logger.bind(tag=TAG).info(f"mcpメッセージを受信しました：{message[:100]}")
            if "payload" in msg_json:
                asyncio.create_task(
                    handle_mcp_message(conn, conn.mcp_client, msg_json["payload"])
                )
        elif msg_json["type"] == "server":
            # ログを記録する際に機密情報をフィルタリング
            conn.logger.bind(tag=TAG).info(
                f"サーバーメッセージを受信しました：{filter_sensitive_info(msg_json)}"
            )
            # 設定がAPIから読み込まれている場合は、secretを検証する必要がある
            if not conn.read_config_from_api:
                return
            # postリクエストのsecretを取得
            post_secret = msg_json.get("content", {}).get("secret", "")
            secret = conn.config["manager-api"].get("secret", "")
            # secretが一致しない場合は、戻る
            if post_secret != secret:
                await conn.websocket.send(
                    json.dumps(
                        {
                            "type": "server",
                            "status": "error",
                            "message": "サーバーキーの検証に失敗しました",
                        }
                    )
                )
                return
            # 設定を動的に更新
            if msg_json["action"] == "update_config":
                try:
                    # WebSocketServerの設定を更新
                    if not conn.server:
                        await conn.websocket.send(
                            json.dumps(
                                {
                                    "type": "server",
                                    "status": "error",
                                    "message": "サーバーインスタンスを取得できません",
                                    "content": {"action": "update_config"},
                                }
                            )
                        )
                        return

                    if not await conn.server.update_config():
                        await conn.websocket.send(
                            json.dumps(
                                {
                                    "type": "server",
                                    "status": "error",
                                    "message": "サーバー設定の更新に失敗しました",
                                    "content": {"action": "update_config"},
                                }
                            )
                        )
                        return

                    # 成功応答を送信
                    await conn.websocket.send(
                        json.dumps(
                            {
                                "type": "server",
                                "status": "success",
                                "message": "設定の更新に成功しました",
                                "content": {"action": "update_config"},
                            }
                        )
                    )
                except Exception as e:
                    conn.logger.bind(tag=TAG).error(f"設定の更新に失敗しました: {str(e)}")
                    await conn.websocket.send(
                        json.dumps(
                            {
                                "type": "server",
                                "status": "error",
                                "message": f"設定の更新に失敗しました: {str(e)}",
                                "content": {"action": "update_config"},
                            }
                        )
                    )
            # サーバーを再起動
            elif msg_json["action"] == "restart":
                await conn.handle_restart(msg_json)
        else:
            conn.logger.bind(tag=TAG).error(f"不明なタイプのメッセージを受信しました：{message}")
    except json.JSONDecodeError:
        await conn.websocket.send(message)