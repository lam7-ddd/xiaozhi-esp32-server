import random
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action

TAG = __name__
logger = setup_logging()

GET_NEWS_FROM_CHINANEWS_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_news_from_chinanews",
        "description": (
            "最新ニュースを取得し、ランダムに1つのニュースを選んで報道します。"
            "ユーザーは社会ニュース、科学技術ニュース、国際ニュースなどのニュースの種類を指定できます。"
            "指定がない場合は、デフォルトで社会ニュースを報道します。"
            "ユーザーは詳細な内容を要求することができ、その場合はニュースの詳細な内容を取得します。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "ニュースのカテゴリ、例：社会、科学技術、国際。オプションのパラメータで、指定しない場合はデフォルトのカテゴリが使用されます",
                },
                "detail": {
                    "type": "boolean",
                    "description": "詳細な内容を取得するかどうか、デフォルトはfalseです。trueの場合、前のニュースの詳細な内容を取得します",
                },
                "lang": {
                    "type": "string",
                    "description": "ユーザーが使用する言語コードを返します。例：zh_CN/zh_HK/en_US/ja_JPなど。デフォルトはzh_CNです",
                },
            },
            "required": ["lang"],
        },
    },
}


def fetch_news_from_rss(rss_url):
    """RSSフィードからニュースリストを取得する"""
    try:
        response = requests.get(rss_url)
        response.raise_for_status()

        # XMLを解析
        root = ET.fromstring(response.content)

        # すべてのitem要素（ニュース項目）を検索
        news_items = []
        for item in root.findall(".//item"):
            title = (
                item.find("title").text if item.find("title") is not None else "タイトルなし"
            )
            link = item.find("link").text if item.find("link") is not None else "#"
            description = (
                item.find("description").text
                if item.find("description") is not None
                else "説明なし"
            )
            pubDate = (
                item.find("pubDate").text
                if item.find("pubDate") is not None
                else "不明な時間"
            )

            news_items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pubDate": pubDate,
                }
            )

        return news_items
    except Exception as e:
        logger.bind(tag=TAG).error(f"RSSニュースの取得に失敗しました: {e}")
        return []


