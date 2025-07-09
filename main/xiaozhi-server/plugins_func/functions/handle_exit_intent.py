from plugins_func.register import register_function, ToolType, ActionResponse, Action
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

handle_exit_intent_function_desc = {
    "type": "function",
    "function": {
        "name": "handle_exit_intent",
        "description": "ユーザーが対話を終了したい、またはシステムを終了する必要がある場合に呼び出されます。"
        "parameters": {
            "type": "object",
            "properties": {
                "say_goodbye": {
                    "type": "string",
                    "description": "ユーザーとの対話を友好的に終了するための別れの言葉。"
                }
            },
            "required": ["say_goodbye"],
        },
    },
}


@register_function(
    "handle_exit_intent", handle_exit_intent_function_desc, ToolType.SYSTEM_CTL
)
def handle_exit_intent(conn, say_goodbye: str | None = None):
    # 終了インテントの処理
    try:
        if say_goodbye is None:
            say_goodbye = "さようなら、どうぞお元気で！"
        conn.close_after_chat = True
        logger.bind(tag=TAG).info(f"終了インテントが処理されました:{say_goodbye}")
        return ActionResponse(
            action=Action.RESPONSE, result="終了インテントが処理されました", response=say_goodbye
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"終了インテントの処理エラー: {e}")
        return ActionResponse(
            action=Action.NONE, result="終了インテントの処理に失敗しました", response=""
        )
