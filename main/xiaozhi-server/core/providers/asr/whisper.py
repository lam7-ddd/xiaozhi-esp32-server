import os
import whisper
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.model_name = config.get("model_name", "turbo")
        self.language = config.get("language", None)
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        # Whisperモデルのロード
        self.model = whisper.load_model(self.model_name)

    async def speech_to_text(self, opus_data, session_id, audio_format="opus"):
        try:
            # Opusデータをデコード
            if audio_format == "opus":
                pcm_data = self.decode_opus(opus_data)
            else:
                pcm_data = opus_data

            # PCMデータを結合
            combined_pcm_data = b"".join(pcm_data)

            # WAVファイルとして保存
            file_path = self.save_audio_to_file(pcm_data, session_id)

            # Whisperを使用して音声をテキストに変換
            result = self.model.transcribe(file_path, language=self.language)

            # ファイルを削除
            if self.delete_audio_file and os.path.exists(file_path):
                os.remove(file_path)

            return result["text"], file_path

        except Exception as e:
            logger.bind(tag=TAG).error(f"Whisper ASR request failed: {str(e)}")
            return "", None