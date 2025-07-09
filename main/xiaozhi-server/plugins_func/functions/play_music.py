from config.logger import setup_logging
import os
import re
import time
import random
import asyncio
import difflib
import traceback
from pathlib import Path
from core.utils import p3
from core.handle.sendAudioHandle import send_stt_message
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.dialogue import Message
from core.providers.tts.dto.dto import TTSMessageDTO, SentenceType, ContentType

TAG = __name__

MUSIC_CACHE = {}

play_music_function_desc = {
    "type": "function",
    "function": {
        "name": "play_music",
        "description": "歌を歌う、音楽を聴く、音楽を再生するためのメソッド。",
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {
                    "type": "string",
                    "description": "曲名。ユーザーが具体的な曲名を指定しない場合は'random'になります。明確に指定された場合は曲名を返します。例: ```ユーザー:「きらきら星」を再生して\nパラメータ:きらきら星``` ```ユーザー:音楽を再生して\nパラメータ:random```",
                }
            },
            "required": ["song_name"],
        },
    },
}


@register_function("play_music", play_music_function_desc, ToolType.SYSTEM_CTL)
def play_music(conn, song_name: str):
    try:
        music_intent = (
            f"音楽を再生 {song_name}" if song_name != "random" else "音楽をランダム再生"
        )

        # イベントループの状態を確認
        if not conn.loop.is_running():
            conn.logger.bind(tag=TAG).error("イベントループが実行されていないため、タスクを送信できません")
            return ActionResponse(
                action=Action.RESPONSE, result="システムがビジーです", response="しばらくしてからもう一度お試しください"
            )

        # 非同期タスクを送信
        future = asyncio.run_coroutine_threadsafe(
            handle_music_command(conn, music_intent), conn.loop
        )

        # ノンブロッキングコールバック処理
        def handle_done(f):
            try:
                f.result()  # ここで成功ロジックを処理できます
                conn.logger.bind(tag=TAG).info("再生完了")
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"再生失敗: {e}")

        future.add_done_callback(handle_done)

        return ActionResponse(
            action=Action.NONE, result="コマンドを受信しました", response="音楽を再生しています"
        )
    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"音楽インテントの処理中にエラーが発生しました: {e}")
        return ActionResponse(
            action=Action.RESPONSE, result=str(e), response="音楽の再生中にエラーが発生しました"
        )


def _extract_song_name(text):
    """ユーザーの入力から曲名を抽出します"""
    for keyword in ["音楽を再生"]:
        if keyword in text:
            parts = text.split(keyword)
            if len(parts) > 1:
                return parts[1].strip()
    return None


def _find_best_match(potential_song, music_files):
    """最も一致する曲を検索します"""
    best_match = None
    highest_ratio = 0

    for music_file in music_files:
        song_name = os.path.splitext(music_file)[0]
        ratio = difflib.SequenceMatcher(None, potential_song, song_name).ratio()
        if ratio > highest_ratio and ratio > 0.4:
            highest_ratio = ratio
            best_match = music_file
    return best_match


def get_music_files(music_dir, music_ext):
    music_dir = Path(music_dir)
    music_files = []
    music_file_names = []
    for file in music_dir.rglob("*"):
        # ファイルかどうかを判断
        if file.is_file():
            # ファイルの拡張子を取得
            ext = file.suffix.lower()
            # 拡張子がリストにあるか判断
            if ext in music_ext:
                # 相対パスを追加
                music_files.append(str(file.relative_to(music_dir)))
                music_file_names.append(
                    os.path.splitext(str(file.relative_to(music_dir)))[0]
                )
    return music_files, music_file_names


def initialize_music_handler(conn):
    global MUSIC_CACHE
    if MUSIC_CACHE == {}:
        if "play_music" in conn.config["plugins"]:
            MUSIC_CACHE["music_config"] = conn.config["plugins"]["play_music"]
            MUSIC_CACHE["music_dir"] = os.path.abspath(
                MUSIC_CACHE["music_config"].get("music_dir", "./music")  # デフォルトパスの変更
            )
            MUSIC_CACHE["music_ext"] = MUSIC_CACHE["music_config"].get(
                "music_ext", (".mp3", ".wav", ".p3")
            )
            MUSIC_CACHE["refresh_time"] = MUSIC_CACHE["music_config"].get(
                "refresh_time", 60
            )
        else:
            MUSIC_CACHE["music_dir"] = os.path.abspath("./music")
            MUSIC_CACHE["music_ext"] = (".mp3", ".wav", ".p3")
            MUSIC_CACHE["refresh_time"] = 60
        # 音楽ファイルリストを取得
        MUSIC_CACHE["music_files"], MUSIC_CACHE["music_file_names"] = get_music_files(
            MUSIC_CACHE["music_dir"], MUSIC_CACHE["music_ext"]
        )
        MUSIC_CACHE["scan_time"] = time.time()
    return MUSIC_CACHE


