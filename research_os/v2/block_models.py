from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MAJOR_CATEGORY_OPTIONS = [
    "ページ前提",
    "ファーストビュー",
    "ランキング前説明",
    "解決方法・選択肢理解",
    "費用・負担理解",
    "選び方・評価基準",
    "比較表",
    "ランキング",
    "個別候補詳細",
    "行動前不安解消",
    "クロージング",
    "サイト信頼・回遊",
    "その他",
]

DETAIL_LABEL_OPTIONS = [
    "PR・広告表記",
    "最新版・地域版ラベル",
    "カテゴリ明示タイトル",
    "対象ユーザー定義",
    "ファーストビュー結論",
    "上位候補ミニ比較",
    "信頼バッジ",
    "即時CTA",
    "アンカー/目次",
    "悩み共感リスト",
    "セルフチェック/診断",
    "原因・仕組み解説",
    "未対策リスク",
    "行動後ベネフィット",
    "代替手段比較",
    "解決方法の種類",
    "主要方式の比較",
    "向いている人/向かない人",
    "効果・限界の整理",
    "痛み・負担・副作用",
    "期間・回数・通院頻度",
    "価格体系の基礎解説",
    "保険・支払い方法",
    "選び方3〜5ポイント",
    "比較前チェックリスト",
    "失敗/後悔パターン",
    "格安・キャンペーン注意",
    "評価基準/調査方法",
    "一括比較表",
    "横スクロール比較表",
    "目的別比較表",
    "絞り込み検索",
    "ランキング本文",
    "おすすめポイント要約",
    "料金メニュー詳細",
    "効果/症例/Before After",
    "口コミ/体験談",
    "専門家/担当者紹介",
    "実績・運営基盤",
    "サポート/保証",
    "プライバシー/心理安全",
    "店舗/地域一覧",
    "個別候補の基本情報",
    "個別候補の詳細比較",
    "利用・施術の流れ",
    "初回相談の使い方",
    "FAQ/Q&A",
    "反論処理",
    "タイプ別おすすめ",
    "迷ったらここ",
    "限定オファー",
    "CTA反復",
    "関連コラム/深掘り",
    "法務・注意書き",
    "運営者/問い合わせ",
    "その他",
]


@dataclass(frozen=True)
class CapturedBlock:
    name: str
    source_url: str
    domain: str
    page_title: str
    run_id: str
    viewport: str
    order: int
    major_category: str
    detail_label: str
    screenshot_path: str
    structure_memo: str
    image_prompt: str
    prompt_state: str
    confidence: str
    extracted_at: str
    clip: dict[str, float]
    selector: str
    status: str
    image_text: str = ""
    template_image_text: str = ""
    reference_review_status: str = "参照なし"
    reference_similarity: float | None = None
    reference_review_note: str = ""
    reference_run_ids: tuple[str, ...] = ()
    applied_learning_rule_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlockCaptureRun:
    run_id: str
    category_name: str
    urls: list[str]
    viewport: str
    blocks: list[CapturedBlock]
    failed_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "category_name": self.category_name,
            "urls": self.urls,
            "viewport": self.viewport,
            "block_count": len(self.blocks),
            "failed_urls": self.failed_urls,
            "blocks": [block.to_dict() for block in self.blocks],
        }
