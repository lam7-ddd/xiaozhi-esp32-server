import io
from elevenlabs import ElevenLabs, play
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.voice_id = config.get("voice_id", "JBFqnCBsd6RMkjVDRZzb")  # Default voice
        self.model_id = config.get("model_id", "eleven_multilingual_v2")
        self.output_format = config.get("output_format", "mp3_44100_128")
        self.output_file = config.get("output_dir", "tmp/")
        model_key_msg = check_model_key("TTS", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)
        self.client = ElevenLabs(api_key=self.api_key)

    async def text_to_speak(self, text, output_file):
        try:
            # ElevenLabs APIを使用して音声合成を実行
            audio = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model_id,
                output_format=self.output_format,
            )
            
            if output_file:
                # 音声データをファイルに保存
                with open(output_file, "wb") as out:
                    for chunk in audio:
                        if isinstance(chunk, bytes):
                            out.write(chunk)
            else:
                # 音声データをバイト列として返す
                audio_bytes = b""
                for chunk in audio:
                    if isinstance(chunk, bytes):
                        audio_bytes += chunk
                return audio_bytes
                
        except Exception as e:
            raise Exception(f"ElevenLabs TTS request failed: {str(e)}")