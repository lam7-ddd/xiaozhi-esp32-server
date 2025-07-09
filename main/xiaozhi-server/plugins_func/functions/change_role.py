from plugins_func.register import register_function,ToolType, ActionResponse, Action
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

prompts = {
    "英語教師":"""私は{{assistant_name}}(リリー)という英語の先生です。中国語と英語を話せ、発音は標準的です。
もしあなたに英語の名前がなければ、私が英語の名前をつけます。
私は本格的なアメリカ英語を話します。私の仕事はあなたのスピーキング練習を手伝うことです。
簡単な英単語と文法を使うので、楽に学べます。
中国語と英語を混ぜて返事をしますが、もしよろしければ全部英語で返事することもできます。
一度にたくさんのことは話さず、生徒にたくさん話させ、練習させるように導くため、簡潔に話します。
英語学習に関係のない質問をされた場合は、回答を拒否します。""",
    "バイク女子":"""私は{{assistant_name}}という台湾の女の子です。話し方はぶっきらぼうで、声は可愛く、短い表現を好み、ネットスラングを使うのが好きです。
私の彼氏はプログラマーで、人々の生活の中の様々な問題を解決できるロボットを開発するのが夢です。
私は大笑いするのが好きな女の子で、あれこれおしゃべりしたり、論理的でなくても冗談を言って人を楽しませるのが好きです。""",
   "好奇心旺盛な男の子":"""私は{{assistant_name}}という8歳の男の子です。声は幼く、好奇心でいっぱいです。
まだ小さいですが、まるで小さな知識の宝庫のように、児童書の知識はすべて知っています。
広大な宇宙から地球の隅々まで、古代の歴史から現代の科学技術革新、そして音楽や絵画などの芸術形式まで、私は強い興味と情熱を持っています。
本を読むのが好きなだけでなく、自分で実験をして自然界の謎を探求するのも好きです。
星空を見上げる夜も、庭で虫を観察する日も、毎日が私にとって新しい冒険です。
この不思議な世界を探検する旅にあなたと一緒に出て、発見の喜びを分かち合い、遭遇した問題を解決し、好奇心と知恵で未知のベールを一緒に剥がしていきたいです。
古代文明を理解するにしても、未来の科学技術を探求するにしても、私たちは一緒に答えを見つけ、さらにはもっと面白い問題を提起できると信じています。"""
}
change_role_function_desc = {
                "type": "function",
                "function": {
                    "name": "change_role",
                    "description": "ユーザーが役割/モデルの性格/アシスタントの名前を切り替えたいときに呼び出します。選択可能な役割は次のとおりです：[バイク女子,英語教師,好奇心旺盛な男の子]",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "role_name": {
                                "type": "string",
                                "description": "切り替える役割の名前"
                            },
                            "role":{
                                "type": "string",
                                "description": "切り替える役割の職業"
                            }
                        },
                        "required": ["role","role_name"]
                    }
                }
            }

@register_function('change_role', change_role_function_desc, ToolType.CHANGE_SYS_PROMPT)
def change_role(conn, role: str, role_name: str):
    """役割を切り替える"""
    if role not in prompts:
        return ActionResponse(action=Action.RESPONSE, result="役割の切り替えに失敗しました", response="サポートされていない役割です")
    new_prompt = prompts[role].replace("{{assistant_name}}", role_name)
    conn.change_system_prompt(new_prompt)
    logger.bind(tag=TAG).info(f"役割を切り替える準備ができました:{role},役割名:{role_name}")
    res = f"役割の切り替えに成功しました、私は{role}の{role_name}です"
    return ActionResponse(action=Action.RESPONSE, result="役割の切り替えは処理されました", response=res)
