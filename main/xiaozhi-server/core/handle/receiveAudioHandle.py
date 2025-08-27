from core.handle.sendAudioHandle import send_stt_message
from core.handle.intentHandler import handle_user_intent
from core.utils.output_counter import check_device_output_limit
from core.handle.abortHandle import handleAbortMessage
import time
import asyncio
from core.handle.sendAudioHandle import SentenceType
from core.utils.util import audio_to_data

TAG = __name__


async def handleAudioMessage(conn, audio):
    # 現在のフラグメントに誰かが話しているか
    have_voice = conn.vad.is_vad(conn, audio)
    # デバイスがちょうど起動された場合、VAD検出を一時的に無視
    if have_voice and hasattr(conn, "just_woken_up") and conn.just_woken_up:
        have_voice = False
        # 短い遅延の後にVAD検出を再開するように設定
        conn.asr_audio.clear()
        if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
            conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
        return

    if have_voice:
        if conn.client_is_speaking:
            await handleAbortMessage(conn)
    # デバイスの長時間アイドル検出、さようならを言うために使用
    await no_voice_close_connect(conn, have_voice)
    # 音声を受信
    await conn.asr.receive_audio(conn, audio, have_voice)


async def resume_vad_detection(conn):
    # 2秒待ってからVAD検出を再開
    await asyncio.sleep(1)
    conn.just_woken_up = False


async def startToChat(conn, text):
    if conn.need_bind:
        await check_bind_device(conn)
        return

    # その日の出力文字数が制限を超えた場合
    if conn.max_output_size > 0:
        if check_device_output_limit(
            conn.headers.get("device-id"), conn.max_output_size
        ):
            await max_out_size(conn)
            return
    if conn.client_is_speaking:
        await handleAbortMessage(conn)

    # まず意図分析を行う
    intent_handled = await handle_user_intent(conn, text)

    if intent_handled:
        # 意図が処理された場合は、チャットを続行しない
        return

    # 意図が処理されていない場合は、通常のチャットフローを続行
    await send_stt_message(conn, text)
    conn.executor.submit(conn.chat, text)


async def no_voice_close_connect(conn, have_voice):
    if have_voice:
        conn.last_activity_time = time.time() * 1000
        return
    # タイムスタンプが初期化されている場合にのみタイムアウトチェックを実行
    if conn.last_activity_time > 0.0:
        no_voice_time = time.time() * 1000 - conn.last_activity_time
        close_connection_no_voice_time = int(
            conn.config.get("close_connection_no_voice_time", 120)
        )
        if (
            not conn.close_after_chat
            and no_voice_time > 1000 * close_connection_no_voice_time
        ):
            conn.close_after_chat = True
            conn.client_abort = False
            end_prompt = conn.config.get("end_prompt", {})
            if end_prompt and end_prompt.get("enable", True) is False:
                conn.logger.bind(tag=TAG).info("会話を終了します。終了プロンプトを送信する必要はありません")
                await conn.close()
                return
            prompt = end_prompt.get("prompt")
            if not prompt:
                prompt = "「時間はあっという間に過ぎていくね」という言葉で、感情的で名残惜しい言葉でこの会話を締めくくってください。"
            await startToChat(conn, prompt)


async def max_out_size(conn):
    text = "すみません、今ちょっと用事があるので、明日のこの時間にまた話しましょう。約束ですよ！また明日、さようなら！"
    await send_stt_message(conn, text)
    file_path = "config/assets/max_output_size.wav"
    opus_packets, _ = audio_to_data(file_path)
    conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))
    conn.close_after_chat = True


async def check_bind_device(conn):
    if conn.bind_code:
        # bind_codeが6桁の数字であることを確認
        if len(conn.bind_code) != 6:
            conn.logger.bind(tag=TAG).error(f"無効なバインドコード形式: {conn.bind_code}")
            text = "バインドコードの形式が正しくありません。設定を確認してください。"
            await send_stt_message(conn, text)
            return

        text = f"コントロールパネルにログインし、{conn.bind_code}を入力してデバイスをバインドしてください。"
        await send_stt_message(conn, text)

        # プロンプト音を再生
        music_path = "config/assets/bind_code.wav"
        opus_packets, _ = audio_to_data(music_path)
        conn.tts.tts_audio_queue.put((SentenceType.FIRST, opus_packets, text))

        # 数字を1つずつ再生
        for i in range(6):  # 6桁の数字のみを再生することを確認
            try:
                digit = conn.bind_code[i]
                num_path = f"config/assets/bind_code/{digit}.wav"
                num_packets, _ = audio_to_data(num_path)
                conn.tts.tts_audio_queue.put((SentenceType.MIDDLE, num_packets, None))
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"数字の音声の再生に失敗しました: {e}")
                continue
        conn.tts.tts_audio_queue.put((SentenceType.LAST, [], None))
    else:
        text = "このデバイスのバージョン情報が見つかりませんでした。OTAアドレスを正しく設定してから、ファームウェアを再コンパイルしてください。"
        await send_stt_message(conn, text)
        music_path = "config/assets/bind_not_found.wav"
        opus_packets, _ = audio_to_data(music_path)
        conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))