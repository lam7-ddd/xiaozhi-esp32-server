import os
import sys
from loguru import logger
from config.config_loader import load_config
from config.settings import check_config_file
from datetime import datetime

SERVER_VERSION = "0.6.3"
_logger_initialized = False


def get_module_abbreviation(module_name, module_dict):
    """モジュール名の略称を取得します。空の場合は「00」を返します。
    名前にアンダースコアが含まれている場合は、アンダースコアの後の最初の2文字を返します。
    """
    module_value = module_dict.get(module_name, "")
    if not module_value:
        return "00"
    if "_" in module_value:
        parts = module_value.split("_")
        return parts[-1][:2] if parts[-1] else "00"
    return module_value[:2]


def build_module_string(selected_module):
    """モジュール文字列を構築します"""
    return (
        get_module_abbreviation("VAD", selected_module)
        + get_module_abbreviation("ASR", selected_module)
        + get_module_abbreviation("LLM", selected_module)
        + get_module_abbreviation("TTS", selected_module)
        + get_module_abbreviation("Memory", selected_module)
        + get_module_abbreviation("Intent", selected_module)
    )


def formatter(record):
    """タグのないログにデフォルト値を追加します"""
    record["extra"].setdefault("tag", record["name"])
    return record["message"]


def setup_logging():
    check_config_file()
    """設定ファイルからログ設定を読み取り、ログ出力形式とレベルを設定します"""
    config = load_config()
    log_config = config["log"]
    global _logger_initialized

    # 最初の初期化時にログを設定します
    if not _logger_initialized:
        logger.configure(
            extra={
                "selected_module": log_config.get("selected_module", "00000000000000")
            }
        )  # 新しい設定
        log_format = log_config.get(
            "log_format",
            "<green>{time:YYMMDD HH:mm:ss}</green>[{version}_{extra[selected_module]}][<light-blue>{extra[tag]}</light-blue>]-<level>{level}</level>-<light-green>{message}</light-green>",
        )
        log_format_file = log_config.get(
            "log_format_file",
            "{time:YYYY-MM-DD HH:mm:ss} - {version}_{extra[selected_module]} - {name} - {level} - {extra[tag]} - {message}",
        )
        selected_module_str = logger._core.extra["selected_module"]

        log_format = log_format.replace("{version}", SERVER_VERSION)
        log_format = log_format.replace("{selected_module}", selected_module_str)
        log_format_file = log_format_file.replace("{version}", SERVER_VERSION)
        log_format_file = log_format_file.replace(
            "{selected_module}", selected_module_str
        )

        log_level = log_config.get("log_level", "INFO")
        log_dir = log_config.get("log_dir", "tmp")
        log_file = log_config.get("log_file", "server.log")
        data_dir = log_config.get("data_dir", "data")

        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)

        # ログ出力を設定します
        logger.remove()

        # コンソールに出力
        logger.add(sys.stdout, format=log_format, level=log_level, filter=formatter)

        # ファイルに出力 - 統一されたディレクトリ、サイズでローテーション
        # ログファイルのフルパス
        log_file_path = os.path.join(log_dir, log_file)

        # ログハンドラを追加
        logger.add(
            log_file_path,
            format=log_format_file,
            level=log_level,
            filter=formatter,
            rotation="10 MB",  # 各ファイルの最大サイズは10MB
            retention="30 days",  # 30日間保持
            compression=None,
            encoding="utf-8",
            enqueue=True,  # 非同期セーフ
            backtrace=True,
            diagnose=True,
        )
        _logger_initialized = True  # 初期化済みとしてマーク

    return logger


def update_module_string(selected_module_str):
    """モジュール文字列を更新し、ログハンドラを再設定します"""
    logger.debug("ログ設定コンポーネントを更新します")
    current_module = logger._core.extra["selected_module"]

    if current_module == selected_module_str:
        logger.debug("コンポーネントは変更されていないため、更新は不要です")
        return

    try:
        logger.configure(extra={"selected_module": selected_module_str})

        config = load_config()
        log_config = config["log"]

        log_format = log_config.get(
            "log_format",
            "<green>{time:YYMMDD HH:mm:ss}</green>[{version}_{extra[selected_module]}][<light-blue>{extra[tag]}</light-blue>]-<level>{level}</level>-<light-green>{message}</light-green>",
        )
        log_format_file = log_config.get(
            "log_format_file",
            "{time:YYYY-MM-DD HH:mm:ss} - {version}_{extra[selected_module]} - {name} - {level} - {extra[tag]} - {message}",
        )

        log_format = log_format.replace("{version}", SERVER_VERSION)
        log_format = log_format.replace("{selected_module}", selected_module_str)
        log_format_file = log_format_file.replace("{version}", SERVER_VERSION)
        log_format_file = log_format_file.replace(
            "{selected_module}", selected_module_str
        )

        logger.remove()
        logger.add(
            sys.stdout,
            format=log_format,
            level=log_config.get("log_level", "INFO"),
            filter=formatter,
        )

        # ファイルログ設定を更新 - 統一されたディレクトリ、サイズでローテーション
        log_dir = log_config.get("log_dir", "tmp")
        log_file = log_config.get("log_file", "server.log")

        # ログファイルのフルパス
        log_file_path = os.path.join(log_dir, log_file)

        logger.add(
            log_file_path,
            format=log_format_file,
            level=log_config.get("log_level", "INFO"),
            filter=formatter,
            rotation="10 MB",  # 各ファイルの最大サイズは10MB
            retention="30 days",  # 30日間保持
            compression=None,
            encoding="utf-8",
            enqueue=True,  # 非同期セーフ
            backtrace=True,
            diagnose=True,
        )

    except Exception as e:
        logger.error(f"ログ設定の更新に失敗しました: {str(e)}")
        raise