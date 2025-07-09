from plugins_func.register import register_function, ToolType, ActionResponse, Action
from plugins_func.functions.hass_init import initialize_hass_handler
from config.logger import setup_logging
import asyncio
import requests

TAG = __name__
logger = setup_logging()

hass_set_state_function_desc = {
    "type": "function",
    "function": {
        "name": "hass_set_state",
        "description": "Home Assistantのデバイスの状態を設定します。オン、オフ、照明の明るさ、色、色温度の調整、プレーヤーの音量調整、デバイスの一時停止、再開、ミュート操作が含まれます。"
        "parameters": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "description": "操作するアクション。デバイスをオンにする:turn_on、デバイスをオフにする:turn_off、明るさを上げる:brightness_up、明るさを下げる:brightness_down、明るさを設定する:brightness_value、音量を上げる:volume_up、音量を下げる:volume_down、音量を設定する:volume_set、色温度を設定する:set_kelvin、色を設定する:set_color、デバイスを一時停止する:pause、デバイスを再開する:continue、ミュート/ミュート解除:volume_mute"
                        },
                        "input": {
                            "type": "integer",
                            "description": "音量または明るさを設定する場合にのみ必要です。有効値は1〜100で、音量と明るさの1%〜100%に対応します。"
                        },
                        "is_muted": {
                            "type": "string",
                            "description": "ミュート操作を設定する場合にのみ必要です。ミュートを設定する場合はtrue、ミュートを解除する場合はfalseに設定します。"
                        },
                        "rgb_color": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "色を設定する場合にのみ必要です。ここにターゲットの色のRGB値を入力します。"
                        },
                    },
                    "required": ["type"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "操作するデバイスのID、Home Assistantのentity_id"
                },
            },
            "required": ["state", "entity_id"],
        },
    },
}


@register_function("hass_set_state", hass_set_state_function_desc, ToolType.SYSTEM_CTL)
def hass_set_state(conn, entity_id="", state={}):
    try:
        future = asyncio.run_coroutine_threadsafe(
            handle_hass_set_state(conn, entity_id, state), conn.loop
        )
        ha_response = future.result()
        return ActionResponse(Action.REQLLM, ha_response, None)
    except Exception as e:
        logger.bind(tag=TAG).error(f"属性設定インテントの処理エラー: {e}")


async def handle_hass_set_state(conn, entity_id, state):
    ha_config = initialize_hass_handler(conn)
    api_key = ha_config.get("api_key")
    base_url = ha_config.get("base_url")
    """
    state = { "type":"brightness_up","input":"80","is_muted":"true"}
    """
    domains = entity_id.split(".")
    if len(domains) > 1:
        domain = domains[0]
    else:
        return "実行に失敗しました、不正なデバイスIDです"
    action = ""
    arg = ""
    value = ""
    if state["type"] == "turn_on":
        description = "デバイスがオンになりました"
        if domain == "cover":
            action = "open_cover"
        elif domain == "vacuum":
            action = "start"
        else:
            action = "turn_on"
    elif state["type"] == "turn_off":
        description = "デバイスがオフになりました"
        if domain == "cover":
            action = "close_cover"
        elif domain == "vacuum":
            action = "stop"
        else:
            action = "turn_off"
    elif state["type"] == "brightness_up":
        description = "ライトが明るくなりました"
        action = "turn_on"
        arg = "brightness_step_pct"
        value = 10
    elif state["type"] == "brightness_down":
        description = "ライトが暗くなりました"
        action = "turn_on"
        arg = "brightness_step_pct"
        value = -10
    elif state["type"] == "brightness_value":
        description = f"明るさが{state['input']}に調整されました"
        action = "turn_on"
        arg = "brightness_pct"
        value = state["input"]
    elif state["type"] == "set_color":
        description = f"色が{state['rgb_color']}に調整されました"
        action = "turn_on"
        arg = "rgb_color"
        value = state["rgb_color"]
    elif state["type"] == "set_kelvin":
        description = f"色温度が{state['input']}Kに調整されました"
        action = "turn_on"
        arg = "kelvin"
        value = state["input"]
    elif state["type"] == "volume_up":
        description = "音量が上がりました"
        action = state["type"]
    elif state["type"] == "volume_down":
        description = "音量が下がりました"
        action = state["type"]
    elif state["type"] == "volume_set":
        description = f"音量が{state['input']}に調整されました"
        action = state["type"]
        arg = "volume_level"
        value = state["input"]
        if state["input"] >= 1:
            value = state["input"] / 100
    elif state["type"] == "volume_mute":
        description = f"デバイスがミュートされました"
        action = state["type"]
        arg = "is_volume_muted"
        value = state["is_muted"]
    elif state["type"] == "pause":
        description = f"デバイスが一時停止しました"
        action = state["type"]
        if domain == "media_player":
            action = "media_pause"
        if domain == "cover":
            action = "stop_cover"
        if domain == "vacuum":
            action = "pause"
    elif state["type"] == "continue":
        description = f"デバイスが再開しました"
        if domain == "media_player":
            action = "media_play"
        if domain == "vacuum":
            action = "start"
    else:
        return f"{domain} {state.type}機能はまだサポートされていません"

    if arg == "":
        data = {
            "entity_id": entity_id,
        }
    else:
        data = {"entity_id": entity_id, arg: value}
    url = f"{base_url}/api/services/{domain}/{action}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=data)
    logger.bind(tag=TAG).info(
        f"状態設定:{description},url:{url},return_code:{response.status_code}"
    )
    if response.status_code == 200:
        return description
    else:
        return f"設定に失敗しました、エラーコード: {response.status_code}"
