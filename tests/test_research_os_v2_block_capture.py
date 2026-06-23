import argparse
import json
import tempfile
import unittest
from pathlib import Path

from research_os.cli import build_parser
from research_os.v2.block_finalize import finalize_block_capture
from research_os.v2.block_image_text import apply_image_text_prompts
from research_os.v2.block_capture import (
    CANDIDATE_SELECTOR_PARTS,
    RawBlockCandidate,
    _cap_synthetic_first_view,
    classify_candidate,
    select_semantic_blocks,
    safe_screenshot_clip,
    viewport_relative_screenshot_plan,
)
from research_os.v2.block_models import CapturedBlock
from research_os.v2.block_learning import (
    apply_approved_learning_rules,
    build_feedback_learning_payload,
)
from research_os.v2.block_notion import (
    block_page_children,
    block_page_properties,
    missing_block_database_schema_payload,
    required_block_database_properties,
)
from research_os.v2.block_prompting import analyze_blocks
from research_os.v2.block_reference_review import (
    apply_reference_review_to_blocks,
    load_reference_blocks_from_notion,
    review_blocks_against_references,
)


def _captured_block_for_review(
    *,
    order: int,
    selector: str,
    y: int,
    height: int,
    label: str,
    source_url: str = "https://example.com",
    domain: str = "example.com",
    run_id: str = "test-run",
    structure_memo: str = "",
) -> CapturedBlock:
    return CapturedBlock(
        name=f"block {order}",
        source_url=source_url,
        domain=domain,
        page_title="example",
        run_id=run_id,
        viewport="mobile-390",
        order=order,
        major_category="クロージング" if label == "CTA反復" else "ランキング",
        detail_label=label,
        screenshot_path="",
        structure_memo=structure_memo,
        image_prompt="",
        prompt_state="未生成",
        confidence="高",
        extracted_at="2026-06-22T00:00:00+00:00",
        clip={"x": 0, "y": y, "width": 390, "height": height},
        selector=selector,
        status="取得済み",
    )


def _rich_text_plain(prop: dict) -> str:
    return "".join(item.get("plain_text") or item.get("text", {}).get("content", "") for item in prop.get("rich_text", []))


def _child_plain_text(child: dict) -> str:
    child_type = child.get("type", "")
    rich_text = (child.get(child_type) or {}).get("rich_text") or []
    return "".join(item.get("plain_text") or item.get("text", {}).get("content", "") for item in rich_text)


class FakeImageTextClient:
    def __init__(self) -> None:
        self.calls: list[tuple[CapturedBlock, str]] = []

    def available(self) -> bool:
        return True

    def generate(self, block: CapturedBlock, *, category_name: str) -> dict[str, str]:
        self.calls.append((block, category_name))
        return {
            "image_text": json.dumps(
                {
                    "basic": {"aspectRatio": "1:1", "size": "1080x1080px"},
                    "globalDesign": {"style": "比較リスティング広告"},
                    "colorScheme": {"main": "#0066CC"},
                    "zones": [{"name": "Hero", "elements": [{"type": "text", "content": "スマイルモア矯正"}]}],
                    "reproduction": {"keyPoints": ["元画像に近い構図"]},
                },
                ensure_ascii=False,
            ),
            "Template_image_text": json.dumps(
                {
                    "basic": {"aspectRatio": "1:1", "size": "1080x1080px"},
                    "globalDesign": {"style": "比較リスティング広告"},
                    "colorScheme": {"main": "{メインカラー}"},
                    "zones": [{"name": "Hero", "elements": [{"type": "text", "content": "{サービス名}"}]}],
                    "reproduction": {"keyPoints": ["{ジャンル名}の比較素材として再利用できる構図"]},
                },
                ensure_ascii=False,
            ),
        }


class UnavailableImageTextClient(FakeImageTextClient):
    def available(self) -> bool:
        return False


class FakeBlockNotion:
    def __init__(self) -> None:
        self.created_pages: list[dict] = []
        self.uploaded_paths: list[str] = []

    def retrieve_database(self, database_id: str) -> dict:
        return {"data_sources": [{"id": "ds-test"}], "properties": {"名前": {"title": {}}}}

    def retrieve_data_source(self, data_source_id: str) -> dict:
        return {"properties": {"名前": {"title": {}}}}

    def update_data_source(self, data_source_id: str, payload: dict) -> dict:
        return {"id": data_source_id, **payload}

    def upload_file(self, file_path: str) -> str:
        self.uploaded_paths.append(str(file_path))
        return f"upload-{len(self.uploaded_paths)}"

    def create_page(self, data_source_id: str, properties: dict, children=None) -> dict:
        page_id = f"page-{len(self.created_pages) + 1}"
        self.created_pages.append({"id": page_id, "data_source_id": data_source_id, "properties": properties, "children": children or []})
        return {"id": page_id}


