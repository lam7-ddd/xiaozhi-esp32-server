from plugins_func.register import register_function, ToolType, ActionResponse, Action
from plugins_func.functions.hass_init import initialize_hass_handler
from config.logger import setup_logging
import asyncio
import requests

TAG = __name__
logger = setup_logging()

hass_get_state_function_desc = {
    "type": "function",
    "function": {
        "name": "hass_get_state",
        "description": "Home Assistantのデバイスの状態を取得します。照明の明るさ、色、色温度、メディアプレーヤーの音量、デバイスの一時停止、再開操作のクエリが含まれます。"
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "操作が必要なデバイスのID、Home Assistantのentity_id"
                }
            },
            "required": ["entity_id"],
        },
    },
}


@register_function("hass_get_state", hass_get_state_function_desc, ToolType.SYSTEM_CTL)
def hass_get_state(conn, entity_id=""):
    try:

        future = asyncio.run_coroutine_threadsafe(
            handle_hass_get_state(conn, entity_id), conn.loop
        )
        ha_response = future.result()
        return ActionResponse(Action.REQLLM, ha_response, None)
    except Exception as e:
        logger.bind(tag=TAG).error(f"属性設定インテントの処理エラー: {e}")


async def handle_hass_get_state(conn, entity_id):
    ha_config = initialize_hass_handler(conn)
    api_key = ha_config.get("api_key")
    base_url = ha_config.get("base_url")
    url = f"{base_url}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        responsetext = "デバイスの状態:" + response.json()["state"] + " "
        logger.bind(tag=TAG).info(f"APIからのレスポンス内容: {response.json()}")

        if "media_title" in response.json()["attributes"]:
            responsetext = (
                responsetext
                + "再生中:"
                + str(response.json()["attributes"]["media_title"])
                + " "
            )
        if "volume_level" in response.json()["attributes"]:
            responsetext = (
                responsetext
                + "音量:"
                + str(response.json()["attributes"]["volume_level"])
                + " "
            )
        if "color_temp_kelvin" in response.json()["attributes"]:
            responsetext = (
                responsetext
                + "色温度:"
                + str(response.json()["attributes"]["color_temp_kelvin"])
                + " "
            )
        if "rgb_color" in response.json()["attributes"]:
            responsetext = (
                responsetext
                + "RGBカラー:"
                + str(response.json()["attributes"]["rgb_color"])
                + " "
            )
        if "brightness" in response.json()["attributes"]:
            responsetext = (
                responsetext
                + "明るさ:"
                + str(response.json()["attributes"]["brightness"])
                + " "
            )
        logger.bind(tag=TAG).info(f"クエリのレスポンス内容: {responsetext}")
        return responsetext
        # return response.json()['attributes']
        # response.attributes

    else:
        return f"切り替えに失敗しました、エラーコード: {response.status_code}"
