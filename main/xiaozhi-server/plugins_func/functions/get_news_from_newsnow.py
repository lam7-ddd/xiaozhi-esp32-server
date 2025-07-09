import random
import requests
import json
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from markitdown import MarkItDown

TAG = __name__
logger = setup_logging()

CHANNEL_MAP = {
    "V2EX": "v2ex-share",
    "Zhihu": "zhihu",
    "Weibo": "weibo",
    "Lianhe Zaobao": "zaobao",
    "Coolapk": "coolapk",
    "MKTNews": "mktnews-flash",
    "Wallstreetcn": "wallstreetcn-quick",
    "36Kr": "36kr-quick",
    "Douyin": "douyin",
    "Hupu": "hupu",
    "Baidu Tieba": "tieba",
    "Toutiao": "toutiao",
    "ITHome": "ithome",
    "The Paper": "thepaper",
    "Sputnik News": "sputniknewscn",
    "Reference News": "cankaoxiaoxi",
    "PCBeta Windows 11 Forum": "pcbeta-windows11",
    "CLS": "cls-depth",
    "Xueqiu": "xueqiu-hotstock",
    "Gelonghui": "gelonghui",
    "Fastbull Finance": "fastbull-express",
    "Solidot": "solidot",
    "Hacker News": "hackernews",
    "Product Hunt": "producthunt",
    "Github": "github-trending-today",
    "Bilibili": "bilibili-hot-search",
    "Kuaishou": "kuaishou",
    "Kaopu News": "kaopu",
    "Jin10 Data": "jin10",
    "Baidu Hot Search": "baidu",
    "Nowcoder": "nowcoder",
    "SSPAI": "sspai",
    "Juejin": "juejin",
    "iFeng": "ifeng",
    "Chongbuluo": "chongbuluo-latest",
}


# デフォルトのニュースソース辞書。設定で指定されていない場合に使用されます。
DEFAULT_NEWS_SOURCES = "The Paper;Baidu Hot Search;CLS"


def get_news_sources_from_config(conn):
    """設定からニュースソースの文字列を取得します"""
    try:
        # プラグイン設定からニュースソースの取得を試みます
        if (
            conn.config.get("plugins")
            and conn.config["plugins"].get("get_news_from_newsnow")
            and conn.config["plugins"]["get_news_from_newsnow"].get("news_sources")
        ):
            # 設定されたニュースソースの文字列を取得します
            news_sources_config = conn.config["plugins"]["get_news_from_newsnow"][
                "news_sources"
            ]

            if isinstance(news_sources_config, str) and news_sources_config.strip():
                logger.bind(tag=TAG).debug(f"設定されたニュースソースを使用: {news_sources_config}")
                return news_sources_config
            else:
                logger.bind(tag=TAG).warning("ニュースソースの設定が空または形式が正しくありません。デフォルト設定を使用します")
        else:
            logger.bind(tag=TAG).debug("ニュースソースの設定が見つかりません。デフォルト設定を使用します")

        return DEFAULT_NEWS_SOURCES

    except Exception as e:
        logger.bind(tag=TAG).error(f"ニュースソース設定の取得に失敗しました: {e}。デフォルト設定を使用します")
        return DEFAULT_NEWS_SOURCES


# CHANNEL_MAPから利用可能なすべてのニュースソース名を取得します
available_sources = list(CHANNEL_MAP.keys())
example_sources_str = "、".join(available_sources)

GET_NEWS_FROM_NEWSNOW_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news_from_newsnow",
        "description": (
            "最新ニュースを取得し、ランダムに1つ選んで読み上げます。"
            f"ユーザーは異なるニュースソースを選択できます。標準的な名称は次のとおりです：{example_sources_str}"
            "例えば、ユーザーが「Baidu News」を要求した場合、実際には「Baidu Hot Search」を指します。指定がない場合は、デフォルトで「The Paper」から取得します。"
            "ユーザーは詳細な内容を要求でき、その場合はニュースの詳細な内容を取得します。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": f"ニュースソースの標準的な中国語名（例：{example_sources_str}など）。オプションパラメータで、指定しない場合はデフォルトのニュースソースが使用されます",
                },
                "detail": {
                    "type": "boolean",
                    "description": "詳細コンテンツを取得するかどうか。デフォルトはfalseです。trueの場合、前のニュースの詳細コンテンツを取得します",
                },
                "lang": {
                    "type": "string",
                    "description": "ユーザーが使用する言語コードを返します（例：zh_CN/zh_HK/en_US/ja_JPなど）。デフォルトはja_JPです",
                },
            },
            "required": ["lang"],
        },
    },
}


def fetch_news_from_api(conn, source="thepaper"):
    """APIからニュースリストを取得します"""
    try:
        api_url = f"https://newsnow.busiyi.world/api/s?id={source}"
        if conn.config["plugins"].get("get_news_from_newsnow") and conn.config[
            "plugins"
        ]["get_news_from_newsnow"].get("url"):
            api_url = conn.config["plugins"]["get_news_from_newsnow"]["url"] + source

        response = requests.get(api_url, timeout=10)
        response.raise_for_status()

        data = response.json()

        if "items" in data:
            return data["items"]
        else:
            logger.bind(tag=TAG).error(f"ニュースAPIのレスポンス形式が正しくありません: {data}")
            return []

    except Exception as e:
        logger.bind(tag=TAG).error(f"ニュースAPIの取得に失敗しました: {e}")
        return []