async def handle_music_command(conn, text):
    initialize_music_handler(conn)
    global MUSIC_CACHE

    """音楽再生コマンドを処理します"""
    clean_text = re.sub(r"[^\w\s]", "", text).strip()
    conn.logger.bind(tag=TAG).debug(f"音楽コマンドかどうかを確認: {clean_text}")

    # 具体的な曲名との一致を試みます
    if os.path.exists(MUSIC_CACHE["music_dir"]):
        if time.time() - MUSIC_CACHE["scan_time"] > MUSIC_CACHE["refresh_time"]:
            # 音楽ファイルリストを更新
            MUSIC_CACHE["music_files"], MUSIC_CACHE["music_file_names"] = (
                get_music_files(MUSIC_CACHE["music_dir"], MUSIC_CACHE["music_ext"])
            )
            MUSIC_CACHE["scan_time"] = time.time()

        potential_song = _extract_song_name(clean_text)
        if potential_song:
            best_match = _find_best_match(potential_song, MUSIC_CACHE["music_files"])
            if best_match:
                conn.logger.bind(tag=TAG).info(f"最も一致する曲が見つかりました: {best_match}")
                await play_local_music(conn, specific_file=best_match)
                return True
    # 一般的な音楽再生コマンドかどうかを確認
    await play_local_music(conn)
    return True


def _get_random_play_prompt(song_name):
    """ランダム再生用のプロンプトを生成します"""
    # ファイル拡張子を削除
    clean_name = os.path.splitext(song_name)[0]
    prompts = [
        f"{clean_name}を再生します",
        f"曲をお楽しみください、{clean_name}",
        f"まもなく再生します、{clean_name}",
        f"お届けします、{clean_name}",
        f"聴きましょう、{clean_name}",
        f"次にお楽しみください、{clean_name}",
        f"お送りします、{clean_name}",
    ]
    # seedを設定せずにrandom.choiceを直接使用
    return random.choice(prompts)


async def play_local_music(conn, specific_file=None):
    global MUSIC_CACHE
    """ローカルの音楽ファイルを再生します"""
    try:
        if not os.path.exists(MUSIC_CACHE["music_dir"]):
            conn.logger.bind(tag=TAG).error(
                f"音楽ディレクトリが存在しません: " + MUSIC_CACHE["music_dir"]
            )
            return

        # 确保路径正确性
        if specific_file:
            selected_music = specific_file
            music_path = os.path.join(MUSIC_CACHE["music_dir"], specific_file)
        else:
            if not MUSIC_CACHE["music_files"]:
                conn.logger.bind(tag=TAG).error("未找到MP3音乐文件")
                return
            selected_music = random.choice(MUSIC_CACHE["music_files"])
            music_path = os.path.join(MUSIC_CACHE["music_dir"], selected_music)

        if not os.path.exists(music_path):
            conn.logger.bind(tag=TAG).error(f"选定的音乐文件不存在: {music_path}")
            return
        text = _get_random_play_prompt(selected_music)
        await send_stt_message(conn, text)
        conn.dialogue.put(Message(role="assistant", content=text))

        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.FIRST,
                content_type=ContentType.ACTION,
            )
        )
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.MIDDLE,
                content_type=ContentType.TEXT,
                content_detail=text,
            )
        )
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.MIDDLE,
                content_type=ContentType.FILE,
                content_file=music_path,
            )
        )
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=conn.sentence_id,
                sentence_type=SentenceType.LAST,
                content_type=ContentType.ACTION,
            )
        )

    except Exception as e:
        conn.logger.bind(tag=TAG).error(f"播放音乐失败: {str(e)}")
        conn.logger.bind(tag=TAG).error(f"详细错误: {traceback.format_exc()}")
