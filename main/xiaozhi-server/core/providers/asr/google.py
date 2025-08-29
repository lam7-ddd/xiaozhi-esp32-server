import os
import io
import wave
from google.cloud import speech
from core.providers.asr.base import ASRProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__()
        self.api_key = config.get("api_key")
        self.language_code = config.get("language_code", "en-US")
        self.output_dir = config.get("output_dir", "tmp/")
        self.delete_audio_file = delete_audio_file
        # Google Cloud Speech-to-Textクライアントの初期化
        self.client = speech.SpeechClient()

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

            # 音声データをGoogle Cloud Speech-to-Text APIに送信
            with io.open(file_path, "rb") as audio_file:
                content = audio_file.read()

            audio = speech.RecognitionAudio(content=content)
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=16000,
                language_code=self.language_code,
                enable_automatic_punctuation=True,
            )

            response = self.client.recognize(config=config, audio=audio)

            # 結果を取得
            transcript = ""
            if response.results:
                transcript = response.results[0].alternatives[0].transcript

            # ファイルを削除
            if self.delete_audio_file and os.path.exists(file_path):
                os.remove(file_path)

            return transcript, file_path

        except Exception as e:
            logger.bind(tag=TAG).error(f"Google ASR request failed: {str(e)}")
            return "", None