def fetch_news_detail(url):
    """ニュース詳細ページの内容を取得して要約する"""
    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # 本文の内容を抽出しようと試みる（ここのセレクタは実際のウェブサイトの構造に合わせて調整する必要があります）
        content_div = soup.select_one(
            ".content_desc, .content, article, .article-content"
        )
        if content_div:
            paragraphs = content_div.find_all("p")
            content = "\n".join(
                [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
            )
            return content
        else:
            # 特定のコンテンツ領域が見つからない場合は、すべての段落を取得しようと試みる
            paragraphs = soup.find_all("p")
            content = "\n".join(
                [p.get_text().strip() for p in paragraphs if p.get_text().strip()]
            )
            return content[:2000]  # 長さを制限
    except Exception as e:
        logger.bind(tag=TAG).error(f"ニュース詳細の取得に失敗しました: {e}")
        return "詳細な内容を取得できません"


def map_category(category_text):
    """ユーザーが入力した中国語のカテゴリを構成ファイル内のカテゴリキーにマッピングする"""
    if not category_text:
        return None

    # カテゴリマッピング辞書、現在サポートしているのは社会、国際、財経ニュースです。他の種類が必要な場合は構成ファイルを参照してください
    category_map = {
        # 社会ニュース
        "社会": "society_rss_url",
        "社会新闻": "society_rss_url",
        # 国際ニュース
        "国际": "world_rss_url",
        "国际新闻": "world_rss_url",
        # 財経ニュース
        "财经": "finance_rss_url",
        "财经新闻": "finance_rss_url",
        "金融": "finance_rss_url",
        "经济": "finance_rss_url",
    }

    # 小文字に変換してスペースを削除
    normalized_category = category_text.lower().strip()

    # マッピング結果を返す、一致する項目がない場合は元の入力を返す
    return category_map.get(normalized_category, category_text)


@register_function(
    "get_news_from_chinanews",
    GET_NEWS_FROM_CHINANEWS_FUNCTION_DESC,
    ToolType.SYSTEM_CTL,
)
def get_news_from_chinanews(
    conn, category: str = None, detail: bool = False, lang: str = "zh_CN"
):
    """ニュースを取得し、ランダムに1つ選んで報道するか、前のニュースの詳細を取得する"""
    try:
        # detailがTrueの場合、前のニュースの詳細を取得する
        if detail:
            if (
                not hasattr(conn, "last_news_link")
                or not conn.last_news_link
                or "link" not in conn.last_news_link
            ):
                return ActionResponse(
                    Action.REQLLM,
                    "申し訳ありませんが、最近照会されたニュースが見つかりませんでした。まずニュースを1件取得してください。",
                    None,
                )

            link = conn.last_news_link.get("link")
            title = conn.last_news_link.get("title", "不明なタイトル")

            if link == "#":
                return ActionResponse(
                    Action.REQLLM, "申し訳ありませんが、このニュースには詳細を取得するためのリンクがありません。", None
                )

            logger.bind(tag=TAG).debug(f"ニュース詳細の取得: {title}, URL={link}")

            # ニュース詳細の取得
            detail_content = fetch_news_detail(link)

            if not detail_content or detail_content == "詳細な内容を取得できません":
                return ActionResponse(
                    Action.REQLLM,
                    f"申し訳ありませんが、『{title}』の詳細な内容を取得できませんでした。リンクが切れているか、ウェブサイトの構造が変更された可能性があります。",
                    None,
                )

            # 詳細レポートの作成
            detail_report = (
                f"以下のデータに基づき、{lang}でユーザーのニュース詳細照会リクエストに応答してください：\n\n"
                f"ニュースタイトル: {title}\n"
                f"詳細内容: {detail_content}\n\n"
                f"（上記ニュース内容を要約し、重要な情報を抽出し、自然で流暢な方法でユーザーに報道してください。"
                f"これが要約であることには触れず、まるで完全なニュースストーリーを語っているかのようにしてください）"
            )

            return ActionResponse(Action.REQLLM, detail_report, None)

        # そうでなければ、ニュースリストを取得してランダムに1つ選ぶ
        # 設定からRSS URLを取得
        rss_config = conn.config["plugins"]["get_news_from_chinanews"]
        default_rss_url = rss_config.get(
            "default_rss_url", "https://www.chinanews.com.cn/rss/society.xml"
        )

        # 将用户输入的类别映射到配置中的类别键
        mapped_category = map_category(category)

        # 如果提供了类别，尝试从配置中获取对应的URL
        rss_url = default_rss_url
        if mapped_category and mapped_category in rss_config:
            rss_url = rss_config[mapped_category]

        logger.bind(tag=TAG).info(
            f"获取新闻: 原始类别={category}, 映射类别={mapped_category}, URL={rss_url}"
        )

        # 获取新闻列表
        news_items = fetch_news_from_rss(rss_url)

        if not news_items:
            return ActionResponse(
                Action.REQLLM, "抱歉，未能获取到新闻信息，请稍后再试。", None
            )

        # 随机选择一条新闻
        selected_news = random.choice(news_items)

        # 保存当前新闻链接到连接对象，以便后续查询详情
        if not hasattr(conn, "last_news_link"):
            conn.last_news_link = {}
        conn.last_news_link = {
            "link": selected_news.get("link", "#"),
            "title": selected_news.get("title", "未知标题"),
        }

        # 构建新闻报告
        news_report = (
            f"根据下列数据，用{lang}回应用户的新闻查询请求：\n\n"
            f"新闻标题: {selected_news['title']}\n"
            f"发布时间: {selected_news['pubDate']}\n"
            f"新闻内容: {selected_news['description']}\n"
            f"(请以自然、流畅的方式向用户播报这条新闻，可以适当总结内容，"
            f"直接读出新闻即可，不需要额外多余的内容。"
            f"如果用户询问更多详情，告知用户可以说'请详细介绍这条新闻'获取更多内容)"
        )

        return ActionResponse(Action.REQLLM, news_report, None)

    except Exception as e:
        logger.bind(tag=TAG).error(f"获取新闻出错: {e}")
        return ActionResponse(
            Action.REQLLM, "抱歉，获取新闻时发生错误，请稍后再试。", None
        )
