import os
import io
from google.cloud import texttospeech
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.language_code = config.get("language_code", "en-US")
        self.voice_name = config.get("voice_name", "en-US-Wavenet-A")
        self.audio_encoding = config.get("audio_encoding", "LINEAR16")
        self.output_file = config.get("output_dir", "tmp/")
        model_key_msg = check_model_key("TTS", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    async def text_to_speak(self, text, output_file):
        try:
            # Google Cloud Text-to-Speechクライアントの初期化
            client = texttospeech.TextToSpeechClient()
            
            # 音声合成の設定
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=self.language_code,
                name=self.voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=getattr(texttospeech.AudioEncoding, self.audio_encoding)
            )
            
            # 音声合成の実行
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            
            if output_file:
                # 音声データをファイルに保存
                with open(output_file, "wb") as out:
                    out.write(response.audio_content)
            else:
                # 音声データをバイト列として返す
                return response.audio_content
                
        except Exception as e:
            raise Exception(f"Google TTS request failed: {str(e)}")