class BlockCaptureHeuristicsTest(unittest.TestCase):
    def test_safe_screenshot_clip_keeps_bottom_edge_inside_page(self):
        clip = safe_screenshot_clip({"x": 0, "y": 1336.4375, "width": 390, "height": 425}, page_height=1761, page_width=390)

        self.assertEqual(clip, {"x": 0, "y": 1336, "width": 389, "height": 416})

    def test_viewport_relative_screenshot_plan_scrolls_to_offscreen_clip(self):
        plan = viewport_relative_screenshot_plan({"x": 0, "y": 1268, "width": 389, "height": 691}, viewport_height=1200)

        self.assertEqual(plan.scroll_y, 1268)
        self.assertEqual(plan.clip, {"x": 0, "y": 0, "width": 389, "height": 691})

    def test_synthetic_first_view_does_not_swallow_following_comparison_section(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="2026年最新版 結婚相談所おすすめランキング TOP3 料金 会員数 無料相談",
                x=0,
                y=0,
                width=390,
                height=900,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.hero",
                tag="section",
                text="2026年最新版 結婚相談所おすすめランキング TOP3 料金 会員数 無料相談",
                x=0,
                y=0,
                width=390,
                height=585,
                class_name="hero",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.compare",
                tag="section",
                text="一括比較表 サービス 料金 会員数 CTA ツヴァイ 月額 多数 公式サイト",
                x=0,
                y=585,
                width=390,
                height=230,
                class_name="compare",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/ranking/",
            page_title="Example Ranking",
            category_name="結婚相談所",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual([block.detail_label for block in blocks], ["ファーストビュー結論", "一括比較表"])
        self.assertEqual(blocks[0].selector, "main > section.hero")

    def test_select_semantic_blocks_keeps_meaningful_chunks_and_drops_nested_rows(self):
        candidates = [
            RawBlockCandidate(
                selector="main > section.hero",
                tag="section",
                text="2026年最新版 結婚相談所おすすめランキング TOP3 料金 会員数 無料相談",
                x=0,
                y=0,
                width=390,
                height=620,
                class_name="hero fv",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.compare table",
                tag="table",
                text="料金 会員数 サポート 出会い方 店舗数 公式サイト 一括比較表",
                x=12,
                y=760,
                width=366,
                height=720,
                class_name="comparison-table",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.compare table tr:nth-child(2)",
                tag="tr",
                text="ツヴァイ 料金 会員数 サポート 公式サイト",
                x=12,
                y=840,
                width=366,
                height=96,
                class_name="",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.ranking",
                tag="section",
                text="ランキング 1位 ツヴァイ 2位 サンマリエ 3位 フィオーレ 詳細を見る 公式サイト",
                x=0,
                y=1560,
                width=390,
                height=850,
                class_name="ranking cards",
                element_id="rank",
            ),
            RawBlockCandidate(
                selector="main > section.faq",
                tag="section",
                text="よくある質問 Q&A 費用は？ 無料相談だけでもよい？",
                x=0,
                y=2520,
                width=390,
                height=480,
                class_name="faq accordion",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.final-cta",
                tag="section",
                text="迷ったらここ 無料相談 公式サイト 今すぐ予約",
                x=0,
                y=3080,
                width=390,
                height=420,
                class_name="cta",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/ranking/",
            page_title="Example Ranking",
            category_name="結婚相談所",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual([block.detail_label for block in blocks], ["ファーストビュー結論", "一括比較表", "ランキング本文", "FAQ/Q&A", "CTA反復"])
        self.assertEqual([block.major_category for block in blocks], ["ファーストビュー", "比較表", "ランキング", "行動前不安解消", "クロージング"])
        self.assertNotIn("tr:nth-child", "\n".join(block.selector for block in blocks))

    def test_select_semantic_blocks_merges_comparison_heading_table_and_cta(self):
        candidates = [
            RawBlockCandidate(
                selector="main > section.hero",
                tag="section",
                text="2026年最新版 マウスピース矯正 おすすめ 人気ブランド 無料診断",
                x=0,
                y=0,
                width=390,
                height=420,
                class_name="hero fv",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > h2.compare-title",
                tag="h2",
                text="マウスピース矯正 人気ブランド 徹底比較",
                x=0,
                y=455,
                width=390,
                height=92,
                class_name="compare-title",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.compare-table",
                tag="section",
                text="スマイルモア矯正 ウィスマイル キレイライン矯正 矯正費用 初診料 再診料 治療期間 提携院数",
                x=10,
                y=552,
                width=370,
                height=650,
                class_name="compare-table",
                element_id="",
            ),
            RawBlockCandidate(
                selector="main > section.compare-cta",
                tag="section",
                text="公式サイトはこちら 公式サイトはこちら 公式サイトはこちら",
                x=10,
                y=1188,
                width=370,
                height=110,
                class_name="compare-cta cta",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual([block.detail_label for block in blocks], ["ファーストビュー結論", "一括比較表"])
        self.assertEqual(blocks[1].clip, {"x": 0, "y": 455, "width": 390, "height": 843})
        self.assertNotIn("CTA反復", [block.detail_label for block in blocks])

    def test_select_semantic_blocks_caps_synthetic_first_view_before_next_full_width_section(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="2026年最新版 マウスピース矯正 5選 人気ブランド 徹底比較",
                x=0,
                y=0,
                width=390,
                height=900,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#top3",
                tag="section",
                text="マウスピース矯正 人気ブランド 徹底比較 矯正費用 初診料 再診料 公式サイトはこちら",
                x=0,
                y=317,
                width=390,
                height=951,
                class_name="",
                element_id="top3",
            ),
            RawBlockCandidate(
                selector="body > section#top3 > table",
                tag="table",
                text="矯正費用 初診料 再診料 治療期間 提携院数 公式サイトはこちら",
                x=10,
                y=407,
                width=370,
                height=841,
                class_name="",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual([block.detail_label for block in blocks], ["ファーストビュー結論", "一括比較表"])
        self.assertEqual(blocks[0].clip, {"x": 0, "y": 0, "width": 390, "height": 317})
        self.assertEqual(blocks[1].selector, "body > section#top3")

    def test_select_semantic_blocks_drops_near_identical_nested_comparison_blocks(self):
        candidates = [
            RawBlockCandidate(
                selector="body > section#hikaku",
                tag="section",
                text="スクロールできます スマイルモア矯正 ウィスマイル キレイライン矯正 矯正費用 初診料 再診料 治療期間 提携院数",
                x=0,
                y=5000,
                width=390,
                height=932,
                class_name="p-hikaku",
                element_id="hikaku",
            ),
            RawBlockCandidate(
                selector="body > section#hikaku > div",
                tag="div",
                text="スクロールできます スマイルモア矯正 ウィスマイル キレイライン矯正 矯正費用 初診料 再診料 治療期間 提携院数",
                x=0,
                y=5000,
                width=390,
                height=932,
                class_name="",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#hikaku > div > div:nth-of-type(1)",
                tag="div",
                text="スマイルモア矯正 ウィスマイル キレイライン矯正 矯正費用 初診料 再診料 治療期間 提携院数",
                x=12,
                y=5000,
                width=378,
                height=736,
                class_name="",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#hikaku > div > div:nth-of-type(2) > div",
                tag="div",
                text="ブランドを比較する際は2つ以上のブランドのカウンセリングを受けてみましょう",
                x=102,
                y=5762,
                width=261,
                height=99,
                class_name="",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual([block.selector for block in blocks], ["body > section#hikaku"])

    def test_select_semantic_blocks_prefers_ranking_cards_over_oversized_ranking_parent(self):
        candidates = [
            RawBlockCandidate(
                selector="body > section#ranking",
                tag="section",
                text="ランキング スマイルモア矯正 ウィスマイル キレイライン矯正 基本情報 料金プラン 費用目安",
                x=0,
                y=6000,
                width=390,
                height=7400,
                class_name="p-ranking",
                element_id="ranking",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1)",
                tag="li",
                text="スマイルモア矯正 基本情報 料金プラン 費用目安 3,000円/月 症例 口コミ 公式サイト",
                x=10,
                y=6080,
                width=370,
                height=1800,
                class_name="ranking-card",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(2)",
                tag="li",
                text="ウィスマイル 基本情報 料金プラン 費用目安 3,000円/月 症例 口コミ 公式サイト",
                x=10,
                y=7900,
                width=370,
                height=1600,
                class_name="ranking-card",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(2) > div:nth-of-type(2)",
                tag="div",
                text="ウィスマイル 基本情報 料金プラン 費用目安 3,000円/月 症例 口コミ 公式サイト",
                x=10,
                y=7970,
                width=370,
                height=1400,
                class_name="ranking-card-inner",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual(
            [block.selector for block in blocks],
            [
                "body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1)",
                "body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(2)",
            ],
        )
        self.assertEqual([block.major_category for block in blocks], ["ランキング", "ランキング"])

    def test_classify_first_view_with_case_text_still_first_view(self):
        candidate = RawBlockCandidate(
            selector="body::first-view",
            tag="section",
            text="2026年 最新版 マウスピース矯正おすすめランキング 症例 Before After 期間 2ヶ月 総額 18.7万円 治療内容 無料相談",
            x=0,
            y=0,
            width=390,
            height=317,
            class_name="first-view",
            element_id="",
        )

        classification = classify_candidate(candidate, order=1)

        self.assertEqual(classification.major_category, "ファーストビュー")
        self.assertEqual(classification.detail_label, "ファーストビュー結論")

    def test_candidate_selectors_include_wordpress_article_blocks(self):
        self.assertIn("main#main_content > div > div > figure", CANDIDATE_SELECTOR_PARTS)
        self.assertIn("main#main_content > div > div > div.wp-block-sbd-checkpoint-block", CANDIDATE_SELECTOR_PARTS)

    def test_select_semantic_blocks_promotes_wordpress_figure_nested_in_first_view(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="最新版 東京で最も信頼できるマウスピース矯正おすすめランキングTOP5 無料相談",
                x=0,
                y=0,
                width=390,
                height=900,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(1)",
                tag="figure",
                text="東京で最も信頼できるマウスピース矯正TOP5",
                x=16,
                y=89,
                width=359,
                height=231,
                class_name="wp-block-image size-full",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(15)",
                tag="figure",
                text="第1位 第2位 第3位 第4位 第5位 総合評価 97点 クリニック数 治療期間 費用 公式サイト",
                x=16,
                y=5768,
                width=359,
                height=1016,
                class_name="wp-block-table wp-block-sbd-table",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > div:nth-of-type(2)",
                tag="div",
                text="スマイルモア矯正の特徴 最も信頼できるマウスピース矯正No.1 治療実績 インビザライン 痛みが少ない 総額18.7万円",
                x=16,
                y=7503,
                width=359,
                height=280,
                class_name="wp-block-sbd-checkpoint-block",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual(
            [block.selector for block in blocks],
            [
                "body > main#main_content > div > div > figure:nth-of-type(1)",
                "body > main#main_content > div > div > figure:nth-of-type(15)",
                "body > main#main_content > div > div > div:nth-of-type(2)",
            ],
        )
        self.assertEqual("ファーストビュー結論", blocks[0].detail_label)

    def test_select_semantic_blocks_keeps_per_item_comparison_cards_separate(self):
        candidates = [
            RawBlockCandidate(
                selector="body > div#block_first",
                tag="div",
                text="料金プラン マウスピース種類 医院数 スマイルモア矯正 初診料0円 月額3,000円 178医院",
                x=16,
                y=444,
                width=358,
                height=377,
                class_name="hikaku_table margin-bottom--35",
                element_id="block_first",
            ),
            RawBlockCandidate(
                selector="body > div#block_first > table",
                tag="table",
                text="料金プラン マウスピース種類 医院数 スマイルモア矯正 初診料0円 月額3,000円 178医院",
                x=23,
                y=444,
                width=344,
                height=316,
                class_name="",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#block_second",
                tag="div",
                text="料金プラン マウスピース種類 医院数 ウィスマイル 初診料0円 月額3,000円 153医院",
                x=16,
                y=777,
                width=358,
                height=397,
                class_name="hikaku_table margin-bottom--35",
                element_id="block_second",
            ),
            RawBlockCandidate(
                selector="body > div#block_third",
                tag="div",
                text="料金プラン マウスピース種類 医院数 キレイライン矯正 初診料0円 月額3,100円 130医院",
                x=16,
                y=1128,
                width=358,
                height=364,
                class_name="hikaku_table margin-bottom--35",
                element_id="block_third",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual(
            [block.selector for block in blocks],
            ["body > div#block_first", "body > div#block_second", "body > div#block_third"],
        )
        self.assertEqual([block.major_category for block in blocks], ["ランキング", "ランキング", "ランキング"])
        self.assertEqual(blocks[0].clip["height"], 316)

    def test_select_semantic_blocks_classifies_single_product_detail_tables_as_product_details(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="マウスピース矯正5選",
                x=0,
                y=0,
                width=390,
                height=320,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="hybrid::comparison",
                tag="section",
                text="料金プラン 月額3,000円 メーカー保証 世界最大メーカー 矯正範囲 1-3カ月 実績 178医院 エリア 北海道 東京 神奈川",
                x=0,
                y=8600,
                width=390,
                height=610,
                class_name="hybrid-visual-block hikaku_table",
                element_id="",
            ),
            RawBlockCandidate(
                selector="hybrid::comparison",
                tag="section",
                text="料金プラン 月額3,000円 メーカー保証 世界3大メーカー 矯正範囲 2-3カ月 実績 153医院 エリア 北海道 東京 神奈川",
                x=0,
                y=13400,
                width=390,
                height=590,
                class_name="hybrid-visual-block hikaku_table",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://good-choice.net/orthodontics/a/1311115448",
            page_title="マウスピース矯正",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        product_blocks = [block for block in blocks if block.detail_label == "個別候補の詳細比較"]
        self.assertEqual(["個別候補詳細", "個別候補詳細"], [block.major_category for block in product_blocks])
        self.assertEqual(["個別候補の詳細比較", "個別候補の詳細比較"], [block.detail_label for block in product_blocks])

    def test_select_semantic_blocks_classifies_wordpress_multi_product_table_as_comparison(self):
        candidates = [
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(15)",
                tag="figure",
                text="第1位 第2位 第3位 第4位 第5位 マウスピース矯正 スマイルモア矯正 キレイライン矯正 ウィスマイル矯正 Oh my teeth 総合評価 97点/100 クリニック数 治療期間 費用 公式サイト",
                x=16,
                y=5768,
                width=359,
                height=1016,
                class_name="wp-block-table wp-block-sbd-table",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual("比較表", blocks[0].major_category)
        self.assertEqual("一括比較表", blocks[0].detail_label)

    def test_select_semantic_blocks_keeps_visual_children_when_selector_is_not_descendant_of_oversized_parent(self):
        candidates = [
            RawBlockCandidate(
                selector="body > article#post-5448",
                tag="article",
                text="料金プラン マウスピース種類 医院数 メーカー保証 矯正範囲 実績 エリア " * 20,
                x=16,
                y=324,
                width=358,
                height=20320,
                class_name="article",
                element_id="post-5448",
            ),
            RawBlockCandidate(
                selector="body > div#block_first",
                tag="div",
                text="料金プラン マウスピース種類 医院数 スマイルモア矯正 初診料0円 月額3,000円 178医院",
                x=16,
                y=444,
                width=358,
                height=377,
                class_name="hikaku_table margin-bottom--35",
                element_id="block_first",
            ),
            RawBlockCandidate(
                selector="body > div#block_second",
                tag="div",
                text="料金プラン マウスピース種類 医院数 ウィスマイル 初診料0円 月額3,000円 153医院",
                x=16,
                y=777,
                width=358,
                height=397,
                class_name="hikaku_table margin-bottom--35",
                element_id="block_second",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://good-choice.net/orthodontics/a/1311115448",
            page_title="マウスピース矯正",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(["body > div#block_first", "body > div#block_second"], [block.selector for block in blocks])

    def test_select_semantic_blocks_keeps_merged_visual_children_inside_oversized_parent(self):
        candidates = [
            RawBlockCandidate(
                selector="body > article#post-5448",
                tag="article",
                text="料金プラン マウスピース種類 医院数 メーカー保証 矯正範囲 実績 エリア " * 20,
                x=16,
                y=324,
                width=358,
                height=20320,
                class_name="article",
                element_id="post-5448",
            ),
            RawBlockCandidate(
                selector="hybrid::comparison",
                tag="section",
                text="料金プラン 月額3,000円 メーカー信頼性 世界4大メーカー 矯正範囲 部分矯正 実績 11万人 医院数 178医院 エリア 北海道 東京",
                x=16,
                y=8650,
                width=358,
                height=610,
                class_name="hybrid-visual-block",
                element_id="",
            ),
            RawBlockCandidate(
                selector="hybrid::comparison",
                tag="section",
                text="料金プラン 月額3,100円 メーカー信頼性 独自開発 矯正範囲 部分矯正 実績 12万人 医院数 130医院 エリア 北海道 東京",
                x=16,
                y=16018,
                width=358,
                height=610,
                class_name="hybrid-visual-block",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://good-choice.net/orthodontics/a/1311115448",
            page_title="マウスピース矯正",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(["hybrid::comparison", "hybrid::comparison"], [block.selector for block in blocks])

    def test_select_semantic_blocks_drops_later_near_duplicate_visual_overlap(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="いびき治療クリニック",
                x=0,
                y=0,
                width=390,
                height=420,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#voice > div > ul",
                tag="ul",
                text="1位 スリープメディカルクリニック 2位 いびきのクリニック 3位 ビナースクリニック",
                x=0,
                y=435,
                width=390,
                height=708,
                class_name="ranking-list",
                element_id="",
            ),
            RawBlockCandidate(
                selector="hybrid::comparison",
                tag="section",
                text="1位 スリープメディカルクリニック 2位 いびきのクリニック 3位 ビナースクリニック",
                x=0,
                y=501,
                width=390,
                height=612,
                class_name="hybrid-visual-block comparison",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://ibiki-hikaku.com/r/",
            page_title="いびき比較",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        selectors = [block.selector for block in blocks]
        self.assertIn("body > div#voice > div > ul", selectors)
        self.assertNotIn("hybrid::comparison", selectors)

    def test_synthetic_first_view_stops_before_narrow_top_ranking_section(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="いびき治療なら スリープメディカルクリニック TOP3",
                x=0,
                y=0,
                width=390,
                height=900,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#voice > div > ul",
                tag="ul",
                text="いびき治療クリニック TOP3 1位 スリープメディカルクリニック 2位 いびきのクリニック",
                x=30,
                y=435,
                width=330,
                height=708,
                class_name="voice ranking",
                element_id="",
            ),
        ]

        capped = _cap_synthetic_first_view(candidates)

        first_view = next(candidate for candidate in capped if candidate.selector == "body::first-view")
        self.assertEqual(435, first_view.height)

    def test_select_semantic_blocks_merges_tiny_rank_cta_into_previous_detail_block(self):
        candidates = [
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div.recommendation",
                tag="div",
                text="おすすめポイント 初回トライアルが安い レーザー治療 専門クリニック",
                x=0,
                y=3000,
                width=390,
                height=520,
                class_name="recommendation",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > p.btn",
                tag="p",
                text="スリープメディカルクリニックの公式サイトをチェック",
                x=0,
                y=3560,
                width=390,
                height=74,
                class_name="btn",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://ibiki-hikaku.com/r/",
            page_title="いびき比較",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(1, len(blocks))
        self.assertEqual(634, blocks[0].clip["height"])
        self.assertEqual("おすすめポイント要約", blocks[0].detail_label)

    def test_select_semantic_blocks_merges_multiple_tiny_rank_ctas_into_previous_detail_block(self):
        candidates = [
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div.recommendation",
                tag="div",
                text="おすすめポイント 初回トライアルが安い レーザー治療 専門クリニック",
                x=0,
                y=3000,
                width=390,
                height=520,
                class_name="recommendation",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > p.btn:nth-of-type(1)",
                tag="p",
                text="スリープメディカルクリニックの公式サイトをチェック",
                x=0,
                y=3560,
                width=390,
                height=74,
                class_name="btn",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > p.btn:nth-of-type(2)",
                tag="p",
                text="リアルタイムの空き枠を確認する",
                x=0,
                y=3650,
                width=390,
                height=58,
                class_name="btn",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://ibiki-hikaku.com/r/",
            page_title="いびき比較",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(1, len(blocks))
        self.assertEqual(708, blocks[0].clip["height"])

    def test_select_semantic_blocks_groups_wordpress_article_figure_and_text_run(self):
        candidates = [
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(15)",
                tag="figure",
                text="スマイルモア矯正 170,000人が選んだ マウスピース矯正",
                x=0,
                y=7102,
                width=390,
                height=384,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > div:nth-of-type(2)",
                tag="div",
                text="スマイルモア矯正の特徴 月額3,000円 目立ちにくい 治療期間が短い",
                x=0,
                y=7502,
                width=390,
                height=280,
                class_name="wp-block-sbd-checkpoint-block",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(17)",
                tag="figure",
                text="スマイルモア矯正を受けた人の98.3%が満足",
                x=0,
                y=7806,
                width=390,
                height=88,
                class_name="wp-block-image",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual("個別候補詳細", blocks[0].major_category)
        self.assertEqual("個別候補の基本情報", blocks[0].detail_label)
        self.assertEqual(680, blocks[0].clip["height"])
        self.assertEqual(88, blocks[1].clip["height"])

    def test_select_semantic_blocks_groups_wordpress_explainer_image_run_with_medium_gaps(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="東京で信頼できるマウスピース矯正TOP5",
                x=0,
                y=0,
                width=390,
                height=900,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(3)",
                tag="figure",
                text="<img src='choice-1.png'>",
                x=16,
                y=673,
                width=359,
                height=320,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(4)",
                tag="figure",
                text="<img src='choice-2.png'>",
                x=16,
                y=1386,
                width=359,
                height=116,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(5)",
                tag="figure",
                text="<img src='choice-3.png'>",
                x=16,
                y=1502,
                width=359,
                height=253,
                class_name="wp-block-image",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(["ファーストビュー結論", "選び方3〜5ポイント"], [block.detail_label for block in blocks])
        self.assertEqual(673, blocks[0].clip["height"])
        self.assertEqual(1082, blocks[1].clip["height"])

    def test_select_semantic_blocks_prefers_nested_wordpress_hero_image_as_first_view(self):
        candidates = [
            RawBlockCandidate(
                selector="body::first-view",
                tag="section",
                text="東京で信頼できるマウスピース矯正TOP5",
                x=0,
                y=0,
                width=390,
                height=673,
                class_name="first-view",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(1)",
                tag="figure",
                text="<img src='hero.png'>",
                x=16,
                y=89,
                width=359,
                height=231,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(3)",
                tag="figure",
                text="<img src='choice-1.png'>",
                x=16,
                y=673,
                width=359,
                height=320,
                class_name="wp-block-image",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(
            [
                "body > main#main_content > div > div > figure:nth-of-type(1)",
                "body > main#main_content > div > div > figure:nth-of-type(3)",
            ],
            [block.selector for block in blocks],
        )
        self.assertEqual("ファーストビュー結論", blocks[0].detail_label)
        self.assertEqual({"x": 16, "y": 89, "width": 359, "height": 231}, blocks[0].clip)

    def test_select_semantic_blocks_splits_wordpress_offer_before_product_feature_card(self):
        candidates = [
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(24)",
                tag="figure",
                text="<img src='offer-ending.png'>",
                x=16,
                y=12351,
                width=359,
                height=357,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(25)",
                tag="figure",
                text="<img src='kireiline-main.png'>",
                x=16,
                y=12813,
                width=359,
                height=377,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > div:nth-of-type(5)",
                tag="div",
                text="キレイライン矯正の特徴 業界大手のマウスピース矯正ブランド 豊富な症例 10回コース",
                x=16,
                y=13221,
                width=359,
                height=280,
                class_name="wp-block-sbd-checkpoint-block",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual("body > main#main_content > div > div > figure:nth-of-type(24)", blocks[0].selector)
        self.assertEqual("個別候補の基本情報", blocks[1].detail_label)
        self.assertEqual(688, blocks[1].clip["height"])

    def test_select_semantic_blocks_splits_product_feature_from_following_evidence_images(self):
        candidates = [
            RawBlockCandidate(
                selector="body > figure#smilemore",
                tag="figure",
                text="<img src='smilemore-main.png'>",
                x=16,
                y=7103,
                width=359,
                height=384,
                class_name="wp-block-image",
                element_id="smilemore",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > div:nth-of-type(2)",
                tag="div",
                text="スマイルモア矯正の特徴 最も信頼できるマウスピース矯正No.1 170,000人以上 治療実績 インビザライン 総額18.7万円",
                x=16,
                y=7503,
                width=359,
                height=280,
                class_name="wp-block-sbd-checkpoint-block",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(17)",
                tag="figure",
                text="<img src='satisfaction-heading.png'>",
                x=16,
                y=7806,
                width=359,
                height=89,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(18)",
                tag="figure",
                text="<img src='satisfaction-chart.png'>",
                x=16,
                y=7895,
                width=359,
                height=280,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(19)",
                tag="figure",
                text="<img src='reviews.png'>",
                x=16,
                y=8176,
                width=359,
                height=271,
                class_name="wp-block-image",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual("個別候補の基本情報", blocks[0].detail_label)
        self.assertEqual(680, blocks[0].clip["height"])
        self.assertEqual("口コミ/体験談", blocks[1].detail_label)
        self.assertEqual(641, blocks[1].clip["height"])

    def test_select_semantic_blocks_caps_long_wordpress_image_run(self):
        candidates = [
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(3)",
                tag="figure",
                text="<img src='choice-overview.png'>",
                x=16,
                y=673,
                width=359,
                height=320,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(4)",
                tag="figure",
                text="<img src='choice-1-heading.png'>",
                x=16,
                y=1386,
                width=359,
                height=116,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(5)",
                tag="figure",
                text="<img src='choice-1-body.png'>",
                x=16,
                y=1503,
                width=359,
                height=253,
                class_name="wp-block-image",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > main#main_content > div > div > figure:nth-of-type(6)",
                tag="figure",
                text="<img src='choice-2-heading.png'>",
                x=16,
                y=1803,
                width=359,
                height=111,
                class_name="wp-block-image",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://mouthpiece-best.com/mouthpiece-tokyo-2/",
            page_title="マウスピース東京",
            category_name="比較リスティング",
            run_id="test-run",
            candidates=candidates,
            screenshot_dir=Path("tmp"),
            max_blocks=10,
        )

        self.assertEqual(2, len(blocks))
        self.assertEqual(1083, blocks[0].clip["height"])
        self.assertEqual("body > main#main_content > div > div > figure:nth-of-type(6)", blocks[1].selector)

    def test_select_semantic_blocks_splits_ibiki_ranking_card(self):
        candidates = [
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1)",
                tag="li",
                text="スリープメディカルクリニック 初回お試し 通常価格 口コミ おすすめポイント 症例 口コミ キャンペーン 店舗一覧 公式サイト",
                x=0,
                y=2434,
                width=360,
                height=4408,
                class_name="rank01 container",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > table",
                tag="table",
                text="初回お試し 通常価格 口コミ 21,780円 99,000円 Google4.6点 治療法 麻酔・痛み 診療時間",
                x=15,
                y=2722,
                width=330,
                height=308,
                class_name="",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div:nth-of-type(1)",
                tag="div",
                text="おすすめポイント いびきのレーザー治療といえばココ 初回トライアルが78%OFF 独自開発の最新治療法",
                x=15,
                y=3077,
                width=330,
                height=850,
                class_name="recommendation",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > section",
                tag="section",
                text="スリープメディカルクリニックの症例 年齢 性別 治療内容 スノアレーズ 治療による変化 Before After",
                x=15,
                y=4178,
                width=330,
                height=669,
                class_name="case-section",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div:nth-of-type(2)",
                tag="div",
                text="スリープメディカルクリニックの口コミ ★★★★★5.0 通いやすい 丁寧な対応 いびき治療を受けた",
                x=15,
                y=4896,
                width=330,
                height=751,
                class_name="reviews",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div:nth-of-type(3)",
                tag="div",
                text="【初めての方限定】 通常99,000円が初回トライアル価格21,780円で試せる",
                x=15,
                y=5712,
                width=330,
                height=561,
                class_name="campaign",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > p:nth-of-type(7)",
                tag="p",
                text="スリープメディカルクリニックの 公式サイトをチェック",
                x=15,
                y=6331,
                width=330,
                height=75,
                class_name="btn",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > div#rank_box > ul > li:nth-of-type(1) > div:nth-of-type(4)",
                tag="div",
                text="スリープメディカルクリニックの店舗一覧 関東 新宿院 渋谷院 銀座院 横浜院 中部 関西 九州",
                x=15,
                y=6591,
                width=330,
                height=222,
                class_name="store-locations",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/snore/",
            page_title="Example Snore",
            category_name="いびき治療",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=20,
        )

        self.assertEqual(
            [block.detail_label for block in blocks],
            [
                "個別候補の基本情報",
                "おすすめポイント要約",
                "効果/症例/Before After",
                "口コミ/体験談",
                "限定オファー",
                "店舗/地域一覧",
            ],
        )
        self.assertNotIn("body > div#rank_box > ul > li:nth-of-type(1)", [block.selector for block in blocks])

    def test_select_semantic_blocks_splits_ranking_card_into_inner_meaning_blocks(self):
        candidates = [
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1)",
                tag="li",
                text="スマイルモア矯正 基本情報 料金プラン 費用目安 症例 対応している歯並び おすすめポイント 近くのクリニック",
                x=10,
                y=6080,
                width=370,
                height=2750,
                class_name="ranking-card",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div:nth-of-type(2)",
                tag="div",
                text="基本情報 料金プラン 費用目安 3,000円/月 症 例 症例1 症例2 期間 2ヶ月 総額 18.7万円 対応している歯並び おすすめポイント",
                x=10,
                y=6147,
                width=370,
                height=1965,
                class_name="p-ranking-main-container-item__main",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div.main > div.wrap",
                tag="div",
                text="基本情報 料金プラン 費用目安 3,000円/月 初診料 0円 再診料 0円 治療期間 3ヶ月 提携院数 176院",
                x=26,
                y=6380,
                width=338,
                height=378,
                class_name="wrap",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div.main > dl.case",
                tag="dl",
                text="症 例 症例1 症例2 症例3 症例4 期間 2ヶ月 総額 18.7万円 Before After 治療内容",
                x=26,
                y=6788,
                width=338,
                height=753,
                class_name="case",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div.main > div.check",
                tag="div",
                text="対応している歯並び #すきっ歯 #受け口 #八重歯・ガタガタ #出っ歯 #中心のずれ",
                x=26,
                y=7571,
                width=338,
                height=166,
                class_name="check",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div.main > dl.point",
                tag="dl",
                text="おすすめポイント カウンセリング満足度98.3% 総額18.7万円 コスパ 医療ホワイトニング剤をプレゼント",
                x=26,
                y=7767,
                width=338,
                height=328,
                class_name="point",
                element_id="",
            ),
            RawBlockCandidate(
                selector="body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div.location",
                tag="div",
                text="近くのクリニックを探す 関東 関西 北海道・東北 中部 中国・四国 九州・沖縄",
                x=10,
                y=8282,
                width=370,
                height=360,
                class_name="p-ranking-main-container-item__location",
                element_id="",
            ),
        ]

        blocks = select_semantic_blocks(
            url="https://example.com/mouthpiece/",
            page_title="Example Mouthpiece",
            category_name="マウスピース矯正",
            run_id="run-test",
            candidates=candidates,
            screenshot_dir=Path("artifacts/test"),
            max_blocks=10,
        )

        self.assertEqual(
            [block.detail_label for block in blocks],
            [
                "個別候補の基本情報",
                "効果/症例/Before After",
                "向いている人/向かない人",
                "おすすめポイント要約",
                "店舗/地域一覧",
            ],
        )
        self.assertNotIn("body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1)", [block.selector for block in blocks])
        self.assertNotIn("body > section#ranking > div > div:nth-of-type(2) > ul > li:nth-of-type(1) > div:nth-of-type(2)", [block.selector for block in blocks])

    def test_review_captured_blocks_warns_on_large_non_fv_overlap(self):
        from research_os.v2.block_capture import review_captured_blocks

        blocks = [
            _captured_block_for_review(order=1, selector="body > a", y=400, height=500, label="ランキング本文"),
            _captured_block_for_review(order=2, selector="body > b", y=450, height=450, label="価格体系の基礎解説"),
        ]

        warnings = review_captured_blocks(blocks)

        self.assertTrue(any("overlap" in warning for warning in warnings))

    def test_review_captured_blocks_warns_on_many_tiny_ctas(self):
        from research_os.v2.block_capture import review_captured_blocks

        blocks = [
            _captured_block_for_review(order=1, selector="body > a", y=1000, height=60, label="CTA反復"),
            _captured_block_for_review(order=2, selector="body > b", y=1100, height=58, label="CTA反復"),
            _captured_block_for_review(order=3, selector="body > c", y=1200, height=74, label="CTA反復"),
        ]

        warnings = review_captured_blocks(blocks)

        self.assertTrue(any("tiny CTA" in warning for warning in warnings))

    def test_review_captured_blocks_ignores_cross_url_visual_overlap(self):
        from research_os.v2.block_capture import review_captured_blocks

        first = _captured_block_for_review(order=1, selector="body > a", y=400, height=500, label="ランキング本文")
        second = _captured_block_for_review(order=1, selector="body > b", y=400, height=500, label="ランキング本文")
        second = CapturedBlock(**{**second.to_dict(), "source_url": "https://other.example.com", "domain": "other.example.com"})

        warnings = review_captured_blocks([first, second])

        self.assertEqual([], warnings)


class BlockReferenceReviewTest(unittest.TestCase):
    def test_load_reference_blocks_from_notion_queries_existing_database(self):
        class FakeNotion:
            def __init__(self):
                self.queries = []

            def retrieve_database(self, database_id):
                self.database_id = database_id
                return {"data_sources": [{"id": "ds-test"}]}

            def query_data_source(self, data_source_id, payload):
                self.queries.append((data_source_id, payload))
                return {
                    "results": [
                        {
                            "id": "page-test",
                            "properties": {
                                "名前": {"title": [{"plain_text": "マウスピース矯正 example.com 001 ファーストビュー結論"}]},
                                "元URL": {"url": "https://example.com/r/"},
                                "ドメイン": {"rich_text": [{"plain_text": "example.com"}]},
                                "ページタイトル": {"rich_text": [{"plain_text": "Example"}]},
                                "Run ID": {"rich_text": [{"plain_text": "ref-run"}]},
                                "表示幅": {"select": {"name": "mobile-390"}},
                                "ブロック順": {"number": 1},
                                "ブロック大分類": {"select": {"name": "ファーストビュー"}},
                                "詳細ラベル": {"select": {"name": "ファーストビュー結論"}},
                                "構造メモ": {"rich_text": [{"plain_text": "hero"}]},
                                "画像生成プロンプト": {"rich_text": []},
                                "プロンプト状態": {"select": {"name": "未生成"}},
                                "信頼度": {"select": {"name": "高"}},
                                "抽出日時": {"date": {"start": "2026-06-23T00:00:00+00:00"}},
                                "スクショ範囲": {"rich_text": [{"plain_text": '{"x":0,"y":0,"width":390,"height":400}'}]},
                                "ステータス": {"select": {"name": "取得済み"}},
                            },
                        }
                    ],
                    "has_more": False,
                }

        notion = FakeNotion()

        blocks = load_reference_blocks_from_notion(
            notion=notion,
            database_id="db-test",
            urls=["https://example.com/r/"],
            category_name="マウスピース矯正",
            viewport="mobile-390",
        )

        self.assertEqual(notion.database_id, "db-test")
        self.assertTrue(notion.queries)
        self.assertEqual(blocks[0].source_url, "https://example.com/r/")
        self.assertEqual(blocks[0].run_id, "ref-run")
        self.assertEqual(blocks[0].clip["height"], 400.0)

    def test_reference_review_reports_no_reference_when_database_is_empty(self):
        current = [_captured_block_for_review(order=1, selector="body > a", y=0, height=400, label="ファーストビュー結論")]

        review = review_blocks_against_references(current, [], category_name="結婚相談所")

        self.assertEqual(review.status, "no_reference")
        self.assertEqual(review.reference_strength, "none")
        self.assertEqual(review.similarity_score, 0.0)

    def test_reference_review_warns_on_over_merged_exact_url_blocks(self):
        current = [
            _captured_block_for_review(order=1, selector="body > fv", y=0, height=400, label="ファーストビュー結論"),
            _captured_block_for_review(order=2, selector="body > rank", y=500, height=2400, label="ランキング本文"),
        ]
        reference = [
            _captured_block_for_review(order=1, selector="body > fv", y=0, height=400, label="ファーストビュー結論", run_id="ref-run"),
            _captured_block_for_review(order=2, selector="body > cmp", y=420, height=800, label="一括比較表", run_id="ref-run"),
            _captured_block_for_review(order=3, selector="body > basic", y=1300, height=400, label="個別候補の基本情報", run_id="ref-run"),
            _captured_block_for_review(order=4, selector="body > case", y=1750, height=500, label="効果/症例/Before After", run_id="ref-run"),
            _captured_block_for_review(order=5, selector="body > voice", y=2300, height=400, label="口コミ/体験談", run_id="ref-run"),
            _captured_block_for_review(order=6, selector="body > cta", y=2750, height=220, label="CTA反復", run_id="ref-run"),
        ]

        review = review_blocks_against_references(current, reference, category_name="結婚相談所")

        self.assertEqual(review.status, "needs_review")
        self.assertEqual(review.reference_strength, "exact_url")
        self.assertTrue(any("over_merged" in warning for warning in review.warnings))
        self.assertIn("ref-run", review.reference_run_ids)

    def test_reference_review_warns_on_single_product_mislabeled_as_comparison(self):
        current = [
            _captured_block_for_review(
                order=1,
                selector="body > table",
                y=0,
                height=500,
                label="一括比較表",
                structure_memo="料金プラン 月額 メーカー保証 矯正範囲 部分矯正 実績 エリア 東京",
            )
        ]
        reference = [
            _captured_block_for_review(order=1, selector="body > product", y=0, height=500, label="個別候補の詳細比較", run_id="ref-run")
        ]

        review = review_blocks_against_references(current, reference, category_name="マウスピース矯正")

        self.assertEqual(review.status, "needs_review")
        self.assertTrue(any("single_product_mislabeled" in warning for warning in review.warnings))

    def test_apply_reference_review_to_blocks_sets_notion_fields(self):
        current = [_captured_block_for_review(order=1, selector="body > a", y=0, height=400, label="ファーストビュー結論")]
        reference = [_captured_block_for_review(order=1, selector="body > a", y=0, height=400, label="ファーストビュー結論", run_id="ref-run")]

        review = review_blocks_against_references(current, reference, category_name="結婚相談所")
        blocks = apply_reference_review_to_blocks(current, review)

        self.assertEqual(blocks[0].reference_review_status, "OK")
        self.assertEqual(blocks[0].reference_run_ids, ("ref-run",))
        self.assertGreater(blocks[0].reference_similarity or 0, 0.9)


class BlockFeedbackLearningTest(unittest.TestCase):
    def test_approved_label_override_rule_updates_matching_block(self):
        block = _captured_block_for_review(
            order=1,
            selector="body > div.hikaku",
            y=0,
            height=500,
            label="一括比較表",
            structure_memo="料金プラン 矯正範囲 エリア",
        )
        rules = [
            {
                "id": "rule-label",
                "status": "approved",
                "scope": {"level": "global"},
                "action": "label_override",
                "match": {"detail_label": ["一括比較表"], "text_contains": ["料金プラン"]},
                "effect": {"major_category": "個別候補詳細", "detail_label": "個別候補の詳細比較"},
            }
        ]

        result = apply_approved_learning_rules([block], rules)

        self.assertEqual(result.blocks[0].major_category, "個別候補詳細")
        self.assertEqual(result.blocks[0].detail_label, "個別候補の詳細比較")
        self.assertEqual(result.blocks[0].applied_learning_rule_ids, ("rule-label",))

    def test_feedback_learning_payload_turns_split_feedback_into_pending_rule(self):
        artifact = {
            "category_name": "マウスピース矯正",
            "run": {
                "blocks": [
                    {
                        "source_url": "https://and-smiles.com/",
                        "domain": "and-smiles.com",
                    }
                ]
            },
        }
        payload = build_feedback_learning_payload(
            run_artifact=artifact,
            feedback="ランキング本文がまとまり過ぎている。基本情報、症例、口コミ、オファーは分けたい。",
        )

        rule = payload["rules"][0]
        self.assertEqual(rule["status"], "pending")
        self.assertEqual(rule["scope"]["level"], "url")
        self.assertEqual(rule["action"], "prefer_split")
        self.assertIn("ranking", rule["match"]["selector_contains"])
        self.assertIn("口コミ/体験談", rule["effect"]["split_labels"])


class BlockNotionPayloadTest(unittest.TestCase):
    def test_missing_schema_payload_adds_required_properties_without_replacing_title(self):
        existing = {"名前": {"id": "title", "type": "title", "title": {}}}

        payload = missing_block_database_schema_payload(existing)

        self.assertNotIn("名前", payload["properties"])
        self.assertEqual(payload["properties"]["元URL"], {"url": {}})
        self.assertEqual(payload["properties"]["ブロック順"], {"number": {}})
        self.assertEqual(payload["properties"]["ブロック画像"], {"files": {}})
        self.assertEqual(payload["properties"]["image_text"], {"rich_text": {}})
        self.assertEqual(payload["properties"]["Template_image_text"], {"rich_text": {}})
        self.assertEqual(payload["properties"]["参照一致度"], {"number": {"format": "number"}})
        self.assertIn("ファーストビュー", [option["name"] for option in payload["properties"]["ブロック大分類"]["select"]["options"]])
        self.assertIn("一括比較表", [option["name"] for option in payload["properties"]["詳細ラベル"]["select"]["options"]])
        self.assertIn("要確認", [option["name"] for option in payload["properties"]["参照レビュー状態"]["select"]["options"]])

        required = required_block_database_properties()
        self.assertEqual(required["名前"], {"title": {}})
        self.assertIn("個別候補の詳細比較", [option["name"] for option in required["詳細ラベル"]["select"]["options"]])

    def test_page_properties_and_children_attach_uploaded_image(self):
        long_image_text = json.dumps({"basic": {"size": "1080x1080px"}, "detail": "A" * 2400}, ensure_ascii=False)
        template_text = json.dumps({"basic": {"size": "1080x1080px"}, "service": "{サービス名}"}, ensure_ascii=False)
        block = CapturedBlock(
            name="結婚相談所 Example 001 ファーストビュー結論",
            source_url="https://example.com/ranking/",
            domain="example.com",
            page_title="Example Ranking",
            run_id="run-test",
            viewport="mobile-390",
            order=1,
            major_category="ファーストビュー",
            detail_label="ファーストビュー結論",
            screenshot_path="artifacts/test/block-001.png",
            structure_memo="Hero with TOP3 cards and CTA",
            image_prompt="Generate a mobile comparison LP first view.",
            prompt_state="生成済み",
            confidence="高",
            extracted_at="2026-06-12T00:00:00+00:00",
            clip={"x": 0, "y": 0, "width": 390, "height": 620},
            selector="main > section.hero",
            status="取得済み",
            reference_review_status="要確認",
            reference_similarity=0.42,
            reference_review_note="over_merged",
            reference_run_ids=("ref-run",),
            image_text=long_image_text,
            template_image_text=template_text,
        )

        properties = block_page_properties(block, file_upload_id="upload-123")
        children = block_page_children(block, file_upload_id="upload-123")

        self.assertEqual(properties["名前"]["title"][0]["text"]["content"], block.name)
        self.assertEqual(properties["ブロック画像"]["files"][0]["type"], "file_upload")
        self.assertEqual(properties["ブロック画像"]["files"][0]["file_upload"]["id"], "upload-123")
        self.assertEqual(properties["参照レビュー状態"]["select"]["name"], "要確認")
        self.assertEqual(properties["参照一致度"]["number"], 0.42)
        self.assertIn("over_merged", properties["参照レビュー"]["rich_text"][0]["text"]["content"])
        self.assertGreater(len(properties["image_text"]["rich_text"]), 1)
        self.assertEqual(_rich_text_plain(properties["image_text"]), long_image_text)
        self.assertEqual(_rich_text_plain(properties["Template_image_text"]), template_text)
        self.assertEqual(children[0]["type"], "image")
        self.assertEqual(children[0]["image"]["file_upload"]["id"], "upload-123")
        child_text = "\n".join(_child_plain_text(child) for child in children)
        self.assertIn("image_text", child_text)
        self.assertIn("Template_image_text", child_text)


class BlockImageTextPromptTest(unittest.TestCase):
    def test_apply_image_text_prompts_uses_client_payloads(self):
        block = _captured_block_for_review(
            order=1,
            selector="body > section.hero",
            y=0,
            height=390,
            label="ファーストビュー結論",
            structure_memo="Hero image",
        )
        client = FakeImageTextClient()

        result = apply_image_text_prompts([block], category_name="マウスピース矯正", client=client)

        self.assertEqual(len(client.calls), 1)
        self.assertIn('"basic"', result[0].image_text)
        self.assertIn('"globalDesign"', result[0].image_text)
        self.assertIn('"zones"', result[0].image_text)
        self.assertIn('"reproduction"', result[0].image_text)
        self.assertIn("{サービス名}", result[0].template_image_text)
        self.assertNotIn("スマイルモア矯正", result[0].template_image_text)


class FinalizeBlockCaptureTest(unittest.TestCase):
    def test_finalize_generates_image_text_and_saves_reviewed_blocks_to_notion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            image_path = root / "block-001.png"
            image_path.write_bytes(b"fake image bytes")
            artifact_path = root / "dry-run.json"
            out_path = root / "finalized.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "version": "v2-block-capture",
                        "dry_run": True,
                        "category_name": "マウスピース矯正",
                        "run": {
                            "run_id": "run-test",
                            "urls": ["https://example.com/"],
                            "viewport": "mobile-390",
                            "failed_urls": [],
                            "blocks": [
                                {
                                    "name": "Example 001",
                                    "source_url": "https://example.com/",
                                    "domain": "example.com",
                                    "page_title": "Example",
                                    "run_id": "run-test",
                                    "viewport": "mobile-390",
                                    "order": 1,
                                    "major_category": "ファーストビュー",
                                    "detail_label": "ファーストビュー結論",
                                    "screenshot_path": str(image_path),
                                    "structure_memo": "selector=hero",
                                    "image_prompt": "",
                                    "prompt_state": "未生成",
                                    "confidence": "高",
                                    "extracted_at": "2026-06-23T00:00:00+00:00",
                                    "clip": {"x": 0, "y": 0, "width": 390, "height": 390},
                                    "selector": "body > section.hero",
                                    "status": "取得済み",
                                }
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            notion = FakeBlockNotion()
            client = FakeImageTextClient()

            result = finalize_block_capture(
                run_artifact_path=artifact_path,
                category_name="マウスピース矯正",
                notion=notion,
                database_id="db-test",
                confirm_reviewed=True,
                client=client,
                out_path=out_path,
            )

            self.assertEqual(result["run"]["block_count"], 1)
            self.assertEqual(result["notion"]["row_ids"], ["page-1"])
            self.assertEqual(notion.uploaded_paths, [str(image_path)])
            created = notion.created_pages[0]["properties"]
            self.assertIn("{サービス名}", _rich_text_plain(created["Template_image_text"]))
            self.assertIn('"basic"', _rich_text_plain(created["image_text"]))
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["version"], "v2-block-capture-finalized")
            self.assertIn('"zones"', saved["run"]["blocks"][0]["image_text"])

    def test_finalize_requires_explicit_review_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "dry-run.json"
            artifact_path.write_text(json.dumps({"run": {"blocks": []}}), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "confirm-reviewed"):
                finalize_block_capture(
                    run_artifact_path=artifact_path,
                    category_name="結婚相談所",
                    notion=FakeBlockNotion(),
                    database_id="db-test",
                    confirm_reviewed=False,
                    client=FakeImageTextClient(),
                )

    def test_finalize_fails_before_notion_when_openai_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "dry-run.json"
            artifact_path.write_text(json.dumps({"run": {"blocks": []}}), encoding="utf-8")
            notion = FakeBlockNotion()

            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                finalize_block_capture(
                    run_artifact_path=artifact_path,
                    category_name="結婚相談所",
                    notion=notion,
                    database_id="db-test",
                    confirm_reviewed=True,
                    client=UnavailableImageTextClient(),
                )
            self.assertEqual(notion.created_pages, [])

    def test_finalize_fails_when_acquired_block_screenshot_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "dry-run.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "run": {
                            "blocks": [
                                {
                                    "name": "Missing",
                                    "source_url": "https://example.com/",
                                    "domain": "example.com",
                                    "page_title": "Example",
                                    "run_id": "run-test",
                                    "viewport": "mobile-390",
                                    "order": 1,
                                    "major_category": "その他",
                                    "detail_label": "その他",
                                    "screenshot_path": str(Path(tmpdir) / "missing.png"),
                                    "structure_memo": "",
                                    "image_prompt": "",
                                    "prompt_state": "未生成",
                                    "confidence": "低",
                                    "extracted_at": "2026-06-23T00:00:00+00:00",
                                    "clip": {"x": 0, "y": 0, "width": 390, "height": 1},
                                    "selector": "body",
                                    "status": "取得済み",
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "screenshot"):
                finalize_block_capture(
                    run_artifact_path=artifact_path,
                    category_name="結婚相談所",
                    notion=FakeBlockNotion(),
                    database_id="db-test",
                    confirm_reviewed=True,
                    client=FakeImageTextClient(),
                )


class BlockPromptingTest(unittest.TestCase):
    def test_analyze_blocks_marks_prompt_unavailable_when_openai_is_disabled(self):
        block = CapturedBlock(
            name="Example 001",
            source_url="https://example.com/",
            domain="example.com",
            page_title="Example",
            run_id="run-test",
            viewport="mobile-390",
            order=1,
            major_category="その他",
            detail_label="その他",
            screenshot_path="artifacts/test/block-001.png",
            structure_memo="",
            image_prompt="",
            prompt_state="未生成",
            confidence="低",
            extracted_at="2026-06-12T00:00:00+00:00",
            clip={"x": 0, "y": 0, "width": 390, "height": 400},
            selector="body",
            status="取得済み",
        )

        analyzed = analyze_blocks([block], category_name="結婚相談所", use_openai=False)

        self.assertEqual(analyzed[0].prompt_state, "未生成")
        self.assertEqual(analyzed[0].image_prompt, "")
        self.assertIn("OpenAI", analyzed[0].structure_memo)


class CaptureBlocksCliTest(unittest.TestCase):
    def test_parser_accepts_capture_blocks_command(self):
        args = build_parser().parse_args(
            [
                "capture-blocks",
                "--category-name",
                "結婚相談所",
                "--competitor-url",
                "https://example.com/ranking/",
                "--dry-run",
                "--no-openai",
                "--reference-review",
                "--reference-database-id",
                "db-test",
            ]
        )

        self.assertIsInstance(args, argparse.Namespace)
        self.assertEqual(args.command, "capture-blocks")
        self.assertEqual(args.category_name, "結婚相談所")
        self.assertTrue(args.dry_run)
        self.assertTrue(args.no_openai)
        self.assertTrue(args.reference_review)
        self.assertEqual(args.reference_database_id, "db-test")

    def test_parser_accepts_learn_block_feedback_command(self):
        args = build_parser().parse_args(
            [
                "learn-block-feedback",
                "--run-artifact",
                "artifacts/latest.json",
                "--feedback-file",
                "feedback.txt",
                "--out",
                "learning/pending_rules.json",
            ]
        )

        self.assertEqual(args.command, "learn-block-feedback")
        self.assertEqual(args.run_artifact, "artifacts/latest.json")
        self.assertEqual(args.feedback_file, "feedback.txt")

    def test_parser_accepts_finalize_block_capture_command(self):
        args = build_parser().parse_args(
            [
                "finalize-block-capture",
                "--run-artifact",
                "artifacts/dry-run.json",
                "--notion-database-id",
                "db-test",
                "--category-name",
                "マウスピース矯正",
                "--confirm-reviewed",
                "--out",
                "artifacts/finalized.json",
            ]
        )

        self.assertEqual(args.command, "finalize-block-capture")
        self.assertEqual(args.run_artifact, "artifacts/dry-run.json")
        self.assertEqual(args.notion_database_id, "db-test")
        self.assertEqual(args.category_name, "マウスピース矯正")
        self.assertTrue(args.confirm_reviewed)


if __name__ == "__main__":
    unittest.main()