def fetch_news_detail(url):
    """ニュース詳細ページの内容を取得し、MarkItDownを使用してHTMLをクリーンアップします"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # MarkItDownを使用してHTMLコンテンツをクリーンアップします
        md = MarkItDown(enable_plugins=False)
        result = md.convert(response)

        # クリーンアップされたテキストコンテンツを取得します
        clean_text = result.text_content

        # クリーンアップされたコンテンツが空の場合、プロンプト情報を返します
        if not clean_text or len(clean_text.strip()) == 0:
            logger.bind(tag=TAG).warning(f"クリーンアップ後のニュースコンテンツが空です: {url}")
            return "ニュースの詳細コンテンツを解析できません。ウェブサイトの構造が特殊であるか、コンテンツが制限されている可能性があります。"

        return clean_text
    except Exception as e:
        logger.bind(tag=TAG).error(f"ニュース詳細の取得に失敗しました: {e}")
        return "詳細コンテンツを取得できません"


@register_function(
    "get_news_from_newsnow",
    GET_NEWS_FROM_NEWSNOW_FUNCTION_DESC,
    ToolType.SYSTEM_CTL,
)
def get_news_from_newsnow(
    conn, source: str = "The Paper", detail: bool = False, lang: str = "zh_CN"
):
    """ニュースを取得してランダムに1つを選択してブロードキャストするか、前のニュースの詳細を取得します"""
    try:
        # 現在設定されているニュースソースを取得します
        news_sources = get_news_sources_from_config(conn)

        # detailがTrueの場合、前のニュースの詳細コンテンツを取得します
        detail = str(detail).lower() == "true"
        if detail:
            if (
                not hasattr(conn, "last_newsnow_link")
                or not conn.last_newsnow_link
                or "url" not in conn.last_newsnow_link
            ):
                return ActionResponse(
                    Action.REQLLM,
                    "申し訳ありませんが、最近照会されたニュースが見つかりませんでした。まずニュースを1件取得してください。",

                    None,
                )

            url = conn.last_newsnow_link.get("url")
            title = conn.last_newsnow_link.get("title", "不明なタイトル")
            source_id = conn.last_newsnow_link.get("source_id", "thepaper")
            source_name = CHANNEL_MAP.get(source_id, "不明なソース")

            if not url or url == "#":
                return ActionResponse(
                    Action.REQLLM, "申し訳ありませんが、このニュースには詳細な内容を取得するための利用可能なリンクがありません。", None
                )

            logger.bind(tag=TAG).debug(
                f"ニュース詳細の取得: {title}, ソース: {source_name}, URL={url}"
            )

            # ニュース詳細の取得
            detail_content = fetch_news_detail(url)

            if not detail_content or detail_content == "詳細コンテンツを取得できません":
                return ActionResponse(
                    Action.REQLLM,
                    f"申し訳ありませんが、「{title}」の詳細コンテンツを取得できません。リンクが切れているか、ウェブサイトの構造が変更された可能性があります。",
                    None,
                )

            # 詳細レポートの作成
            detail_report = (
                f"以下のデータに基づき、{lang}でユーザーのニュース詳細問い合わせリクエストに応答してください：\n\n"
                f"ニュースタイトル: {title}\n"
                # f"ニュースソース: {source_name}\n"
                f"詳細内容: {detail_content}\n\n"
                f"（上記ニュース内容を要約し、キーポイントを抽出し、自然で流暢な方法でユーザーに伝えてください。"
                f"要約であることには触れず、まるで完全なニュース記事を語っているかのようにしてください）"
            )

            return ActionResponse(Action.REQLLM, detail_report, None)

        # それ以外の場合は、ニュースリストを取得してランダムに1つ選択します
        # 中国語名を英語IDに変換します
        english_source_id = None

        # 入力された中国語名が設定されたニュースソースに含まれているか確認します
        news_sources_list = [
            name.strip() for name in news_sources.split(";") if name.strip()
        ]
        if source in news_sources_list:
            # 入力された中国語名が設定されたニュースソースにある場合、CHANNEL_MAPで対応する英語IDを検索します
            english_source_id = CHANNEL_MAP.get(source)

        # 対応する英語IDが見つからない場合は、デフォルトのソースを使用します
        if not english_source_id:
            logger.bind(tag=TAG).warning(f"無効なニュースソース: {source}。デフォルトソースのThe Paperを使用します")
            english_source_id = "thepaper"
            source = "The Paper"

        logger.bind(tag=TAG).info(f"ニュースを取得: ソース={source}({english_source_id})")

        # ニュースリストの取得
        news_items = fetch_news_from_api(conn, english_source_id)

        if not news_items:
            return ActionResponse(
                Action.REQLLM,
                f"申し訳ありませんが、{source}からニュース情報を取得できませんでした。後でもう一度試すか、他のニュースソースを試してください。",
                None,
            )

        # ランダムにニュースを1件選択します
        selected_news = random.choice(news_items)

        # 現在のニュースリンクを接続オブジェクトに保存し、後で詳細を照会できるようにします
        if not hasattr(conn, "last_newsnow_link"):
            conn.last_newsnow_link = {}
        conn.last_newsnow_link = {
            "url": selected_news.get("url", "#"),
            "title": selected_news.get("title", "不明なタイトル"),
            "source_id": english_source_id,
        }

        # ニュースレポートの作成
        news_report = (
            f"以下のデータに基づき、{lang}でユーザーのニュース問い合わせリクエストに応答してください：\n\n"
            f"ニュースタイトル: {selected_news['title']}\n"
            # f"ニュースソース: {source}\n"
            f"（このニュースのタイトルを自然で流暢な方法でユーザーに伝え、"
            f"詳細な内容を要求できることを示唆してください。その場合、ニュースの詳細な内容が取得されます。）"
        )

        return ActionResponse(Action.REQLLM, news_report, None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"ニュースの取得中にエラーが発生しました: {e}")
        return ActionResponse(
            Action.REQLLM, "申し訳ありませんが、ニュースの取得中にエラーが発生しました。後でもう一度お試しください。", None
        )
