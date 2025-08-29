import requests
import json
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_url = config.get("api_url", "http://localhost:50021")
        self.speaker_id = config.get("speaker_id", 3)  # ずんだもんノーマル
        self.output_file = config.get("output_dir", "tmp/")
        # VoicevoxはAPIキー不要のため、check_model_keyは呼び出さない

    async def text_to_speak(self, text, output_file):
        try:
            # 音声合成用のクエリを作成
            query_url = f"{self.api_url}/audio_query"
            query_params = {
                "text": text,
                "speaker": self.speaker_id
            }
            query_response = requests.post(query_url, params=query_params)
            query_response.raise_for_status()
            
            # 音声合成を実行
            synthesis_url = f"{self.api_url}/synthesis"
            synthesis_params = {
                "speaker": self.speaker_id
            }
            synthesis_response = requests.post(
                synthesis_url,
                params=synthesis_params,
                json=query_response.json()
            )
            synthesis_response.raise_for_status()
            
            if output_file:
                # 音声データをファイルに保存
                with open(output_file, "wb") as out:
                    out.write(synthesis_response.content)
            else:
                # 音声データをバイト列として返す
                return synthesis_response.content
                
        except Exception as e:
            raise Exception(f"Voicevox TTS request failed: {str(e)}")