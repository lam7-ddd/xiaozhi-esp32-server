import asyncio
import websockets
from config.logger import setup_logging
from core.connection import ConnectionHandler
from config.config_loader import get_config_from_api
from core.utils.modules_initialize import initialize_modules
from core.utils.util import check_vad_update, check_asr_update

TAG = __name__


class WebSocketServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.config_lock = asyncio.Lock()
        modules = initialize_modules(
            self.logger,
            self.config,
            "VAD" in self.config["selected_module"],
            "ASR" in self.config["selected_module"],
            "LLM" in self.config["selected_module"],
            False,
            "Memory" in self.config["selected_module"],
            "Intent" in self.config["selected_module"],
        )
        self._vad = modules["vad"] if "vad" in modules else None
        self._asr = modules["asr"] if "asr" in modules else None
        self._llm = modules["llm"] if "llm" in modules else None
        self._intent = modules["intent"] if "intent" in modules else None
        self._memory = modules["memory"] if "memory" in modules else None

        self.active_connections = set()

    async def start(self):
        server_config = self.config["server"]
        host = server_config.get("ip", "0.0.0.0")
        port = int(server_config.get("port", 8000))

        async with websockets.serve(
            self._handle_connection, host, port, process_request=self._http_response
        ):
            await asyncio.Future()

    async def _handle_connection(self, websocket):
        """新しい接続を処理し、毎回独立したConnectionHandlerを作成します"""
        # ConnectionHandlerを作成する際に現在のサーバーインスタンスを渡します
        handler = ConnectionHandler(
            self.config,
            self._vad,
            self._asr,
            self._llm,
            self._memory,
            self._intent,
            self,  # サーバーインスタンスを渡す
        )
        self.active_connections.add(handler)
        try:
            await handler.handle_connection(websocket)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"接続処理中にエラーが発生しました: {e}")
        finally:
            # アクティブな接続セットから確実に削除します
            self.active_connections.discard(handler)
            # 接続を強制的に閉じます（まだ閉じていない場合）
            try:
                # WebSocketの状態を安全にチェックして閉じます
                if hasattr(websocket, "closed") and not websocket.closed:
                    await websocket.close()
                elif hasattr(websocket, "state") and websocket.state.name != "CLOSED":
                    await websocket.close()
                else:
                    # closed属性がない場合は、直接クローズを試みます
                    await websocket.close()
            except Exception as close_error:
                self.logger.bind(tag=TAG).error(
                    f"サーバー側で接続を強制的に閉じる際にエラーが発生しました: {close_error}"
                )

    async def _http_response(self, websocket, request_headers):
        # WebSocketアップグレードリクエストかどうかを確認します
        if request_headers.headers.get("connection", "").lower() == "upgrade":
            # WebSocketリクエストの場合は、Noneを返してハンドシェイクを続行させます
            return None
        else:
            # 通常のHTTPリクエストの場合は、「server is running」を返します
            return websocket.respond(200, "Server is running\n")

    async def update_config(self) -> bool:
        """サーバー設定を更新し、コンポーネントを再初期化します

        Returns:
            bool: 更新が成功したかどうか
        """
        try:
            async with self.config_lock:
                # 設定を再取得
                new_config = get_config_from_api(self.config)
                if new_config is None:
                    self.logger.bind(tag=TAG).error("新しい設定の取得に失敗しました")
                    return False
                self.logger.bind(tag=TAG).info("新しい設定の取得に成功しました")
                # VADとASRのタイプを更新する必要があるか確認します
                update_vad = check_vad_update(self.config, new_config)
                update_asr = check_asr_update(self.config, new_config)
                self.logger.bind(tag=TAG).info(
                    f"VADとASRのタイプを更新する必要があるか確認: {update_vad} {update_asr}"
                )
                # 設定を更新
                self.config = new_config
                # コンポーネントを再初期化
                modules = initialize_modules(
                    self.logger,
                    new_config,
                    update_vad,
                    update_asr,
                    "LLM" in new_config["selected_module"],
                    False,
                    "Memory" in new_config["selected_module"],
                    "Intent" in new_config["selected_module"],
                )

                # コンポーネントインスタンスを更新
                if "vad" in modules:
                    self._vad = modules["vad"]
                if "asr" in modules:
                    self._asr = modules["asr"]
                if "llm" in modules:
                    self._llm = modules["llm"]
                if "intent" in modules:
                    self._intent = modules["intent"]
                if "memory" in modules:
                    self._memory = modules["memory"]
                self.logger.bind(tag=TAG).info("設定の更新タスクが完了しました")
                return True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"サーバー設定の更新に失敗しました: {str(e)}")
            return False