from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


CATEGORY_MAJOR_OPTIONS = [
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
]
TARGET_MAJOR_OPTIONS = [
    "デモグラ",
    "婚活歴",
    "利用前状態",
    "欲求",
    "状態",
    "懸念",
    "ビリーフ",
    "比較対象",
    "購入/申込トリガー",
    "意思決定基準",
    "予算感",
    "不安解消条件",
]
TARGET_SEGMENT_OPTIONS = ["20代男性", "30代男性", "20代女性", "30代女性", "20代", "30代", "40代", "50代以上", "男性", "女性", "共通"]


@dataclass(frozen=True)
class ResearchV2DatabaseSpec:
    key: str
    title: str
    request: dict[str, Any]


def build_v2_research_database_specs(parent_page_id: str) -> list[ResearchV2DatabaseSpec]:
    return [
        _spec("category", "カテゴリーリサーチ", parent_page_id, _common_properties(CATEGORY_MAJOR_OPTIONS, ["共通"])),
        _spec("target", "ターゲットリサーチ", parent_page_id, _common_properties(TARGET_MAJOR_OPTIONS, TARGET_SEGMENT_OPTIONS)),
        _spec("players", "メインプレイヤーリサーチ", parent_page_id, _player_properties()),
        _spec("competitor_sites", "競合比較サイトリサーチ", parent_page_id, _competitor_properties()),
    ]


def _spec(key: str, title: str, parent_page_id: str, properties: dict[str, Any]) -> ResearchV2DatabaseSpec:
    return ResearchV2DatabaseSpec(
        key=key,
        title=title,
        request={
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "is_inline": True,
            "initial_data_source": {"properties": deepcopy(properties)},
        },
    )


def _common_properties(major_options: list[str], segment_options: list[str]) -> dict[str, Any]:
    return {
        "事実": {"title": {}},
        "大項目": {"select": {"options": _options(major_options)}},
        "小項目": {"rich_text": {}},
        "セグメント": {"select": {"options": _options(segment_options)}},
        "根拠URL": {"url": {}},
        "根拠タイトル": {"rich_text": {}},
        "短い引用": {"rich_text": {}},
        "信頼度": {"select": {"options": _options(["高", "中", "低"])}},
        "検証状態": {"select": {"options": _options(["検証済み", "要確認", "取得失敗"])}},
        "取得日時": {"date": {}},
        "リサーチRun ID": {"rich_text": {}},
    }


def _player_properties() -> dict[str, Any]:
    props = _common_properties(["特徴", "メリット", "実績", "権威性", "オファー", "リスク・制約", "会社情報"], ["サービス"])
    props.update(
        {
            "サービス名": {"rich_text": {}},
            "公式URL": {"url": {}},
            "価格": {"rich_text": {}},
            "プラン": {"rich_text": {}},
            "会員数": {"rich_text": {}},
            "実績": {"rich_text": {}},
            "オファー": {"rich_text": {}},
        }
    )
    return props


def _competitor_properties() -> dict[str, Any]:
    props = _common_properties(["構成", "ランキング", "CTA", "掲載サービス", "画像内文言", "比較軸", "証拠表現", "訴求パターン"], ["直接競合"])
    props.update(
        {
            "URL": {"url": {}},
            "ドメイン": {"rich_text": {}},
            "構成タイプ": {"select": {"options": _options(["ランキングLP", "比較LP", "診断LP", "記事LP", "不明"])}},
            "ランキング1": {"rich_text": {}},
            "ランキング2": {"rich_text": {}},
            "ランキング3": {"rich_text": {}},
            "ランキング4": {"rich_text": {}},
            "ランキング5": {"rich_text": {}},
            "主要CTA": {"rich_text": {}},
            "掲載サービス": {"rich_text": {}},
            "直接競合": {"checkbox": {}},
            "画像内主要文言": {"rich_text": {}},
        }
    )
    return props


def _options(names: list[str]) -> list[dict[str, str]]:
    return [{"name": name} for name in names]
