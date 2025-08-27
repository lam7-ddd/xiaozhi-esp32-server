from abc import ABC, abstractmethod
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

class LLMProviderBase(ABC):
    @abstractmethod
    def response(self, session_id, dialogue):
        """LLM応答ジェネレーター"""
        pass

    def response_no_stream(self, system_prompt, user_prompt, **kwargs):
        try:
            # 対話形式を構築
            dialogue = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            result = ""
            for part in self.response("", dialogue, **kwargs):
                result += part
            return result

        except Exception as e:
            logger.bind(tag=TAG).error(f"Ollama応答生成エラー: {e}")
            return "【LLMサービス応答例外】"
    
    def response_with_functions(self, session_id, dialogue, functions=None):
        """
        関数呼び出しのデフォルト実装（ストリーミング）
        これは、関数呼び出しをサポートするプロバイダーによってオーバーライドされる必要があります

        戻り値：テキストトークンまたは特別な関数呼び出しトークンを生成するジェネレーター
        """
        # 関数をサポートしないプロバイダーの場合は、通常の応答を返すだけです
        for token in self.response(session_id, dialogue):
            yield token, None