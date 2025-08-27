import sys
import uuid
import signal
import asyncio
from aioconsole import ainput
from config.settings import load_config
from config.logger import setup_logging
from core.utils.util import get_local_ip, validate_mcp_endpoint
from core.http_server import SimpleHttpServer
from core.websocket_server import WebSocketServer
from core.utils.util import check_ffmpeg_installed

TAG = __name__
logger = setup_logging()


async def wait_for_exit() -> None:
    """
    Ctrl-C / SIGTERM を受信するまでブロックします。
    - Unix: add_signal_handler を使用
    - Windows: KeyboardInterrupt に依存
    """
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    if sys.platform != "win32":  # Unix / macOS
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
    else:
        # Windows: 常にペンディング状態の future を await し、
        # KeyboardInterrupt を asyncio.run にバブルアップさせることで、
        # 古い通常のスレッドが原因でプロセスの終了がブロックされる問題を解消します。
        try:
            await asyncio.Future()
        except KeyboardInterrupt:  # Ctrl‑C
            pass


async def monitor_stdin():
    """標準入力を監視し、Enterキーを消費します"""
    while True:
        await ainput()  # 非同期で入力を待ち、Enterキーを消費


async def main():
    check_ffmpeg_installed()
    config = load_config()

    # デフォルトで manager-api の secret を auth_key として使用します
    # secret が空の場合、ランダムなキーを生成します
    # auth_key は JWT 認証に使用されます（例：ビジョン分析インターフェースの JWT 認証）
    auth_key = config.get("manager-api", {}).get("secret", "")
    if not auth_key or len(auth_key) == 0 or "你" in auth_key:
        auth_key = str(uuid.uuid4().hex)
    config["server"]["auth_key"] = auth_key

    # stdin 監視タスクを追加
    stdin_task = asyncio.create_task(monitor_stdin())

    # WebSocket サーバーを起動
    ws_server = WebSocketServer(config)
    ws_task = asyncio.create_task(ws_server.start())
    # Simple http サーバーを起動
    ota_server = SimpleHttpServer(config)
    ota_task = asyncio.create_task(ota_server.start())

    read_config_from_api = config.get("read_config_from_api", False)
    port = int(config["server"].get("http_port", 8003))
    if not read_config_from_api:
        logger.bind(tag=TAG).info(
            "OTAインターフェースは\t\thttp://{{}}:{{}}/xiaozhi/ota/",
            get_local_ip(),
            port,
        )
    logger.bind(tag=TAG).info(
        "ビジョン分析インターフェースは\thttp://{{}}:{{}}/mcp/vision/explain",
        get_local_ip(),
        port,
    )
    mcp_endpoint = config.get("mcp_endpoint", None)
    if mcp_endpoint is not None and "你" not in mcp_endpoint:
        # MCP アクセスポイントのフォーマットを検証
        if validate_mcp_endpoint(mcp_endpoint):
            logger.bind(tag=TAG).info("mcpアクセスポイントは\t{}", mcp_endpoint)
            # mcp アクセスポイントアドレスを呼び出しポイントに変換
            mcp_endpoint = mcp_endpoint.replace("/mcp/", "/call/")
            config["mcp_endpoint"] = mcp_endpoint
        else:
            logger.bind(tag=TAG).error("mcpアクセスポイントが仕様に準拠していません")
            config["mcp_endpoint"] = "あなたのアクセスポイントのwebsocketアドレス"

    # WebSocket 設定を取得し、安全なデフォルト値を使用
    websocket_port = 8000
    server_config = config.get("server", {})
    if isinstance(server_config, dict):
        websocket_port = int(server_config.get("port", 8000))

    logger.bind(tag=TAG).info(
        "Websocketアドレスは\tws://{{}}:{{}}/xiaozhi/v1/",
        get_local_ip(),
        websocket_port,
    )

    logger.bind(tag=TAG).info(
        "=======上記のアドレスはwebsocketプロトコルアドレスです。ブラウザでアクセスしないでください======="
    )
    logger.bind(tag=TAG).info(
        "websocketをテストしたい場合は、Google Chromeでtestディレクトリのtest_page.htmlを開いてください"
    )
    logger.bind(tag=TAG).info(
        "=============================================================\n"
    )

    try:
        await wait_for_exit()  # 終了シグナルを受信するまでブロック
    except asyncio.CancelledError:
        print("タスクがキャンセルされました。リソースをクリーンアップしています...")
    finally:
        # すべてのタスクをキャンセル（重要な修正点）
        stdin_task.cancel()
        ws_task.cancel()
        if ota_task:
            ota_task.cancel()

        # タスクの終了を待つ（タイムアウトを必ず設定）
        await asyncio.wait(
            [stdin_task, ws_task, ota_task] if ota_task else [stdin_task, ws_task],
            timeout=3.0,
            return_when=asyncio.ALL_COMPLETED,
        )
        print("サーバーがシャットダウンしました。プログラムを終了します。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("手動で中断されました。プログラムを終了します。")