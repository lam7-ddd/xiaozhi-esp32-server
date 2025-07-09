# グローバルログレベルをWARNINGに設定し、INFOレベルのログを抑制
logging.basicConfig(level=logging.WARNING)


class AsyncPerformanceTester:
    def __init__(self):
        self.config = load_config()
        self.test_sentences = self.config.get("module_test", {}).get(
            "test_sentences",
            [
                "こんにちは、自己紹介をしてください",
                "今日の天気はどうですか？",
                "量子計算の基本原理と応用の前景を100字で概説してください",
            ],
        )

        self.test_wav_list = []
        self.wav_root = r"config/assets"
        for file_name in os.listdir(self.wav_root):
            file_path = os.path.join(self.wav_root, file_name)
            # ファイルサイズが300KBより大きいかチェック
            if os.path.getsize(file_path) > 300 * 1024:  # 300KB = 300 * 1024 bytes
                with open(file_path, "rb") as f:
                    self.test_wav_list.append(f.read())

        self.results = {"llm": {}, "tts": {}, "stt": {}, "combinations": []}

    async def _check_ollama_service(self, base_url: str, model_name: str) -> bool:
        """Ollamaサービスのステータスを非同期でチェック"""
        async with aiohttp.ClientSession() as session:
            try:
                # サービスが利用可能かチェック
                async with session.get(f"{base_url}/api/version") as response:
                    if response.status != 200:
                        print(f"🚫 Ollamaサービスが起動していないかアクセスできない: {base_url}")
                        return False

                # モデルが存在するかチェック
                async with session.get(f"{base_url}/api/tags") as response:
                    if response.status == 200:
                        data = await response.json()
                        models = data.get("models", [])
                        if not any(model["name"] == model_name for model in models):
                            print(
                                f"🚫 Ollamaモデル {model_name} が見つかりません。まず ollama pull {model_name} でダウンロードしてください"
                            )
                            return False
                    else:
                        print(f"🚫 Ollamaモデルのリストを取得できません")
                        return False
                return True
            except Exception as e:
                print(f"🚫 Ollamaサービスに接続できません: {str(e)}")
                return False

    async def _test_tts(self, tts_name: str, config: Dict) -> Dict:
        """単一のTTSのパフォーマンスを非同期でテスト"""
        try:
            logging.getLogger("core.providers.tts.base").setLevel(logging.WARNING)

            token_fields = ["access_token", "api_key", "token"]
            if any(
                field in config
                and any(x in config[field] for x in ["あなたの", "placeholder"])
                for field in token_fields
            ):
                print(f"⏭️  TTS {tts_name} のアクセストークン/アクセスキーが設定されていません。スキップします")
                return {"name": tts_name, "type": "tts", "errors": 1}

            module_type = config.get("type", tts_name)
            tts = create_tts_instance(module_type, config, delete_audio_file=True)

            print(f"🎵 TTS {tts_name} のテストを開始します")

            tmp_file = tts.generate_filename()
            await tts.text_to_speak("テスト接続", tmp_file)

            if not tmp_file or not os.path.exists(tmp_file):
                print(f"❌ {tts_name} の接続に失敗しました")
                return {"name": tts_name, "type": "tts", "errors": 1}

            total_time = 0
            test_count = len(self.test_sentences[:2])

            for i, sentence in enumerate(self.test_sentences[:2], 1):
                start = time.time()
                tmp_file = tts.generate_filename()
                await tts.text_to_speak(sentence, tmp_file)
                duration = time.time() - start
                total_time += duration

                if tmp_file and os.path.exists(tmp_file):
                    print(f"✓ {tts_name} [{i}/{test_count}]")
                else:
                    print(f"✗ {tts_name} [{i}/{test_count}]")
                    return {"name": tts_name, "type": "tts", "errors": 1}

            return {
                "name": tts_name,
                "type": "tts",
                "avg_time": total_time / test_count,
                "errors": 0,
            }

        except Exception as e:
            print(f"⚠️ {tts_name} のテストに失敗しました: {str(e)}")
            return {"name": tts_name, "type": "tts", "errors": 1}

    async def _test_stt(self, stt_name: str, config: Dict) -> Dict:
        """単一のSTTのパフォーマンスを非同期でテスト"""
        try:
            logging.getLogger("core.providers.asr.base").setLevel(logging.WARNING)
            token_fields = ["access_token", "api_key", "token"]
            if any(
                field in config
                and any(x in config[field] for x in ["あなたの", "placeholder"])
                for field in token_fields
            ):
                print(f"⏭️  STT {stt_name} のアクセストークン/アクセスキーが設定されていません。スキップします")
                return {"name": stt_name, "type": "stt", "errors": 1}

            module_type = config.get("type", stt_name)
            stt = create_stt_instance(module_type, config, delete_audio_file=True)
            stt.audio_format = "pcm"

            print(f"🎵 STT {stt_name} のテストを開始します")

            text, _ = await stt.speech_to_text(
                [self.test_wav_list[0]], "1", stt.audio_format
            )

            if text is None:
                print(f"❌ {stt_name} の接続に失敗しました")
                return {"name": stt_name, "type": "stt", "errors": 1}

            total_time = 0
            test_count = len(self.test_wav_list)

            for i, sentence in enumerate(self.test_wav_list, 1):
                start = time.time()
                text, _ = await stt.speech_to_text([sentence], "1", stt.audio_format)
                duration = time.time() - start
                total_time += duration

                if text:
                    print(f"✓ {stt_name} [{i}/{test_count}]")
                else:
                    print(f"✗ {stt_name} [{i}/{test_count}]")
                    return {"name": stt_name, "type": "stt", "errors": 1}

            return {
                "name": stt_name,
                "type": "stt",
                "avg_time": total_time / test_count,
                "errors": 0,
            }

        except Exception as e:
            print(f"⚠️ {stt_name} のテストに失敗しました: {str(e)}")
            return {"name": stt_name, "type": "stt", "errors": 1}

    async def _test_llm(self, llm_name: str, config: Dict) -> Dict:
        """単一のLLMのパフォーマンスを非同期でテスト"""
        try:
            # Ollamaの場合、APIキーをチェックせずにサービスステータスをチェック
            if llm_name == "Ollama":
                base_url = config.get("base_url", "http://localhost:11434")
                model_name = config.get("model_name")
                if not model_name:
                    print(f"🚫 Ollamaのモデル名が設定されていません")
                    return {"name": llm_name, "type": "llm", "errors": 1}

                if not await self._check_ollama_service(base_url, model_name):
                    return {"name": llm_name, "type": "llm", "errors": 1}
            else:
                if "api_key" in config and any(
                    x in config["api_key"] for x in ["あなたの", "placeholder", "sk-xxx"]
                ):
                    print(f"🚫 LLM {llm_name} のAPIキーが設定されていません。スキップします")
                    return {"name": llm_name, "type": "llm", "errors": 1}

            # 実際のタイプ（古い設定との互換性のため）
            module_type = config.get("type", llm_name)
            llm = create_llm_instance(module_type, config)

            # UTF-8エンコードを使用
            test_sentences = [
                s.encode("utf-8").decode("utf-8") for s in self.test_sentences
            ]

            # 各文のテストタスクを作成
            sentence_tasks = []
            for sentence in test_sentences:
                sentence_tasks.append(
                    self._test_single_sentence(llm_name, llm, sentence)
                )

            # 全文のテストを並行実行
            sentence_results = await asyncio.gather(*sentence_tasks)

            # 結果を処理
            valid_results = [r for r in sentence_results if r is not None]
            if not valid_results:
                print(f"⚠️  {llm_name} の有効なデータがありません。設定が間違っている可能性があります")
                return {"name": llm_name, "type": "llm", "errors": 1}

            first_token_times = [r["first_token_time"] for r in valid_results]
            response_times = [r["response_time"] for r in valid_results]

            # 異常データをフィルタリング
            mean = statistics.mean(response_times)
            stdev = statistics.stdev(response_times) if len(response_times) > 1 else 0
            filtered_times = [t for t in response_times if t <= mean + 3 * stdev]

            if len(filtered_times) < len(test_sentences) * 0.5:
                print(f"⚠️  {llm_name} の有効なデータが不足しています。ネットワークが不安定している可能性があります")
                return {"name": llm_name, "type": "llm", "errors": 1}

            return {
                "name": llm_name,
                "type": "llm",
                "avg_response": sum(response_times) / len(response_times),
                "avg_first_token": sum(first_token_times) / len(first_token_times),
                "std_first_token": (
                    statistics.stdev(first_token_times)
                    if len(first_token_times) > 1
                    else 0
                ),
                "std_response": (
                    statistics.stdev(response_times) if len(response_times) > 1 else 0
                ),
                "errors": 0,
            }
        except Exception as e:
            print(f"LLM {llm_name} のテストに失敗しました: {str(e)}")
            return {"name": llm_name, "type": "llm", "errors": 1}

    async def _test_single_sentence(self, llm_name: str, llm, sentence: str) -> Dict:
        """単一の文のパフォーマンスをテスト"""
        try:
            print(f"📝 {llm_name} のテストを開始します: {sentence[:20]}...")
            sentence_start = time.time()
            first_token_received = False
            first_token_time = None

            async def process_response():
                nonlocal first_token_received, first_token_time
                for chunk in llm.response(
                    "perf_test", [{"role": "user", "content": sentence}]
                ):
                    if not first_token_received and chunk.strip() != "":
                        first_token_time = time.time() - sentence_start
                        first_token_received = True
                        print(f"✓ {llm_name} の最初のトークン: {first_token_time:.3f}秒")
                    yield chunk

            response_chunks = []
            async for chunk in process_response():
                response_chunks.append(chunk)

            response_time = time.time() - sentence_start
            print(f"✓ {llm_name} の応答完了: {response_time:.3f}秒")

            if first_token_time is None:
                first_token_time = (
                    response_time  # 最初のトークンが検出されなかった場合、応答時間を使用
                )

            return {
                "name": llm_name,
                "type": "llm",
                "first_token_time": first_token_time,
                "response_time": response_time,
            }
        except Exception as e:
            print(f"⚠️ {llm_name} の文のテストに失敗しました: {str(e)}")
            return None

    def _generate_combinations(self):
        """ベストな組み合わせを生成"""
        valid_llms = [
            k
            for k, v in self.results["llm"].items()
            if v["errors"] == 0 and v["avg_first_token"] >= 0.05
        ]
        valid_tts = [k for k, v in self.results["tts"].items() if v["errors"] == 0]
        valid_stt = [k for k, v in self.results["stt"].items() if v["errors"] == 0]

        # ベースライン値を取得
        min_first_token = (
            min([self.results["llm"][llm]["avg_first_token"] for llm in valid_llms])
            if valid_llms
            else 1
        )
        min_tts_time = (
            min([self.results["tts"][tts]["avg_time"] for tts in valid_tts])
            if valid_tts
            else 1
        )
        min_stt_time = (
            min([self.results["stt"][stt]["avg_time"] for stt in valid_stt])
            if valid_stt
            else 1
        )

        for llm in valid_llms:
            for tts in valid_tts:
                for stt in valid_stt:
                    # 相対的なパフォーマンススコアを計算（小さい方が良い）
                    llm_score = (
                        self.results["llm"][llm]["avg_first_token"] / min_first_token
                    )
                    tts_score = self.results["tts"][tts]["avg_time"] / min_tts_time
                    stt_score = self.results["stt"][stt]["avg_time"] / min_stt_time

                    # 安定性スコアを計算（標準偏差/平均値、小さい方が安定）
                    llm_stability = (
                        self.results["llm"][llm]["std_first_token"]
                        / self.results["llm"][llm]["avg_first_token"]
                    )

                    # 総合スコアを計算（パフォーマンスと安定性を考慮）
                    # LLMスコア：パフォーマンスの重み（70％）+ 安定性の重み（30％）
                    llm_final_score = llm_score * 0.7 + llm_stability * 0.3

                    # 総スコア = LLMスコア（70％）+ TTSスコア（30％）+ STTスコア（30％）
                    total_score = (
                        llm_final_score * 0.7 + tts_score * 0.3 + stt_score * 0.3
                    )

                    self.results["combinations"].append(
                        {
                            "llm": llm,
                            "tts": tts,
                            "stt": stt,
                            "score": total_score,
                            "details": {
                                "llm_first_token": self.results["llm"][llm][
                                    "avg_first_token"
                                ],
                                "llm_stability": llm_stability,
                                "tts_time": self.results["tts"][tts]["avg_time"],
                                "stt_time": self.results["stt"][stt]["avg_time"],
                            },
                        }
                    )

        # スコアが小さい方が良い
        self.results["combinations"].sort(key=lambda x: x["score"])

    def _print_results(self):
        """テスト結果を出力"""
        llm_table = []
        for name, data in self.results["llm"].items():
            if data["errors"] == 0:
                stability = data["std_first_token"] / data["avg_first_token"]
                llm_table.append(
                    [
                        name,  # 幅を固定しない、tabulateが自動的に調整
                        f"{data['avg_first_token']:.3f}秒",
                        f"{data['avg_response']:.3f}秒",
                        f"{stability:.3f}",
                    ]
                )

        if llm_table:
            print("\nLLM パフォーマンスランキング:\n")
            print(
                tabulate(
                    llm_table,
                    headers=["モデル名", "最初のトークン時間", "総時間", "安定性"],
                    tablefmt="github",
                    colalign=("left", "right", "right", "right"),
                    disable_numparse=True,
                )
            )
        else:
            print("\n⚠️ テスト可能なLLMモジュールがありません。")

        tts_table = []
        for name, data in self.results["tts"].items():
            if data["errors"] == 0:
                tts_table.append([name, f"{data['avg_time']:.3f}秒"])  # 幅を固定しない

        if tts_table:
            print("\nTTS パフォーマンスランキング:\n")
            print(
                tabulate(
                    tts_table,
                    headers=["モデル名", "合成時間"],
                    tablefmt="github",
                    colalign=("left", "right"),
                    disable_numparse=True,
                )
            )
        else:
            print("\n⚠️ テスト可能なTTSモジュールがありません。")

        stt_table = []
        for name, data in self.results["stt"].items():
            if data["errors"] == 0:
                stt_table.append([name, f"{data['avg_time']:.3f}秒"])  # 幅を固定しない

        if stt_table:
            print("\nSTT パフォーマンスランキング:\n")
            print(
                tabulate(
                    stt_table,
                    headers=["モデル名", "合成時間"],
                    tablefmt="github",
                    colalign=("left", "right"),
                    disable_numparse=True,
                )
            )
        else:
            print("\n⚠️ テスト可能なSTTモジュールがありません。")

        if self.results["combinations"]:
            print("\n推奨設定の組み合わせ (スコアが小さい方が良い):\n")
            combo_table = []
            for combo in self.results["combinations"][:]:
                combo_table.append(
                    [
                        f"{combo['llm']} + {combo['tts']} + {combo['stt']}",  # 幅を固定しない
                        f"{combo['score']:.3f}",
                        f"{combo['details']['llm_first_token']:.3f}秒",
                        f"{combo['details']['llm_stability']:.3f}",
                        f"{combo['details']['tts_time']:.3f}秒",
                        f"{combo['details']['stt_time']:.3f}秒",
                    ]
                )

            print(
                tabulate(
                    combo_table,
                    headers=[
                        "組み合わせ",
                        "総合スコア",
                        "LLM最初のトークン時間",
                        "安定性",
                        "TTS合成時間",
                        "STT合成時間",
                    ],
                    tablefmt="github",
                    colalign=("left", "right", "right", "right", "right", "right"),
                    disable_numparse=True,
                )
            )
        else:
            print("\n⚠️ 推奨設定の組み合わせがありません。")

    def _process_results(self, all_results):
        """テスト結果を処理"""
        for result in all_results:
            if result["errors"] == 0:
                if result["type"] == "llm":
                    self.results["llm"][result["name"]] = result
                elif result["type"] == "tts":
                    self.results["tts"][result["name"]] = result
                elif result["type"] == "stt":
                    self.results["stt"][result["name"]] = result
                else:
                    pass

    async def run(self):
        """全量の非同期テストを実行"""
        print("🔍 利用可能なモジュールを検索しています...")

        # 全てのテストタスクを作成
        all_tasks = []

        # LLMテストタスク
        if self.config.get("LLM") is not None:
            for llm_name, config in self.config.get("LLM", {}).items():
                # 設定の有効性をチェック
                if llm_name == "CozeLLM":
                    if any(x in config.get("bot_id", "") for x in ["あなたの"]) or any(
                        x in config.get("user_id", "") for x in ["あなたの"]
                    ):
                        print(f"⏭️  LLM {llm_name} のbot_id/user_idが設定されていません。スキップします")
                        continue
                elif "api_key" in config and any(
                    x in config["api_key"] for x in ["あなたの", "placeholder", "sk-xxx"]
                ):
                    print(f"⏭️  LLM {llm_name} のAPIキーが設定されていません。スキップします")
                    continue

                # Ollamaの場合、サービスステータスをチェック
                if llm_name == "Ollama":
                    base_url = config.get("base_url", "http://localhost:11434")
                    model_name = config.get("model_name")
                    if not model_name:
                        print(f"🚫 Ollamaのモデル名が設定されていません")
                        continue

                    if not await self._check_ollama_service(base_url, model_name):
                        continue

                print(f"📋 LLMテストタスクを追加: {llm_name}")
                module_type = config.get("type", llm_name)
                llm = create_llm_instance(module_type, config)

                # 各文のテストタスクを作成
                for sentence in self.test_sentences:
                    sentence = sentence.encode("utf-8").decode("utf-8")
                    all_tasks.append(
                        self._test_single_sentence(llm_name, llm, sentence)
                    )

        # TTSテストタスク
        if self.config.get("TTS") is not None:
            for tts_name, config in self.config.get("TTS", {}).items():
                token_fields = ["access_token", "api_key", "token"]
                if any(
                    field in config
                    and any(x in config[field] for x in ["あなたの", "placeholder"])
                    for field in token_fields
                ):
                    print(f"⏭️  TTS {tts_name} のアクセストークン/アクセスキーが設定されていません。スキップします")
                    continue
                print(f"🎵 TTSテストタスクを追加: {tts_name}")
                all_tasks.append(self._test_tts(tts_name, config))

        # STTテストタスク
        if len(self.test_wav_list) >= 1:
            if self.config.get("ASR") is not None:
                for stt_name, config in self.config.get("ASR", {}).items():
                    token_fields = ["access_token", "api_key", "token"]
                    if any(
                        field in config
                        and any(x in config[field] for x in ["あなたの", "placeholder"])
                        for field in token_fields
                    ):
                        print(f"⏭️  ASR {stt_name} のアクセストークン/アクセスキーが設定されていません。スキップします")
                        continue
                    print(f"🎵 ASRテストタスクを追加: {stt_name}")
                    all_tasks.append(self._test_stt(stt_name, config))
        else:
            print(f"\n⚠️  {self.wav_root} パスに音声ファイルがありません。STTテストタスクをスキップします")

        print(
            f"\n✅ {len([t for t in all_tasks if 'test_single_sentence' in str(t)]) / len(self.test_sentences):.0f} 個の利用可能なLLMモジュールが見つかりました"
        )
        print(
            f"✅ {len([t for t in all_tasks if '_test_tts' in str(t)])} 個の利用可能なTTSモジュールが見つかりました"
        )
        print(
            f"✅ {len([t for t in all_tasks if '_test_stt' in str(t)])} 個の利用可能なSTTモジュールが見つかりました"
        )
        print("\n⏳ 全てのモジュールのテストを開始します...\n")

        # 全てのテストタスクを並行実行
        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # LLM結果を処理
        llm_results = {}
        for result in [
            r
            for r in all_results
            if r and isinstance(r, dict) and r.get("type") == "llm"
        ]:
            llm_name = result["name"]
            if llm_name not in llm_results:
                llm_results[llm_name] = {
                    "name": llm_name,
                    "type": "llm",
                    "first_token_times": [],
                    "response_times": [],
                    "errors": 0,
                }
            llm_results[llm_name]["first_token_times"].append(
                result["first_token_time"]
            )
            llm_results[llm_name]["response_times"].append(result["response_time"])

        # LLMの平均値と標準偏差を計算
        for llm_name, data in llm_results.items():
            if len(data["first_token_times"]) >= len(self.test_sentences) * 0.5:
                self.results["llm"][llm_name] = {
                    "name": llm_name,
                    "type": "llm",
                    "avg_response": sum(data["response_times"])
                    / len(data["response_times"]),
                    "avg_first_token": sum(data["first_token_times"])
                    / len(data["first_token_times"]),
                    "std_first_token": (
                        statistics.stdev(data["first_token_times"])
                        if len(data["first_token_times"]) > 1
                        else 0
                    ),
                    "std_response": (
                        statistics.stdev(data["response_times"])
                        if len(data["response_times"]) > 1
                        else 0
                    ),
                    "errors": 0,
                }

        # TTS結果を処理
        for result in [
            r
            for r in all_results
            if r and isinstance(r, dict) and r.get("type") == "tts"
        ]:
            if result["errors"] == 0:
                self.results["tts"][result["name"]] = result

        # STT結果を処理
        for result in [
            r
            for r in all_results
            if r and isinstance(r, dict) and r.get("type") == "stt"
        ]:
            if result["errors"] == 0:
                self.results["stt"][result["name"]] = result

        # 組み合わせを生成し、結果を出力
        print("\n📊 テストレポートを生成しています...")
        self._generate_combinations()
        self._print_results()


async def main():
    tester = AsyncPerformanceTester()
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
