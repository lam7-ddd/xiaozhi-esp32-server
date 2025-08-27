import os
from config.config_loader import read_config, get_project_dir, load_config


default_config_file = "config.yaml"
config_file_valid = False


def check_config_file():
    global config_file_valid
    if config_file_valid:
        return
    """
    簡素化された設定チェック。ユーザーに設定ファイルの使用状況を通知するだけです。
    """
    custom_config_file = get_project_dir() + "data/." + default_config_file
    if not os.path.exists(custom_config_file):
        raise FileNotFoundError(
            "data/.config.yamlファイルが見つかりません。チュートリアルに従って設定ファイルが存在することを確認してください"
        )

    # APIから設定を読み込むかどうかを確認
    config = load_config()
    if config.get("read_config_from_api", False):
        print("APIから設定を読み込みます")
        old_config_origin = read_config(custom_config_file)
        if old_config_origin.get("selected_module") is not None:
            error_msg = "設定ファイルに、スマートコントロールパネルの設定とローカル設定の両方が含まれているようです：\n"
            error_msg += "\n次のことをお勧めします：\n"
            error_msg += "1. ルートディレクトリのconfig_from_api.yamlファイルをdataにコピーし、.config.yamlにリネームしてください\n"
            error_msg += "2. チュートリアルに従ってインターフェースアドレスとキーを設定してください\n"
            raise ValueError(error_msg)
    config_file_valid = True