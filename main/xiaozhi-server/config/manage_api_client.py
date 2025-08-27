import os
import time
import base64
from typing import Optional, Dict

import httpx

TAG = __name__


class DeviceNotFoundException(Exception):
    pass


class DeviceBindException(Exception):
    def __init__(self, bind_code):
        self.bind_code = bind_code
        super().__init__(f"デバイスのバインドに失敗しました。バインドコード: {bind_code}")


class ManageApiClient:
    _instance = None
    _client = None
    _secret = None

    def __new__(cls, config):
        """シングルトンパターンでグローバルな単一インスタンスを保証し、設定パラメータの受け渡しをサポートします"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._init_client(config)
        return cls._instance

    @classmethod
    def _init_client(cls, config):
        """永続的な接続プールを初期化します"""
        cls.config = config.get("manager-api")

        if not cls.config:
            raise Exception("manager-apiの設定に誤りがあります")

        if not cls.config.get("url") or not cls.config.get("secret"):
            raise Exception("manager-apiのURLまたはsecretの設定に誤りがあります")

        if "你" in cls.config.get("secret"):
            raise Exception("まずmanager-apiのsecretを設定してください")

        cls._secret = cls.config.get("secret")
        cls.max_retries = cls.config.get("max_retries", 6)  # 最大リトライ回数
        cls.retry_delay = cls.config.get("retry_delay", 10)  # 初期リトライ遅延（秒）
        # NOTE(goody): 2025/4/16 http関連リソースを統一管理し、将来的にはスレッドプールやタイムアウトを追加できます
        # 将来的にはapiTokenなどを統一的に設定し、共通の認証を利用することも可能です
        cls._client = httpx.Client(
            base_url=cls.config.get("url"),
            headers={
                "User-Agent": f"PythonClient/2.0 (PID:{os.getpid()})",
                "Accept": "application/json",
                "Authorization": "Bearer " + cls._secret,
            },
            timeout=cls.config.get("timeout", 30),  # デフォルトのタイムアウト時間は30秒
        )

    @classmethod
    def _request(cls, method: str, endpoint: str, **kwargs) -> Dict:
        """単一のHTTPリクエストを送信し、レスポンスを処理します"""
        endpoint = endpoint.lstrip("/")
        response = cls._client.request(method, endpoint, **kwargs)
        response.raise_for_status()

        result = response.json()

        # APIから返された業務エラーを処理します
        if result.get("code") == 10041:
            raise DeviceNotFoundException(result.get("msg"))
        elif result.get("code") == 10042:
            raise DeviceBindException(result.get("msg"))
        elif result.get("code") != 0:
            raise Exception(f"APIエラー: {result.get('msg', '不明なエラー')}")

        # 成功データを返します
        return result.get("data") if result.get("code") == 0 else None

    @classmethod
    def _should_retry(cls, exception: Exception) -> bool:
        """例外をリトライすべきか判断します"""
        # ネットワーク接続関連のエラー
        if isinstance(
            exception, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)
        ):
            return True

        # HTTPステータスコードエラー
        if isinstance(exception, httpx.HTTPStatusError):
            status_code = exception.response.status_code
            return status_code in [408, 429, 500, 502, 503, 504]

        return False

    @classmethod
    def _execute_request(cls, method: str, endpoint: str, **kwargs) -> Dict:
        """リトライ機構付きのリクエスト実行プログラム"""
        retry_count = 0

        while retry_count <= cls.max_retries:
            try:
                # リクエストを実行
                return cls._request(method, endpoint, **kwargs)
            except Exception as e:
                # リトライすべきか判断
                if retry_count < cls.max_retries and cls._should_retry(e):
                    retry_count += 1
                    print(
                        f"{method} {endpoint} のリクエストに失敗しました。{cls.retry_delay:.1f} 秒後に {retry_count} 回目のリトライを実行します"
                    )
                    time.sleep(cls.retry_delay)
                    continue
                else:
                    # リトライせず、直接例外をスローします
                    raise

    @classmethod
    def safe_close(cls):
        """接続プールを安全にクローズします"""
        if cls._client:
            cls._client.close()
            cls._instance = None


def get_server_config() -> Optional[Dict]:
    """サーバーの基本設定を取得します"""
    return ManageApiClient._instance._execute_request("POST", "/config/server-base")


def get_agent_models(
    mac_address: str, client_id: str, selected_module: Dict
) -> Optional[Dict]:
    """エージェントモデルの設定を取得します"""
    return ManageApiClient._instance._execute_request(
        "POST",
        "/config/agent-models",
        json={
            "macAddress": mac_address,
            "clientId": client_id,
            "selectedModule": selected_module,
        },
    )


def save_mem_local_short(mac_address: str, short_momery: str) -> Optional[Dict]:
    try:
        return ManageApiClient._instance._execute_request(
            "PUT",
            f"/agent/saveMemory/" + mac_address,
            json={
                "summaryMemory": short_momery,
            },
        )
    except Exception as e:
        print(f"短期記憶のサーバーへの保存に失敗しました: {e}")
        return None


def report(
    mac_address: str, session_id: str, chat_type: int, content: str, audio, report_time
) -> Optional[Dict]:
    """サーキットブレーカー付きの業務メソッドの例"""
    if not content or not ManageApiClient._instance:
        return None
    try:
        return ManageApiClient._instance._execute_request(
            "POST",
            f"/agent/chat-history/report",
            json={
                "macAddress": mac_address,
                "sessionId": session_id,
                "chatType": chat_type,
                "content": content,
                "reportTime": report_time,
                "audioBase64": (
                    base64.b64encode(audio).decode("utf-8") if audio else None
                ),
            },
        )
    except Exception as e:
        print(f"TTSのレポートに失敗しました: {e}")
        return None


def init_service(config):
    ManageApiClient(config)


def manage_api_http_safe_close():
    ManageApiClient.safe_close()