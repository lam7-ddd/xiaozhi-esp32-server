import json
import asyncio
import uuid
from core.handle.sendAudioHandle import send_stt_message
from core.handle.helloHandle import checkWakeupWords
from core.utils.util import remove_punctuation_and_length
from core.providers.tts.dto.dto import ContentType
from core.utils.dialogue import Message
from core.providers.tools.device_mcp import call_mcp_tool
from plugins_func.register import Action, ActionResponse
from loguru import logger

TAG = __name__


async def handle_user_intent(conn, text):
    # 明確な終了コマンドがあるか確認
    filtered_text = remove_punctuation_and_length(text)[1]
    if await check_direct_exit(conn, filtered_text):
        return True
    # ウェイクアップワードかどうかを確認
    if await checkWakeupWords(conn, filtered_text):
        return True

    if conn.intent_type == "function_call":
        # function callingをサポートするチャットメソッドを使用し、意図分析は行わない
        return False
    # LLMを使用して意図を分析
    intent_result = await analyze_intent_with_llm(conn, text)
    if not intent_result:
        return False
    # 様々な意図を処理
    return await process_intent_result(conn, intent_result, text)


async def check_direct_exit(conn, text):
    """明確な終了コマンドがあるか確認します"""
    _, text = remove_punctuation_and_length(text)
    cmd_exit = conn.cmd_exit
    for cmd in cmd_exit:
        if text == cmd:
            conn.logger.bind(tag=TAG).info(f"明確な終了コマンドを認識しました: {text}")
            await send_stt_message(conn, text)
            await conn.close()
            return True
    return False


async def analyze_intent_with_llm(conn, text):
    """LLMを使用してユーザーの意図を分析します"""
    if not hasattr(conn, "intent") or not conn.intent:
        conn.logger.bind(tag=TAG).warning("意図認識サービスが初期化されていません")
        return None

    # 対話履歴
    dialogue = conn.dialogue
    try:
        intent_result = await conn.intent.detect_intent(conn, dialogue.dialogue, text)
        return intent_result
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"意図認識に失敗しました: {str(e)}")

    return None


async def process_intent_result(conn, intent_result, original_text):
    """意図認識結果を処理します"""
    try:
        # 結果をJSONとして解析しようと試みる
        intent_data = json.loads(intent_result)

        # function_callがあるか確認
        if "function_call" in intent_data:
            # 意図認識から直接function_callを取得
            conn.logger.bind(tag=TAG).debug(
                f"function_call形式の意図結果を検出しました: {intent_data['function_call']['name']}"
            )
            function_name = intent_data["function_call"]["name"]
            if function_name == "continue_chat":
                return False

            function_args = {}
            if "arguments" in intent_data["function_call"]:
                function_args = intent_data["function_call"]["arguments"]
                if function_args is None:
                    function_args = {}
            # パラメータが文字列形式のJSONであることを確認
            if isinstance(function_args, dict):
                function_args = json.dumps(function_args)

            function_call_data = {
                "name": function_name,
                "id": str(uuid.uuid4().hex),
                "arguments": function_args,
            }

            await send_stt_message(conn, original_text)
            conn.client_abort = False

            # executorを使用して関数呼び出しと結果処理を実行
            def process_function_call():
                conn.dialogue.put(Message(role="user", content=original_text))

                # 統一ツールハンドラを使用してすべてのツール呼び出しを処理
                try:
                    result = asyncio.run_coroutine_threadsafe(
                        conn.func_handler.handle_llm_function_call(
                            conn, function_call_data
                        ),
                        conn.loop,
                    ).result()
                except Exception as e:
                    conn.logger.bind(tag=TAG).error(f"ツール呼び出しに失敗しました: {e}")
                    result = ActionResponse(
                        action=Action.ERROR, result=str(e), response=str(e)
                    )

                if result:
                    if result.action == Action.RESPONSE:  # フロントエンドに直接応答
                        text = result.response
                        if text is not None:
                            speak_txt(conn, text)
                    elif result.action == Action.REQLLM:  # 関数を呼び出した後、llmに再度リクエストして応答を生成
                        text = result.result
                        conn.dialogue.put(Message(role="tool", content=text))
                        llm_result = conn.intent.replyResult(text, original_text)
                        if llm_result is None:
                            llm_result = text
                        speak_txt(conn, llm_result)
                    elif (
                        result.action == Action.NOTFOUND
                        or result.action == Action.ERROR
                    ):
                        text = result.result
                        if text is not None:
                            speak_txt(conn, text)
                    elif function_name != "play_music":
                        # 元のコードとの下位互換性のため
                        # 最新のテキストインデックスを取得
                        text = result.response
                        if text is None:
                            text = result.result
                        if text is not None:
                            speak_txt(conn, text)

            # 関数実行をスレッドプールに配置
            conn.executor.submit(process_function_call)
            return True
        return False
    except json.JSONDecodeError as e:
        conn.logger.bind(tag=TAG).error(f"意図結果の処理中にエラーが発生しました: {e}")
        return False


def speak_txt(conn, text):
    conn.tts.tts_one_sentence(conn, ContentType.TEXT, content_detail=text)
    conn.dialogue.put(Message(role="assistant", content=text))