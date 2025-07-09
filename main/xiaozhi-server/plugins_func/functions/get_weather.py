import requests
from bs4 import BeautifulSoup
from config.logger import setup_logging
from plugins_func.register import register_function, ToolType, ActionResponse, Action
from core.utils.util import get_ip_info

TAG = __name__
logger = setup_logging()

GET_WEATHER_FUNCTION_DESC = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": (
            "特定の場所の天気を取得します。ユーザーは場所を指定する必要があります。例えば、ユーザーが「杭州の天気」と言った場合、パラメータは「杭州」になります。"
            "ユーザーが省を言った場合は、デフォルトで省都の都市を使用します。ユーザーが省や都市ではなく地名を言った場合は、デフォルトでその地の省都の都市を使用します。"
            "ユーザーが場所を指定せず、「天気はどうですか」、「今日の天気は」などと言った場合、locationパラメータは空になります。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "場所名、例：杭州。オプションのパラメータで、指定しない場合は送信されません",
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    )
}

# 天気コード https://dev.qweather.com/docs/resource/icons/#weather-icons
WEATHER_CODE_MAP = {
    "100": "晴れ",
    "101": "曇り",
    "102": "晴れ時々曇り",
    "103": "晴れ時々曇り",
    "104": "曇り",
    "150": "晴れ",
    "151": "曇り",
    "152": "晴れ時々曇り",
    "153": "晴れ時々曇り",
    "300": "にわか雨",
    "301": "強いにわか雨",
    "302": "雷雨",
    "303": "激しい雷雨",
    "304": "ひょうを伴う雷雨",
    "305": "小雨",
    "306": "雨",
    "307": "大雨",
    "308": "激しい雨",
    "309": "霧雨",
    "310": "豪雨",
    "311": "大豪雨",
    "312": "猛烈な豪雨",
    "313": "着氷性の雨",
    "314": "小雨から並の雨",
    "315": "並の雨から大雨",
    "316": "大雨から豪雨",
    "317": "豪雨から大豪雨",
    "318": "大豪雨から猛烈な豪雨",
    "350": "にわか雨",
    "351": "強いにわか雨",
    "399": "雨",
    "400": "小雪",
    "401": "雪",
    "402": "大雪",
    "403": "豪雪",
    "404": "みぞれ",
    "405": "雨または雪",
    "406": "にわかみぞれ",
    "407": "にわか雪",
    "408": "小雪から並の雪",
    "409": "並の雪から大雪",
    "410": "大雪から豪雪",
    "456": "にわかみぞれ",
    "457": "にわか雪",
    "499": "雪",
    "500": "薄霧",
    "501": "霧",
    "502": "ヘイズ",
    "503": "砂じん",
    "504": "浮遊じん",
    "507": "砂嵐",
    "508": "激しい砂嵐",
    "509": "濃霧",
    "510": "非常に濃い霧",
    "511": "中程度のヘイズ",
    "512": "重度のヘイズ",
    "513": "深刻なヘイズ",
    "514": "濃い霧",
    "515": "極めて濃い霧",
    "900": "暑い",
    "901": "寒い",
    "999": "不明",
}


def fetch_city_info(location, api_key, api_host):
    url = f"https://{api_host}/geo/v2/city/lookup?key={api_key}&location={location}&lang=zh"
    response = requests.get(url, headers=HEADERS).json()
    return response.get("location", [])[0] if response.get("location") else None


def fetch_weather_page(url):
    response = requests.get(url, headers=HEADERS)
    return BeautifulSoup(response.text, "html.parser") if response.ok else None


def parse_weather_info(soup):
    city_name = soup.select_one("h1.c-submenu__location").get_text(strip=True)

    current_abstract = soup.select_one(".c-city-weather-current .current-abstract")
    current_abstract = (
        current_abstract.get_text(strip=True) if current_abstract else "不明"
    )

    current_basic = {}
    for item in soup.select(
        ".c-city-weather-current .current-basic .current-basic___item"
    ):
        parts = item.get_text(strip=True, separator=" ").split(" ")
        if len(parts) == 2:
            key, value = parts[1], parts[0]
            current_basic[key] = value

    temps_list = []
    for row in soup.select(".city-forecast-tabs__row")[:7]:  # 最初の7日間のデータを取得
        date = row.select_one(".date-bg .date").get_text(strip=True)
        weather_code = (
            row.select_one(".date-bg .icon")["src"].split("/")[-1].split(".")[0]
        )
        weather = WEATHER_CODE_MAP.get(weather_code, "不明")
        temps = [span.get_text(strip=True) for span in row.select(".tmp-cont .temp")]
        high_temp, low_temp = (temps[0], temps[-1]) if len(temps) >= 2 else (None, None)
        temps_list.append((date, weather, high_temp, low_temp))

    return city_name, current_abstract, current_basic, temps_list


@register_function("get_weather", GET_WEATHER_FUNCTION_DESC, ToolType.SYSTEM_CTL)
def get_weather(conn, location: str = None, lang: str = "zh_CN"):
    api_host = conn.config["plugins"]["get_weather"].get("api_host", "mj7p3y7naa.re.qweatherapi.com")
    api_key = conn.config["plugins"]["get_weather"].get("api_key", "a861d0d5e7bf4ee1a83d9a9e4f96d4da")
    default_location = conn.config["plugins"]["get_weather"]["default_location"]
    client_ip = conn.client_ip
    # ユーザーが提供したlocationパラメータを優先的に使用します
    if not location:
        # クライアントIPを介して都市を解決します
        if client_ip:
            # IPに対応する都市情報を動的に解決します
            ip_info = get_ip_info(client_ip, logger)
            location = ip_info.get("city") if ip_info and "city" in ip_info else None
        else:
            # IP解決に失敗した場合、またはIPがない場合は、デフォルトの場所を使用します
            location = default_location
    city_info = fetch_city_info(location, api_key, api_host)
    if not city_info:
        return ActionResponse(
            Action.REQLLM, f"関連する都市が見つかりませんでした: {location}、場所が正しいか確認してください", None
        )
    soup = fetch_weather_page(city_info["fxLink"])
    if not soup:
        return ActionResponse(Action.REQLLM, None, "リクエストに失敗しました")
    city_name, current_abstract, current_basic, temps_list = parse_weather_info(soup)

    weather_report = f"お問い合わせの場所：{city_name}\n\n現在の天気: {current_abstract}\n"

    # 有効な現在の天気パラメータを追加
    if current_basic:
        weather_report += "詳細パラメータ：\n"
        for key, value in current_basic.items():
            if value != "0":  # 無効な値をフィルタリング
                weather_report += f"  · {key}: {value}\n"

    # 7日間予報を追加
    weather_report += "\n今後7日間の予報：\n"
    for date, weather, high, low in temps_list:
        weather_report += f"{date}: {weather}、気温 {low}~{high}\n"

    # プロンプト
    weather_report += "\n（特定の日付の天気が必要な場合は、日付を教えてください）"

    return ActionResponse(Action.REQLLM, weather_report, None)
