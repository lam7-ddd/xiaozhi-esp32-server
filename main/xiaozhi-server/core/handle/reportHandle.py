"""
TTSレポート機能はConnectionHandlerクラスに統合されました。

レポート機能には以下が含まれます：
1. 各接続オブジェクトは、独自のレポートキューと処理スレッドを所有します
2. レポートスレッドのライフサイクルは、接続オブジェクトにバインドされます
3. ConnectionHandler.enqueue_tts_reportメソッドを使用してレポートします

具体的な実装については、core/connection.pyの関連コードを参照してください。
"""

import time

import opuslib_next

from config.manage_api_client import report as manage_report

TAG = __name__


def report(conn, type, text, opus_data, report_time):
    """チャット履歴のレポート操作を実行します

    Args:
        conn: 接続オブジェクト
        type: レポートタイプ、1はユーザー、2はエージェント
        text: 合成テキスト
        opus_data: opusオーディオデータ
        report_time: レポート時間
    """
    try:
        if opus_data:
            audio_data = opus_to_wav(conn, opus_data)
        else:
            audio_data = None
        # レポートを実行
        manage_report(
            mac_address=conn.device_id,
            session_id=conn.session_id,
            chat_type=type,
            content=text,
            audio=audio_data,
            report_time=report_time,
        )
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"チャット履歴のレポートに失敗しました: {e}")


def opus_to_wav(conn, opus_data):
    """OpusデータをWAV形式のバイトストリームに変換します

    Args:
        output_dir: 出力ディレクトリ（インターフェースの互換性を維持するための予約パラメータ）
        opus_data: opusオーディオデータ

    Returns:
        bytes: WAV形式のオーディオデータ
    """
    decoder = opuslib_next.Decoder(16000, 1)  # 16kHz、モノラル
    pcm_data = []

    for opus_packet in opus_data:
        try:
            pcm_frame = decoder.decode(opus_packet, 960)  # 960サンプル = 60ms
            pcm_data.append(pcm_frame)
        except opuslib_next.OpusError as e:
            conn.logger.bind(tag=TAG).error(f"Opusデコードエラー: {e}", exc_info=True)

    if not pcm_data:
        raise ValueError("有効なPCMデータがありません")

    # WAVファイルヘッダーを作成
    pcm_data_bytes = b"".join(pcm_data)
    num_samples = len(pcm_data_bytes) // 2  # 16ビットサンプル

    # WAVファイルヘッダー
    wav_header = bytearray()
    wav_header.extend(b"RIFF")  # ChunkID
    wav_header.extend((36 + len(pcm_data_bytes)).to_bytes(4, "little"))  # ChunkSize
    wav_header.extend(b"WAVE")  # Format
    wav_header.extend(b"fmt ")  # Subchunk1ID
    wav_header.extend((16).to_bytes(4, "little"))  # Subchunk1Size
    wav_header.extend((1).to_bytes(2, "little"))  # AudioFormat (PCM)
    wav_header.extend((1).to_bytes(2, "little"))  # NumChannels
    wav_header.extend((16000).to_bytes(4, "little"))  # SampleRate
    wav_header.extend((32000).to_bytes(4, "little"))  # ByteRate
    wav_header.extend((2).to_bytes(2, "little"))  # BlockAlign
    wav_header.extend((16).to_bytes(2, "little"))  # BitsPerSample
    wav_header.extend(b"data")  # Subchunk2ID
    wav_header.extend(len(pcm_data_bytes).to_bytes(4, "little"))  # Subchunk2Size

    # 完全なWAVデータを返す
    return bytes(wav_header) + pcm_data_bytes


def enqueue_tts_report(conn, text, opus_data):
    if not conn.read_config_from_api or conn.need_bind or not conn.report_tts_enable:
        return
    if conn.chat_history_conf == 0:
        return
    """TTSデータをレポートキューに追加します

    Args:
        conn: 接続オブジェクト
        text: 合成テキスト
        opus_data: opusオーディオデータ
    """
    try:
        # 接続オブジェクトのキューを使用し、ファイルパスではなくテキストとバイナリデータを渡す
        if conn.chat_history_conf == 2:
            conn.report_queue.put((2, text, opus_data, int(time.time())))
            conn.logger.bind(tag=TAG).debug(
                f"TTSデータがレポートキューに追加されました: {conn.device_id}, オーディオサイズ: {len(opus_data)} "
            )
        else:
            conn.report_queue.put((2, text, None, int(time.time())))
            conn.logger.bind(tag=TAG).debug(
                f"TTSデータがレポートキューに追加されました: {conn.device_id}, オーディオはレポートしません"
            )
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"TTSレポートキューへの追加に失敗しました: {text}, {e}")


def enqueue_asr_report(conn, text, opus_data):
    if not conn.read_config_from_api or conn.need_bind or not conn.report_asr_enable:
        return
    if conn.chat_history_conf == 0:
        return
    """ASRデータをレポートキューに追加します

    Args:
        conn: 接続オブジェクト
        text: 合成テキスト
        opus_data: opusオーディオデータ
    """
    try:
        # 接続オブジェクトのキューを使用し、ファイルパスではなくテキストとバイナリデータを渡す
        if conn.chat_history_conf == 2:
            conn.report_queue.put((1, text, opus_data, int(time.time())))
            conn.logger.bind(tag=TAG).debug(
                f"ASRデータがレポートキューに追加されました: {conn.device_id}, オーディオサイズ: {len(opus_data)} "
            )
        else:
            conn.report_queue.put((1, text, None, int(time.time())))
            conn.logger.bind(tag=TAG).debug(
                f"ASRデータがレポートキューに追加されました: {conn.device_id}, オーディオはレポートしません"
            )
    except Exception as e:
        conn.logger.bind(tag=TAG).debug(f"ASRレポートキューへの追加に失敗しました: {text}, {e}")