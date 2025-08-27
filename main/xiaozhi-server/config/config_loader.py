import os
import argparse
import yaml
from collections.abc import Mapping
from config.manage_api_client import init_service, get_server_config, get_agent_models


# グローバル設定キャッシュを追加
_config_cache = None


def get_project_dir():
    """プロジェクトのルートディレクトリを取得します"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/"


def read_config(config_path):
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    return config


def load_config():
    """設定ファイルを読み込みます"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    default_config_path = get_project_dir() + "config.yaml"
    custom_config_path = get_project_dir() + "data/.config.yaml"

    # デフォルト設定を読み込みます
    default_config = read_config(default_config_path)
    custom_config = read_config(custom_config_path)

    if custom_config.get("manager-api", {}).get("url"):
        config = get_config_from_api(custom_config)
    else:
        # 設定をマージします
        config = merge_configs(default_config, custom_config)
    # ディレクトリを初期化します
    ensure_directories(config)
    _config_cache = config
    return config


def get_config_from_api(config):
    """Java APIから設定を取得します"""
    # APIクライアントを初期化します
    init_service(config)

    # サーバー設定を取得します
    config_data = get_server_config()
    if config_data is None:
        raise Exception("APIからのサーバー設定の取得に失敗しました")

    config_data["read_config_from_api"] = True
    config_data["manager-api"] = {
        "url": config["manager-api"].get("url", ""),
        "secret": config["manager-api"].get("secret", ""),
    }
    # サーバーの設定はローカルを優先します
    if config.get("server"):
        config_data["server"] = {
            "ip": config["server"].get("ip", ""),
            "port": config["server"].get("port", ""),
            "http_port": config["server"].get("http_port", ""),
            "vision_explain": config["server"].get("vision_explain", ""),
            "auth_key": config["server"].get("auth_key", ""),
        }
    return config_data


def get_private_config_from_api(config, device_id, client_id):
    """Java APIからプライベート設定を取得します"""
    return get_agent_models(device_id, client_id, config["selected_module"])


def ensure_directories(config):
    """すべての設定パスが存在することを確認します"""
    dirs_to_create = set()
    project_dir = get_project_dir()  # プロジェクトのルートディレクトリを取得します
    # ログファイルディレクトリ
    log_dir = config.get("log", {}).get("log_dir", "tmp")
    dirs_to_create.add(os.path.join(project_dir, log_dir))

    # ASR/TTSモジュールの出力ディレクトリ
    for module in ["ASR", "TTS"]:
        if config.get(module) is None:
            continue
        for provider in config.get(module, {}).values():
            output_dir = provider.get("output_dir", "")
            if output_dir:
                dirs_to_create.add(output_dir)

    # selected_moduleに基づいてモデルディレクトリを作成します
    selected_modules = config.get("selected_module", {})
    for module_type in ["ASR", "LLM", "TTS"]:
        selected_provider = selected_modules.get(module_type)
        if not selected_provider:
            continue
        if config.get(module) is None:
            continue
        if config.get(selected_provider) is None:
            continue
        provider_config = config.get(module_type, {}).get(selected_provider, {})
        output_dir = provider_config.get("output_dir")
        if output_dir:
            full_model_dir = os.path.join(project_dir, output_dir)
            dirs_to_create.add(full_model_dir)

    # ディレクトリを一括で作成します（元のdataディレクトリ作成は維持）
    for dir_path in dirs_to_create:
        try:
            os.makedirs(dir_path, exist_ok=True)
        except PermissionError:
            print(f"警告：ディレクトリ {dir_path} を作成できません。書き込み権限を確認してください")


def merge_configs(default_config, custom_config):
    """
    設定を再帰的にマージします。custom_configが優先されます

    Args:
        default_config: デフォルト設定
        custom_config: ユーザー定義設定

    Returns:
        マージ後の設定
    """
    if not isinstance(default_config, Mapping) or not isinstance(
        custom_config, Mapping
    ):
        return custom_config

    merged = dict(default_config)

    for key, value in custom_config.items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = merge_configs(merged[key], value)
        else:
            merged[key] = value

    return merged