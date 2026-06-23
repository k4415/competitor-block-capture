import unittest

from research_os.v2.schema import build_v2_research_database_specs


class ResearchV2SchemaTest(unittest.TestCase):
    def test_v2_databases_use_japanese_common_properties(self):
        specs = build_v2_research_database_specs("parent-page-id")
        titles = [spec.title for spec in specs]

        self.assertEqual(titles, ["カテゴリーリサーチ", "ターゲットリサーチ", "メインプレイヤーリサーチ", "競合比較サイトリサーチ"])
        for spec in specs:
            props = spec.request["initial_data_source"]["properties"]
            for name in ["事実", "大項目", "小項目", "セグメント", "根拠URL", "根拠タイトル", "短い引用", "信頼度", "検証状態", "取得日時", "リサーチRun ID"]:
                self.assertIn(name, props)

    def test_category_and_target_fixed_options_are_present(self):
        specs = {spec.key: spec for spec in build_v2_research_database_specs("parent-page-id")}

        category_options = {
            option["name"]
            for option in specs["category"].request["initial_data_source"]["properties"]["大項目"]["select"]["options"]
        }
        target_options = {
            option["name"]
            for option in specs["target"].request["initial_data_source"]["properties"]["大項目"]["select"]["options"]
        }
        segment_options = {
            option["name"]
            for option in specs["target"].request["initial_data_source"]["properties"]["セグメント"]["select"]["options"]
        }

        self.assertGreaterEqual(
            category_options,
            {
                "出会いの方法",
                "利用ステップ",
                "交際ルール",
                "成婚定義",
                "成婚期間",
                "料金・支払い",
                "カウンセラー体制",
                "連盟・会員基盤",
                "比較対象",
                "リスク・注意点",
                "サービス/商品の定義",
                "利用・購入ステップ",
                "料金体系",
                "主要プレイヤー",
                "意思決定基準",
                "法規制・広告表現制約",
                "カテゴリ固有項目",
            },
        )
        self.assertGreaterEqual(
            target_options,
            {"デモグラ", "婚活歴", "欲求", "状態", "懸念", "ビリーフ", "比較対象", "意思決定基準", "利用前状態", "購入/申込トリガー", "予算感", "不安解消条件"},
        )
        self.assertGreaterEqual(segment_options, {"20代男性", "30代男性", "20代女性", "30代女性", "20代", "30代", "40代", "50代以上", "男性", "女性", "共通"})


if __name__ == "__main__":
    unittest.main()
