import os
import sys
import copy
import json
import uuid
import time
import queue
import asyncio
import threading
import traceback
import subprocess
import websockets
from core.utils.util import (
    extract_json_from_string,
    check_vad_update,
    check_asr_update,
    filter_sensitive_info,
)
from typing import Dict, Any
from core.utils.modules_initialize import (
    initialize_modules,
    initialize_tts,
    initialize_asr,
)
from core.handle.reportHandle import report
from core.providers.tts.default import DefaultTTS
from concurrent.futures import ThreadPoolExecutor
from core.utils.dialogue import Message, Dialogue
from core.providers.asr.dto.dto import InterfaceType
from core.handle.textHandle import handleTextMessage
from core.providers.tools.unified_tool_handler import UnifiedToolHandler
from plugins_func.loadplugins import auto_import_modules
from plugins_func.register import Action, ActionResponse
from core.auth import AuthMiddleware, AuthenticationError
from config.config_loader import get_private_config_from_api
from core.providers.tts.dto.dto import ContentType, TTSMessageDTO, SentenceType
from config.logger import setup_logging, build_module_string, update_module_string
from config.manage_api_client import DeviceNotFoundException, DeviceBindException


TAG = __name__

auto_import_modules("plugins_func.functions")


class TTSException(RuntimeError):
    pass


