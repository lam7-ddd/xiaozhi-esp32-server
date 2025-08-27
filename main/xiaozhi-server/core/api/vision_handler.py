import json
import copy
from aiohttp import web
from config.logger import setup_logging
from core.utils.util import get_vision_url, is_valid_image_file
from core.utils.vllm import create_instance
from config.config_loader import get_private_config_from_api
from core.utils.auth import AuthToken
import base64
from typing import Tuple, Optional
from plugins_func.register import Action

TAG = __name__

# 最大ファイルサイズを5MBに設定
MAX_FILE_SIZE = 5 * 1024 * 1024


class VisionHandler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        # 認証ツールを初期化
        self.auth = AuthToken(config["server"]["auth_key"])

    def _create_error_response(self, message: str) -> dict:
        """統一されたエラーレスポンス形式を作成します"""
        return {"success": False, "message": message}

    def _verify_auth_token(self, request) -> Tuple[bool, Optional[str]]:
        """認証トークンを検証します"""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False, None

        token = auth_header[7:]  # "Bearer "プレフィックスを削除
        return self.auth.verify_token(token)

    async def handle_post(self, request):
        """MCP Vision POSTリクエストを処理します"""
        response = None  # response変数を初期化
        try:
            # トークンを検証
            is_valid, token_device_id = self._verify_auth_token(request)
            if not is_valid:
                response = web.Response(
                    text=json.dumps(
                        self._create_error_response("無効な認証トークンまたはトークンが期限切れです")
                    ),
                    content_type="application/json",
                    status=401,
                )
                return response

            # リクエストヘッダー情報を取得
            device_id = request.headers.get("Device-Id", "")
            client_id = request.headers.get("Client-Id", "")
            if device_id != token_device_id:
                raise ValueError("デバイスIDがトークンと一致しません")
            # multipart/form-dataリクエストを解析
            reader = await request.multipart()

            # questionフィールドを読み取り
            question_field = await reader.next()
            if question_field is None:
                raise ValueError("質問フィールドがありません")
            question = await question_field.text()
            self.logger.bind(tag=TAG).debug(f"質問: {question}")

            # 画像ファイルを読み取り
            image_field = await reader.next()
            if image_field is None:
                raise ValueError("画像ファイルがありません")

            # 画像データを読み取り
            image_data = await image_field.read()
            if not image_data:
                raise ValueError("画像データが空です")

            # ファイルサイズを確認
            if len(image_data) > MAX_FILE_SIZE:
                raise ValueError(
                    f"画像サイズが制限を超えています。最大許容サイズは{MAX_FILE_SIZE/1024/1024}MBです"
                )

            # ファイル形式を確認
            if not is_valid_image_file(image_data):
                raise ValueError(
                    "サポートされていないファイル形式です。有効な画像ファイル（JPEG、PNG、GIF、BMP、TIFF、WEBP形式をサポート）をアップロードしてください"
                )

            # 画像をbase64エンコーディングに変換
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # スマートコントロールパネルが有効な場合は、そこからモデル設定を取得
            current_config = copy.deepcopy(self.config)
            read_config_from_api = current_config.get("read_config_from_api", False)
            if read_config_from_api:
                current_config = get_private_config_from_api(
                    current_config,
                    device_id,
                    client_id,
                )

            select_vllm_module = current_config["selected_module"].get("VLLM")
            if not select_vllm_module:
                raise ValueError("デフォルトの視覚分析モジュールがまだ設定されていません")

            vllm_type = (
                select_vllm_module
                if "type" not in current_config["VLLM"][select_vllm_module]
                else current_config["VLLM"][select_vllm_module]["type"]
            )

            if not vllm_type:
                raise ValueError(f"VLLMモジュールに対応するプロバイダーが見つかりません{vllm_type}")

            vllm = create_instance(
                vllm_type, current_config["VLLM"][select_vllm_module]
            )

            result = vllm.response(question, image_base64)

            return_json = {
                "success": True,
                "action": Action.RESPONSE.name,
                "response": result,
            }

            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        except ValueError as e:
            self.logger.bind(tag=TAG).error(f"MCP Vision POSTリクエスト例外: {e}")
            return_json = self._create_error_response(str(e))
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"MCP Vision POSTリクエスト例外: {e}")
            return_json = self._create_error_response("リクエストの処理中にエラーが発生しました")
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        finally:
            if response:
                self._add_cors_headers(response)
            return response

    async def handle_get(self, request):
        """MCP Vision GETリクエストを処理します"""
        try:
            vision_explain = get_vision_url(self.config)
            if vision_explain and len(vision_explain) > 0 and "null" != vision_explain:
                message = (
                    f"MCP Visionインターフェースは正常に動作しています。視覚解説インターフェースのアドレスは次のとおりです：{vision_explain}"
                )
            else:
                message = "MCP Visionインターフェースは正常に動作していません。dataディレクトリの.config.yamlファイルを開き、【server.vision_explain】にアドレスを設定してください"

            response = web.Response(text=message, content_type="text/plain")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"MCP Vision GETリクエスト例外: {e}")
            return_json = self._create_error_response("サーバー内部エラー")
            response = web.Response(
                text=json.dumps(return_json, separators=(",", ":")),
                content_type="application/json",
            )
        finally:
            self._add_cors_headers(response)
            return response

    def _add_cors_headers(self, response):
        """CORSヘッダーを追加します"""
        response.headers["Access-Control-Allow-Headers"] = (
            "client-id, content-type, device-id"
        )
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Origin"] = "*"