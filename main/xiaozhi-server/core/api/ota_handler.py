import json
import time
from aiohttp import web
from core.utils.util import get_local_ip
from core.api.base_handler import BaseHandler

TAG = __name__


class OTAHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)

    def _get_websocket_url(self, local_ip: str, port: int) -> str:
        """websocketアドレスを取得します

        Args:
            local_ip: ローカルIPアドレス
            port: ポート番号

        Returns:
            str: websocketアドレス
        """
        server_config = self.config["server"]
        websocket_config = server_config.get("websocket", "")

        if "あなたの" not in websocket_config:
            return websocket_config
        else:
            return f"ws://{local_ip}:{port}/xiaozhi/v1/"

    async def handle_post(self, request):
        """OTA POSTリクエストを処理します"""
        try:
            data = await request.text()
            self.logger.bind(tag=TAG).debug(f"OTAリクエストメソッド: {request.method}")
            self.logger.bind(tag=TAG).debug(f"OTAリクエストヘッダー: {request.headers}")
            self.logger.bind(tag=TAG).debug(f"OTAリクエストデータ: {data}")

            device_id = request.headers.get("device-id", "")
            if device_id:
                self.logger.bind(tag=TAG).info(f"OTAリクエストデバイスID: {device_id}")
            else:
                raise Exception("OTAリクエストのデバイスIDが空です")

            data_json = json.loads(data)

            server_config = self.config["server"]
            port = int(server_config.get("port", 8000))
            local_ip = get_local_ip()

            return_json = {
                "server_time": {
                    "timestamp": int(round(time.time() * 1000)),
                    "timezone_offset": server_config.get("timezone_offset", 8) * 60,
                },
                "firmware": {
                    "version": data_json["application"].get("version", "1.0.0"),
                    "url": "",
                },
                "websocket": {
                    "url": self._get_websocket_url(local_ip, port),
                },
            }
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        except Exception as e:
            return_json = {"success": False, "message": "request error."}
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        finally:
            self._add_cors_headers(response)
            return response

    async def handle_get(self, request):
        """OTA GETリクエストを処理します"""
        try:
            server_config = self.config["server"]
            local_ip = get_local_ip()
            port = int(server_config.get("port", 8000))
            websocket_url = self._get_websocket_url(local_ip, port)
            message = f"OTAインターフェースは正常に動作しています。デバイスに送信されるwebsocketアドレスは次のとおりです：{websocket_url}"
            response = web.Response(text=message, content_type="text/plain")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"OTA GETリクエスト例外: {e}")
            response = web.Response(text="OTAインターフェース例外", content_type="text/plain")
        finally:
            self._add_cors_headers(response)
            return response