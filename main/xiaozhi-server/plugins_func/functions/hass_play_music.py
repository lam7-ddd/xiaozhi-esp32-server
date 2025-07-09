from plugins_func.register import register_function, ToolType, ActionResponse, Action
from plugins_func.functions.hass_init import initialize_hass_handler
from config.logger import setup_logging
import asyncio
import requests

TAG = __name__
logger = setup_logging()

hass_play_music_function_desc = {
    "type": "function",
    "function": {
        "name": "hass_play_music",
        "description": "ユーザーが音楽やオーディオブックを聴きたいときに使用し、部屋のメディアプレーヤー（media_player）で対応するオーディオを再生します", 
        "parameters": {
            "type": "object",
            "properties": {
                "media_content_id": {
                    "type": "string",
                    "description": "音楽やオーディオブックのアルバム名、曲名、アーティスト名などを指定できます。指定しない場合は「random」と入力してください",
                },
                "entity_id": {
                    "type": "string",
                    "description": "操作が必要なスピーカーのデバイスID、Home Assistantのentity_idで、media_playerで始まります",
                },
            },
            "required": ["media_content_id", "entity_id"],
        },
    },
}


@register_function(
    "hass_play_music", hass_play_music_function_desc, ToolType.SYSTEM_CTL
)
def hass_play_music(conn, entity_id="", media_content_id="random"):
    try:
        # 音楽再生コマンドを実行
        future = asyncio.run_coroutine_threadsafe(
            handle_hass_play_music(conn, entity_id, media_content_id), conn.loop
        )
        ha_response = future.result()
        return ActionResponse(
            action=Action.RESPONSE, result="音楽再生の意図は処理されました", response=ha_response
        )
    except Exception as e:
        logger.bind(tag=TAG).error(f"音楽の意図の処理中にエラーが発生しました: {e}")


async def handle_hass_play_music(conn, entity_id, media_content_id):
    ha_config = initialize_hass_handler(conn)
    api_key = ha_config.get("api_key")
    base_url = ha_config.get("base_url")
    url = f"{base_url}/api/services/music_assistant/play_media"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"entity_id": entity_id, "media_id": media_content_id}
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return f"{media_content_id}の音楽を再生しています"
    else:
        return f"音楽の再生に失敗しました、エラーコード: {response.status_code}"