class ConnectionHandler:
    def __init__(
        self,
        config: Dict[str, Any],
        _vad,
        _asr,
        _llm,
        _memory,
        _intent,
        server=None,
    ):
        self.common_config = config
        self.config = copy.deepcopy(config)
        self.session_id = str(uuid.uuid4())
        self.logger = setup_logging()
        self.server = server  # サーバーインスタンスへの参照を保存

        self.auth = AuthMiddleware(config)
        self.need_bind = False
        self.bind_code = None
        self.read_config_from_api = self.config.get("read_config_from_api", False)

        self.websocket = None
        self.headers = None
        self.device_id = None
        self.client_ip = None
        self.client_ip_info = {}
        self.prompt = None
        self.welcome_msg = None
        self.max_output_size = 0
        self.chat_history_conf = 0
        self.audio_format = "opus"

        # クライアントの状態関連
        self.client_abort = False
        self.client_is_speaking = False
        self.client_listen_mode = "auto"

        # スレッドタスク関連
        self.loop = asyncio.get_event_loop()
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=5)

        # レポート用スレッドプールを追加
        self.report_queue = queue.Queue()
        self.report_thread = None
        # 将来的にはここを修正してASRとTTSのレポートを調整できますが、現在はデフォルトで両方有効です
        self.report_asr_enable = self.read_config_from_api
        self.report_tts_enable = self.read_config_from_api

        # 依存コンポーネント
        self.vad = None
        self.asr = None
        self.tts = None
        self._asr = _asr
        self._vad = _vad
        self.llm = _llm
        self.memory = _memory
        self.intent = _intent

        # VAD関連の変数
        self.client_audio_buffer = bytearray()
        self.client_have_voice = False
        self.last_activity_time = 0.0  # 統一されたアクティビティタイムスタンプ（ミリ秒）
        self.client_voice_stop = False

        # ASR関連の変数
        # 実際のデプロイでは共有のローカルASRが使用される可能性があるため、変数を共有ASRに公開することはできません
        # そのため、ASR関連の変数はここで定義する必要があり、connectionのプライベート変数となります
        self.asr_audio = []
        self.asr_audio_queue = queue.Queue()

        # LLM関連の変数
        self.llm_finish_task = True
        self.dialogue = Dialogue()

        # TTS関連の変数
        self.sentence_id = None

        # IoT関連の変数
        self.iot_descriptors = {}
        self.func_handler = None

        self.cmd_exit = self.config["exit_commands"]
        self.max_cmd_length = 0
        for cmd in self.cmd_exit:
            if len(cmd) > self.max_cmd_length:
                self.max_cmd_length = len(cmd)

        # チャット終了後に接続を閉じるかどうか
        self.close_after_chat = False
        self.load_function_plugin = False
        self.intent_type = "nointent"

        self.timeout_seconds = (
            int(self.config.get("close_connection_no_voice_time", 120)) + 60
        )  # 元々の第一段階のクローズに60秒を追加して、第二段階のクローズを行います
        self.timeout_task = None

        # {"mcp":true} はMCP機能を有効にすることを意味します
        self.features = None

    async def handle_connection(self, ws):
        try:
            # ヘッダーを取得して検証
            self.headers = dict(ws.request.headers)

            if self.headers.get("device-id", None) is None:
                # URLのクエリパラメータからdevice-idの取得を試みる
                from urllib.parse import parse_qs, urlparse

                # WebSocketリクエストからパスを取得
                request_path = ws.request.path
                if not request_path:
                    self.logger.bind(tag=TAG).error("リクエストパスを取得できません")
                    return
                parsed_url = urlparse(request_path)
                query_params = parse_qs(parsed_url.query)
                if "device-id" in query_params:
                    self.headers["device-id"] = query_params["device-id"][0]
                    self.headers["client-id"] = query_params["client-id"][0]
                else:
                    await ws.send("ポートは正常です。接続をテストする必要がある場合は、test_page.htmlを使用してください")
                    await self.close(ws)
                    return
            # クライアントのIPアドレスを取得
            self.client_ip = ws.remote_address[0]
            self.logger.bind(tag=TAG).info(
                f"{self.client_ip} conn - Headers: {self.headers}"
            )

            # 認証を実行
            await self.auth.authenticate(self.headers)

            # 認証成功、処理を続行
            self.websocket = ws
            self.device_id = self.headers.get("device-id", None)

            # アクティビティタイムスタンプを初期化
            self.last_activity_time = time.time() * 1000

            # タイムアウトチェックタスクを開始
            self.timeout_task = asyncio.create_task(self._check_timeout())

            self.welcome_msg = self.config["xiaozhi"]
            self.welcome_msg["session_id"] = self.session_id

            # 差分設定を取得
            self._initialize_private_config()
            # 非同期初期化
            self.executor.submit(self._initialize_components)

            try:
                async for message in self.websocket:
                    await self._route_message(message)
            except websockets.exceptions.ConnectionClosed:
                self.logger.bind(tag=TAG).info("クライアントが切断しました")

        except AuthenticationError as e:
            self.logger.bind(tag=TAG).error(f"認証に失敗しました: {str(e)}")
            return
        except Exception as e:
            stack_trace = traceback.format_exc()
            self.logger.bind(tag=TAG).error(f"接続エラー: {str(e)}-{stack_trace}")
            return
        finally:
            try:
                await self._save_and_close(ws)
            except Exception as final_error:
                self.logger.bind(tag=TAG).error(f"最終クリーンアップ中にエラーが発生しました: {final_error}")
                # メモリの保存に失敗した場合でも、必ず接続を閉じるようにします
                try:
                    await self.close(ws)
                except Exception as close_error:
                    self.logger.bind(tag=TAG).error(
                        f"接続を強制的に閉じる際にエラーが発生しました: {close_error}"
                    )

    async def _save_and_close(self, ws):
        """メモリを保存して接続を閉じます"""
        try:
            if self.memory:
                # スレッドプールを使用して非同期でメモリを保存
                def save_memory_task():
                    try:
                        # 新しいイベントループを作成（メインループとの競合を避けるため）
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(
                            self.memory.save_memory(self.dialogue.dialogue)
                        )
                    except Exception as e:
                        self.logger.bind(tag=TAG).error(f"メモリの保存に失敗しました: {e}")
                    finally:
                        try:
                            loop.close()
                        except Exception:
                            pass

                # スレッドを開始してメモリを保存し、完了を待たない
                threading.Thread(target=save_memory_task, daemon=True).start()
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"メモリの保存に失敗しました: {e}")
        finally:
            # メモリの保存完了を待たずにすぐに接続を閉じる
            try:
                await self.close(ws)
            except Exception as close_error:
                self.logger.bind(tag=TAG).error(
                    f"メモリ保存後に接続を閉じるのに失敗しました: {close_error}"
                )

    async def _route_message(self, message):
        """メッセージルーティング"""
        if isinstance(message, str):
            self.last_activity_time = time.time() * 1000
            await handleTextMessage(self, message)
        elif isinstance(message, bytes):
            if self.vad is None:
                return
            if self.asr is None:
                return
            self.asr_audio_queue.put(message)

    async def handle_restart(self, message):
        """サーバー再起動リクエストを処理します"""
        try:

            self.logger.bind(tag=TAG).info("サーバー再起動コマンドを受信しました。実行準備中...")

            # 確認応答を送信
            await self.websocket.send(
                json.dumps(
                    {
                        "type": "server",
                        "status": "success",
                        "message": "サーバー再起動中...",
                        "content": {"action": "restart"},
                    }
                )
            )

            # 非同期で再起動操作を実行
            def restart_server():
                """実際に再起動を実行するメソッド"""
                time.sleep(1)
                self.logger.bind(tag=TAG).info("サーバーを再起動しています...")
                subprocess.Popen(
                    [sys.executable, "app.py"],
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    start_new_session=True,
                )
                os._exit(0)

            # スレッドを使用してイベントループをブロックせずに再起動を実行
            threading.Thread(target=restart_server, daemon=True).start()

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"再起動に失敗しました: {str(e)}")
            await self.websocket.send(
                json.dumps(
                    {
                        "type": "server",
                        "status": "error",
                        "message": f"再起動に失敗しました: {str(e)}",
                        "content": {"action": "restart"},
                    }
                )
            )

    def _initialize_components(self):
        try:
            self.selected_module_str = build_module_string(
                self.config.get("selected_module", {})
            )
            update_module_string(self.selected_module_str)
            """コンポーネントを初期化します"""
            if self.config.get("prompt") is not None:
                self.prompt = self.config["prompt"]
                self.change_system_prompt(self.prompt)
                self.logger.bind(tag=TAG).info(
                    f"コンポーネントの初期化: prompt成功 {self.prompt[:50]}..."
                )

            """ローカルコンポーネントを初期化します"""
            if self.vad is None:
                self.vad = self._vad
            if self.asr is None:
                self.asr = self._initialize_asr()
            # 音声認識チャネルを開く
            asyncio.run_coroutine_threadsafe(
                self.asr.open_audio_channels(self), self.loop
            )
            if self.tts is None:
                self.tts = self._initialize_tts()
            # 音声合成チャネルを開く
            asyncio.run_coroutine_threadsafe(
                self.tts.open_audio_channels(self), self.loop
            )

            """メモリをロード"""
            self._initialize_memory()
            """意図認識をロード"""
            self._initialize_intent()
            """レポート用スレッドを初期化"""
            self._init_report_threads()
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"コンポーネントのインスタンス化に失敗しました: {e}")

    def _init_report_threads(self):
        """ASRおよびTTSレポート用スレッドを初期化します"""
        if not self.read_config_from_api or self.need_bind:
            return
        if self.chat_history_conf == 0:
            return
        if self.report_thread is None or not self.report_thread.is_alive():
            self.report_thread = threading.Thread(
                target=self._report_worker, daemon=True
            )
            self.report_thread.start()
            self.logger.bind(tag=TAG).info("TTSレポート用スレッドが開始されました")

    def _initialize_tts(self):
        """TTSを初期化します"""
        tts = None
        if not self.need_bind:
            tts = initialize_tts(self.config)

        if tts is None:
            tts = DefaultTTS(self.config, delete_audio_file=True)

        return tts

    def _initialize_asr(self):
        """ASRを初期化します"""
        if self._asr.interface_type == InterfaceType.LOCAL:
            # 共有ASRがローカルサービスの場合は直接返す
            # ローカルの1つのASRインスタンスは複数の接続で共有できるため
            asr = self._asr
        else:
            # 共有ASRがリモートサービスの場合は新しいインスタンスを初期化する
            # リモートASRはwebsocket接続と受信スレッドに関わるため、接続ごとにインスタンスが必要
            asr = initialize_asr(self.config)

        return asr

    def _initialize_private_config(self):
        """設定ファイルから取得する場合は、二次的なインスタンス化を行います"""
        if not self.read_config_from_api:
            return
        """インターフェースから差分設定を取得して二次的なインスタンス化を行い、完全な再インスタンス化は行いません"""
        try:
            begin_time = time.time()
            private_config = get_private_config_from_api(
                self.config,
                self.headers.get("device-id"),
                self.headers.get("client-id", self.headers.get("device-id")),
            )
            private_config["delete_audio"] = bool(self.config.get("delete_audio", True))
            self.logger.bind(tag=TAG).info(
                f"{time.time() - begin_time} 秒、差分設定の取得に成功しました: {json.dumps(filter_sensitive_info(private_config), ensure_ascii=False)}"
            )
        except DeviceNotFoundException as e:
            self.need_bind = True
            private_config = {}
        except DeviceBindException as e:
            self.need_bind = True
            self.bind_code = e.bind_code
            private_config = {}
        except Exception as e:
            self.need_bind = True
            self.logger.bind(tag=TAG).error(f"差分設定の取得に失敗しました: {e}")
            private_config = {}

        init_llm, init_tts, init_memory, init_intent = (
            False,
            False,
            False,
            False,
        )

        init_vad = check_vad_update(self.common_config, private_config)
        init_asr = check_asr_update(self.common_config, private_config)

        if init_vad:
            self.config["VAD"] = private_config["VAD"]
            self.config["selected_module"]["VAD"] = private_config["selected_module"][
                "VAD"
            ]
        if init_asr:
            self.config["ASR"] = private_config["ASR"]
            self.config["selected_module"]["ASR"] = private_config["selected_module"][
                "ASR"
            ]
        if private_config.get("TTS", None) is not None:
            init_tts = True
            self.config["TTS"] = private_config["TTS"]
            self.config["selected_module"]["TTS"] = private_config["selected_module"][
                "TTS"
            ]
        if private_config.get("LLM", None) is not None:
            init_llm = True
            self.config["LLM"] = private_config["LLM"]
            self.config["selected_module"]["LLM"] = private_config["selected_module"][
                "LLM"
            ]
        if private_config.get("Memory", None) is not None:
            init_memory = True
            self.config["Memory"] = private_config["Memory"]
            self.config["selected_module"]["Memory"] = private_config[
                "selected_module"
            ]["Memory"]
        if private_config.get("Intent", None) is not None:
            init_intent = True
            self.config["Intent"] = private_config["Intent"]
            model_intent = private_config.get("selected_module", {}).get("Intent", {})
            self.config["selected_module"]["Intent"] = model_intent
            # プラグイン設定をロード
            if model_intent != "Intent_nointent":
                plugin_from_server = private_config.get("plugins", {})
                for plugin, config_str in plugin_from_server.items():
                    plugin_from_server[plugin] = json.loads(config_str)
                self.config["plugins"] = plugin_from_server
                self.config["Intent"][self.config["selected_module"]["Intent"]][
                    "functions"
                ] = plugin_from_server.keys()
        if private_config.get("prompt", None) is not None:
            self.config["prompt"] = private_config["prompt"]
        if private_config.get("summaryMemory", None) is not None:
            self.config["summaryMemory"] = private_config["summaryMemory"]
        if private_config.get("device_max_output_size", None) is not None:
            self.max_output_size = int(private_config["device_max_output_size"])
        if private_config.get("chat_history_conf", None) is not None:
            self.chat_history_conf = int(private_config["chat_history_conf"])
        if private_config.get("mcp_endpoint", None) is not None:
            self.config["mcp_endpoint"] = private_config["mcp_endpoint"]
        try:
            modules = initialize_modules(
                self.logger,
                private_config,
                init_vad,
                init_asr,
                init_llm,
                init_tts,
                init_memory,
                init_intent,
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"コンポーネントの初期化に失敗しました: {e}")
            modules = {}
        if modules.get("tts", None) is not None:
            self.tts = modules["tts"]
        if modules.get("vad", None) is not None:
            self.vad = modules["vad"]
        if modules.get("asr", None) is not None:
            self.asr = modules["asr"]
        if modules.get("llm", None) is not None:
            self.llm = modules["llm"]
        if modules.get("intent", None) is not None:
            self.intent = modules["intent"]
        if modules.get("memory", None) is not None:
            self.memory = modules["memory"]

    def _initialize_memory(self):
        if self.memory is None:
            return
        """メモリモジュールを初期化します"""
        self.memory.init_memory(
            role_id=self.device_id,
            llm=self.llm,
            summary_memory=self.config.get("summaryMemory", None),
            save_to_file=not self.read_config_from_api,
        )

        # メモリ要約設定を取得
        memory_config = self.config["Memory"]
        memory_type = self.config["Memory"][self.config["selected_module"]["Memory"]][
            "type"
        ]
        # nomemを使用する場合は直接返す
        if memory_type == "nomem":
            return
        # mem_local_shortモードを使用
        elif memory_type == "mem_local_short":
            memory_llm_name = memory_config[self.config["selected_module"]["Memory"]][
                "llm"
            ]
            if memory_llm_name and memory_llm_name in self.config["LLM"]:
                # 専用LLMが設定されている場合は、独立したLLMインスタンスを作成
                from core.utils import llm as llm_utils

                memory_llm_config = self.config["LLM"][memory_llm_name]
                memory_llm_type = memory_llm_config.get("type", memory_llm_name)
                memory_llm = llm_utils.create_instance(
                    memory_llm_type, memory_llm_config
                )
                self.logger.bind(tag=TAG).info(
                    f"メモリ要約用に専用LLMを作成しました: {memory_llm_name}, タイプ: {memory_llm_type}"
                )
                self.memory.set_llm(memory_llm)
            else:
                # それ以外の場合はメインLLMを使用
                self.memory.set_llm(self.llm)
                self.logger.bind(tag=TAG).info("メインLLMを意図認識モデルとして使用します")

    def _initialize_intent(self):
        if self.intent is None:
            return
        self.intent_type = self.config["Intent"][
            self.config["selected_module"]["Intent"]
        ]["type"]
        if self.intent_type == "function_call" or self.intent_type == "intent_llm":
            self.load_function_plugin = True
        """意図認識モジュールを初期化します"""
        # 意図認識設定を取得
        intent_config = self.config["Intent"]
        intent_type = self.config["Intent"][self.config["selected_module"]["Intent"]][
            "type"
        ]

        # nointentを使用する場合は直接返す
        if intent_type == "nointent":
            return
        # intent_llmモードを使用
        elif intent_type == "intent_llm":
            intent_llm_name = intent_config[self.config["selected_module"]["Intent"]][
                "llm"
            ]

            if intent_llm_name and intent_llm_name in self.config["LLM"]:
                # 専用LLMが設定されている場合は、独立したLLMインスタンスを作成
                from core.utils import llm as llm_utils

                intent_llm_config = self.config["LLM"][intent_llm_name]
                intent_llm_type = intent_llm_config.get("type", intent_llm_name)
                intent_llm = llm_utils.create_instance(
                    intent_llm_type, intent_llm_config
                )
                self.logger.bind(tag=TAG).info(
                    f"意図認識用に専用LLMを作成しました: {intent_llm_name}, タイプ: {intent_llm_type}"
                )
                self.intent.set_llm(intent_llm)
            else:
                # それ以外の場合はメインLLMを使用
                self.intent.set_llm(self.llm)
                self.logger.bind(tag=TAG).info("メインLLMを意図認識モデルとして使用します")

        """統一ツールハンドラをロード"""
        self.func_handler = UnifiedToolHandler(self)

        # ツールハンドラを非同期で初期化
        if hasattr(self, "loop") and self.loop:
            asyncio.run_coroutine_threadsafe(self.func_handler._initialize(), self.loop)

    def change_system_prompt(self, prompt):
        self.prompt = prompt
        # システムプロンプトをコンテキストに更新
        self.dialogue.update_system_message(self.prompt)

    def chat(self, query, tool_call=False):
        self.logger.bind(tag=TAG).info(f"大規模モデルがユーザーメッセージを受信しました: {query}")
        self.llm_finish_task = False

        if not tool_call:
            self.dialogue.put(Message(role="user", content=query))

        # 意図関数を定義
        functions = None
        if self.intent_type == "function_call" and hasattr(self, "func_handler"):
            functions = self.func_handler.get_functions()
        response_message = []

        try:
            # メモリ付きの対話を使用
            memory_str = None
            if self.memory is not None:
                future = asyncio.run_coroutine_threadsafe(
                    self.memory.query_memory(query), self.loop
                )
                memory_str = future.result()

            self.sentence_id = str(uuid.uuid4().hex)

            if self.intent_type == "function_call" and functions is not None:
                # functionsをサポートするストリーミングインターフェースを使用
                llm_responses = self.llm.response_with_functions(
                    self.session_id,
                    self.dialogue.get_llm_dialogue_with_memory(memory_str),
                    functions=functions,
                )
            else:
                llm_responses = self.llm.response(
                    self.session_id,
                    self.dialogue.get_llm_dialogue_with_memory(memory_str),
                )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM処理中にエラーが発生しました {query}: {e}")
            return None

        # ストリーミング応答を処理
        tool_call_flag = False
        function_name = None
        function_id = None
        function_arguments = ""
        content_arguments = ""
        text_index = 0
        self.client_abort = False
        for response in llm_responses:
            if self.client_abort:
                break
            if self.intent_type == "function_call" and functions is not None:
                content, tools_call = response
                if "content" in response:
                    content = response["content"]
                    tools_call = None
                if content is not None and len(content) > 0:
                    content_arguments += content

                if not tool_call_flag and content_arguments.startswith("<tool_call>"):
                    # print("content_arguments", content_arguments)
                    tool_call_flag = True

                if tools_call is not None and len(tools_call) > 0:
                    tool_call_flag = True
                    if tools_call[0].id is not None:
                        function_id = tools_call[0].id
                    if tools_call[0].function.name is not None:
                        function_name = tools_call[0].function.name
                    if tools_call[0].function.arguments is not None:
                        function_arguments += tools_call[0].function.arguments
            else:
                content = response
            if content is not None and len(content) > 0:
                if not tool_call_flag:
                    response_message.append(content)
                    if text_index == 0:
                        self.tts.tts_text_queue.put(
                            TTSMessageDTO(
                                sentence_id=self.sentence_id,
                                sentence_type=SentenceType.FIRST,
                                content_type=ContentType.ACTION,
                            )
                        )
                    self.tts.tts_text_queue.put(
                        TTSMessageDTO(
                            sentence_id=self.sentence_id,
                            sentence_type=SentenceType.MIDDLE,
                            content_type=ContentType.TEXT,
                            content_detail=content,
                        )
                    )
                    text_index += 1
        # function callを処理
        if tool_call_flag:
            bHasError = False
            if function_id is None:
                a = extract_json_from_string(content_arguments)
                if a is not None:
                    try:
                        content_arguments_json = json.loads(a)
                        function_name = content_arguments_json["name"]
                        function_arguments = json.dumps(
                            content_arguments_json["arguments"], ensure_ascii=False
                        )
                        function_id = str(uuid.uuid4().hex)
                    except Exception as e:
                        bHasError = True
                        response_message.append(a)
                else:
                    bHasError = True
                    response_message.append(content_arguments)
                if bHasError:
                    self.logger.bind(tag=TAG).error(
                        f"function callエラー: {content_arguments}"
                    )
            if not bHasError:
                response_message.clear()
                self.logger.bind(tag=TAG).debug(
                    f"function_name={function_name}, function_id={function_id}, function_arguments={function_arguments}"
                )
                function_call_data = {
                    "name": function_name,
                    "id": function_id,
                    "arguments": function_arguments,
                }

                # 統一ツールハンドラを使用してすべてのツール呼び出しを処理
                result = asyncio.run_coroutine_threadsafe(
                    self.func_handler.handle_llm_function_call(
                        self, function_call_data
                    ),
                    self.loop,
                ).result()
                self._handle_function_result(result, function_call_data)

        # 対話内容を保存
        if len(response_message) > 0:
            self.dialogue.put(
                Message(role="assistant", content="".join(response_message))
            )
        if text_index > 0:
            self.tts.tts_text_queue.put(
                TTSMessageDTO(
                    sentence_id=self.sentence_id,
                    sentence_type=SentenceType.LAST,
                    content_type=ContentType.ACTION,
                )
            )
        self.llm_finish_task = True
        self.logger.bind(tag=TAG).debug(
            json.dumps(self.dialogue.get_llm_dialogue(), indent=4, ensure_ascii=False)
        )

        return True

    def _handle_function_result(self, result, function_call_data):
        if result.action == Action.RESPONSE:  # フロントエンドに直接応答
            text = result.response
            self.tts.tts_one_sentence(self, ContentType.TEXT, content_detail=text)
            self.dialogue.put(Message(role="assistant", content=text))
        elif result.action == Action.REQLLM:  # 関数を呼び出した後、llmに再度リクエストして応答を生成
            text = result.result
            if text is not None and len(text) > 0:
                function_id = function_call_data["id"]
                function_name = function_call_data["name"]
                function_arguments = function_call_data["arguments"]
                self.dialogue.put(
                    Message(
                        role="assistant",
                        tool_calls=[
                            {
                                "id": function_id,
                                "function": {
                                    "arguments": function_arguments,
                                    "name": function_name,
                                },
                                "type": "function",
                                "index": 0,
                            }
                        ],
                    )
                )

                self.dialogue.put(
                    Message(
                        role="tool",
                        tool_call_id=(
                            str(uuid.uuid4()) if function_id is None else function_id
                        ),
                        content=text,
                    )
                )
                self.chat(text, tool_call=True)
        elif result.action == Action.NOTFOUND or result.action == Action.ERROR:
            text = result.response if result.response else result.result
            self.tts.tts_one_sentence(self, ContentType.TEXT, content_detail=text)
            self.dialogue.put(Message(role="assistant", content=text))
        else:
            pass

    def _report_worker(self):
        """チャット履歴レポートワーカースレッド"""
        while not self.stop_event.is_set():
            try:
                # キューからデータを取得し、定期的に停止イベントをチェックするためにタイムアウトを設定
                item = self.report_queue.get(timeout=1)
                if item is None:  # ポイズンピルを検出
                    break
                type, text, audio_data, report_time = item
                try:
                    # スレッドプールの状態を確認
                    if self.executor is None:
                        continue
                    # タスクをスレッドプールに送信
                    self.executor.submit(
                        self._process_report, type, text, audio_data, report_time
                    )
                except Exception as e:
                    self.logger.bind(tag=TAG).error(f"チャット履歴レポートスレッドで例外が発生しました: {e}")
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.bind(tag=TAG).error(f"チャット履歴レポートワーカースレッドで例外が発生しました: {e}")

        self.logger.bind(tag=TAG).info("チャット履歴レポートスレッドが終了しました")

    def _process_report(self, type, text, audio_data, report_time):
        """レポートタスクを処理します"""
        try:
            # レポートを実行（バイナリデータを渡す）
            report(self, type, text, audio_data, report_time)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"レポート処理で例外が発生しました: {e}")
        finally:
            # タスク完了をマーク
            self.report_queue.task_done()

    def clearSpeakStatus(self):
        self.client_is_speaking = False
        self.logger.bind(tag=TAG).debug("サーバーサイドのスピーキング状態をクリアしました")

    async def close(self, ws=None):
        """リソースクリーンアップメソッド"""
        try:
            # タイムアウトタスクをキャンセル
            if self.timeout_task and not self.timeout_task.done():
                self.timeout_task.cancel()
                try:
                    await self.timeout_task
                except asyncio.CancelledError:
                    pass
                self.timeout_task = None

            # ツールハンドラのリソースをクリーンアップ
            if hasattr(self, "func_handler") and self.func_handler:
                try:
                    await self.func_handler.cleanup()
                except Exception as cleanup_error:
                    self.logger.bind(tag=TAG).error(
                        f"ツールハンドラのクリーンアップ中にエラーが発生しました: {cleanup_error}"
                    )

            # 停止イベントをトリガー
            if self.stop_event:
                self.stop_event.set()

            # タスクキューをクリア
            self.clear_queues()

            # WebSocket接続を閉じる
            try:
                if ws:
                    # WebSocketの状態を安全にチェックして閉じる
                    try:
                        if hasattr(ws, "closed") and not ws.closed:
                            await ws.close()
                        elif hasattr(ws, "state") and ws.state.name != "CLOSED":
                            await ws.close()
                        else:
                            # closed属性がない場合は、直接クローズを試みる
                            await ws.close()
                    except Exception:
                        # クローズに失敗した場合はエラーを無視
                        pass
                elif self.websocket:
                    try:
                        if (
                            hasattr(self.websocket, "closed")
                            and not self.websocket.closed
                        ):
                            await self.websocket.close()
                        elif (
                            hasattr(self.websocket, "state")
                            and self.websocket.state.name != "CLOSED"
                        ):
                            await self.websocket.close()
                        else:
                            # closed属性がない場合は、直接クローズを試みる
                            await self.websocket.close()
                    except Exception:
                        # クローズに失敗した場合はエラーを無視
                        pass
            except Exception as ws_error:
                self.logger.bind(tag=TAG).error(f"WebSocket接続を閉じる際にエラーが発生しました: {ws_error}")

            # 最後にスレッドプールを閉じる（ブロッキングを避けるため）
            if self.executor:
                try:
                    self.executor.shutdown(wait=False)
                except Exception as executor_error:
                    self.logger.bind(tag=TAG).error(
                        f"スレッドプールを閉じる際にエラーが発生しました: {executor_error}"
                    )
                self.executor = None

            self.logger.bind(tag=TAG).info("接続リソースが解放されました")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"接続を閉じる際にエラーが発生しました: {e}")
        finally:
            # 停止イベントが設定されていることを確認
            if self.stop_event:
                self.stop_event.set()

    def clear_queues(self):
        """すべてのタスクキューをクリアします"""
        if self.tts:
            self.logger.bind(tag=TAG).debug(
                f"クリーンアップ開始: TTSキューサイズ={self.tts.tts_text_queue.qsize()}, オーディオキューサイズ={self.tts.tts_audio_queue.qsize()}"
            )

            # 非ブロッキング方式でキューをクリア
            for q in [
                self.tts.tts_text_queue,
                self.tts.tts_audio_queue,
                self.report_queue,
            ]:
                if not q:
                    continue
                while True:
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        break

            self.logger.bind(tag=TAG).debug(
                f"クリーンアップ終了: TTSキューサイズ={self.tts.tts_text_queue.qsize()}, オーディオキューサイズ={self.tts.tts_audio_queue.qsize()}"
            )

    def reset_vad_states(self):
        self.client_audio_buffer = bytearray()
        self.client_have_voice = False
        self.client_voice_stop = False
        self.logger.bind(tag=TAG).debug("VADの状態がリセットされました。")

    def chat_and_close(self, text):
        """ユーザーとチャットしてから接続を閉じます"""
        try:
            # 既存のチャットメソッドを使用
            self.chat(text)

            # チャット完了後、接続を閉じる
            self.close_after_chat = True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"チャットアンドクローズエラー: {str(e)}")

    async def _check_timeout(self):
        """接続タイムアウトを確認します"""
        try:
            while not self.stop_event.is_set():
                # タイムアウトを確認（タイムスタンプが初期化されている場合のみ）
                if self.last_activity_time > 0.0:
                    current_time = time.time() * 1000
                    if (
                        current_time - self.last_activity_time
                        > self.timeout_seconds * 1000
                    ):
                        if not self.stop_event.is_set():
                            self.logger.bind(tag=TAG).info("接続がタイムアウトしました。クローズ準備中")
                            # 重複処理を防ぐために停止イベントを設定
                            self.stop_event.set()
                            # クローズ操作をtry-exceptでラップし、例外によるブロッキングを防ぐ
                            try:
                                await self.close(self.websocket)
                            except Exception as close_error:
                                self.logger.bind(tag=TAG).error(
                                    f"タイムアウトで接続を閉じる際にエラーが発生しました: {close_error}"
                                )
                        break
                # 10秒ごとにチェックして、頻繁すぎるチェックを避ける
                await asyncio.sleep(10)
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"タイムアウトチェックタスクでエラーが発生しました: {e}")
        finally:
            self.logger.bind(tag=TAG).info("タイムアウトチェックタスクが終了しました")
