from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class AuthenticationError(Exception):
    """認証例外"""
    pass


class AuthMiddleware:
    def __init__(self, config):
        self.config = config
        self.auth_config = config["server"].get("auth", {})
        # トークン検索テーブルを構築
        self.tokens = {
            item["token"]: item["name"]
            for item in self.auth_config.get("tokens", [])
        }
        # デバイスのホワイトリスト
        self.allowed_devices = set(
            self.auth_config.get("allowed_devices", [])
        )

    async def authenticate(self, headers):
        """接続リクエストを検証します"""
        # 認証が有効かどうかを確認
        if not self.auth_config.get("enabled", False):
            return True

        # デバイスがホワイトリストに含まれているか確認
        device_id = headers.get("device-id", "")

        if self.allowed_devices and device_id in self.allowed_devices:
            return True

        # Authorizationヘッダーを検証
        auth_header = headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.bind(tag=TAG).error("Authorizationヘッダーが見つからないか、無効です")
            raise AuthenticationError("Authorizationヘッダーが見つからないか、無効です")

        token = auth_header.split(" ")[1]
        if token not in self.tokens:
            logger.bind(tag=TAG).error(f"無効なトークン: {token}")
            raise AuthenticationError("無効なトークン")

        logger.bind(tag=TAG).info(f"認証成功 - デバイス: {device_id}, トークン: {self.tokens[token]}")
        return True

    def get_token_name(self, token):
        """トークンに対応するデバイス名を取得します"""
        return self.tokens.get(token)