from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .block_models import CapturedBlock, DETAIL_LABEL_OPTIONS, MAJOR_CATEGORY_OPTIONS


DEFAULT_APPROVED_RULES_PATH = Path("learning/approved_rules.json")


@dataclass(frozen=True)
class LearningRuleApplication:
    blocks: list[CapturedBlock]
    warnings: tuple[str, ...]
    applied_rule_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "warnings": list(self.warnings),
            "applied_rule_ids": list(self.applied_rule_ids),
        }


def load_approved_learning_rules(path: str | Path = DEFAULT_APPROVED_RULES_PATH) -> list[dict[str, Any]]:
    rule_path = Path(path)
    if not rule_path.exists():
        return []
    data = json.loads(rule_path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        rules = data.get("rules", [])
    else:
        rules = data
    return [rule for rule in rules if isinstance(rule, dict) and rule.get("status") == "approved"]


def apply_approved_learning_rules(blocks: list[CapturedBlock], rules: list[dict[str, Any]]) -> LearningRuleApplication:
    output: list[CapturedBlock] = []
    warnings: list[str] = []
    applied_ids: list[str] = []

    for block in blocks:
        current = block
        excluded = False
        current_rule_ids: list[str] = list(current.applied_learning_rule_ids)
        for rule in rules:
            if not _rule_matches_block(rule, current):
                continue
            rule_id = str(rule.get("id") or "")
            action = str(rule.get("action") or "")
            effect = rule.get("effect") if isinstance(rule.get("effect"), dict) else {}
            if rule_id:
                applied_ids.append(rule_id)
                current_rule_ids.append(rule_id)
            if action == "selector_exclude":
                warnings.append(f"learning_selector_exclude: order {current.order} matched {rule_id}")
                excluded = True
                break
            if action == "label_override":
                major_category = _safe_choice(str(effect.get("major_category") or current.major_category), MAJOR_CATEGORY_OPTIONS, current.major_category)
                detail_label = _safe_choice(str(effect.get("detail_label") or current.detail_label), DETAIL_LABEL_OPTIONS, current.detail_label)
                current = replace(current, major_category=major_category, detail_label=detail_label, confidence="高")
            elif action in {"prefer_split", "prefer_merge", "review_warning", "selector_include"}:
                warnings.append(f"learning_{action}: order {current.order} matched {rule_id}")
        if not excluded:
            output.append(replace(current, applied_learning_rule_ids=tuple(_dedupe(current_rule_ids))))

    return LearningRuleApplication(blocks=output, warnings=tuple(_dedupe(warnings)), applied_rule_ids=tuple(_dedupe(applied_ids)))


def build_feedback_learning_payload(*, run_artifact: dict[str, Any], feedback: str) -> dict[str, Any]:
    blocks = run_artifact.get("run", {}).get("blocks", [])
    category_name = str(run_artifact.get("category_name") or run_artifact.get("run", {}).get("category_name") or "")
    domains = _dedupe(str(block.get("domain") or _domain_from_url(str(block.get("source_url") or ""))) for block in blocks if isinstance(block, dict))
    urls = _dedupe(str(block.get("source_url") or "") for block in blocks if isinstance(block, dict) and block.get("source_url"))
    action = _infer_feedback_action(feedback)
    scope_level = "url" if len(urls) == 1 else "domain" if len(domains) == 1 else "category" if category_name else "global"
    scope: dict[str, str] = {"level": scope_level}
    if category_name:
        scope["category"] = category_name
    if scope_level in {"domain", "url"} and domains:
        scope["domain"] = domains[0]
    if scope_level == "url" and urls:
        scope["url"] = urls[0]

    rule = {
        "id": f"rule-{uuid.uuid4().hex[:12]}",
        "status": "pending",
        "scope": scope,
        "action": action,
        "match": _infer_feedback_match(feedback),
        "effect": _infer_feedback_effect(feedback, action),
        "source_feedback": feedback.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "test_suggestions": _test_suggestions_for_action(action),
    }
    return {"version": "v1", "rules": [rule]}


def write_feedback_learning_payload(*, run_artifact_path: str | Path, feedback_file: str | Path, out: str | Path) -> dict[str, Any]:
    run_artifact = json.loads(Path(run_artifact_path).read_text(encoding="utf-8"))
    feedback = Path(feedback_file).read_text(encoding="utf-8")
    payload = build_feedback_learning_payload(run_artifact=run_artifact, feedback=feedback)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _rule_matches_block(rule: dict[str, Any], block: CapturedBlock) -> bool:
    if not _scope_matches(rule.get("scope") if isinstance(rule.get("scope"), dict) else {}, block):
        return False
    match = rule.get("match") if isinstance(rule.get("match"), dict) else {}
    selector_contains = _as_str_list(match.get("selector_contains"))
    text_contains = _as_str_list(match.get("text_contains"))
    detail_labels = _as_str_list(match.get("detail_label"))
    if selector_contains and not any(item in block.selector for item in selector_contains):
        return False
    text = " ".join([block.name, block.structure_memo, block.detail_label, block.major_category])
    if text_contains and not all(item in text for item in text_contains):
        return False
    if detail_labels and block.detail_label not in detail_labels:
        return False
    return True


def _scope_matches(scope: dict[str, Any], block: CapturedBlock) -> bool:
    level = str(scope.get("level") or "global")
    if level == "global":
        return True
    if level == "category":
        category = str(scope.get("category") or "")
        return bool(category and category in block.name)
    if level == "domain":
        return block.domain == str(scope.get("domain") or "")
    if level == "url":
        return block.source_url == str(scope.get("url") or "")
    return False


def _infer_feedback_action(feedback: str) -> str:
    if _contains_any(feedback, ["一括比較表", "1商品", "１商品", "個別候補"]):
        return "label_override"
    if _contains_any(feedback, ["まとまり過ぎ", "まとまりすぎ", "分解", "分け", "分割して", "細分化"]):
        return "prefer_split"
    if _contains_any(feedback, ["細かすぎ", "細か過ぎ", "まとめ", "結合"]):
        return "prefer_merge"
    return "review_warning"


def _infer_feedback_match(feedback: str) -> dict[str, list[str]]:
    match: dict[str, list[str]] = {}
    if _contains_any(feedback, ["ランキング", "rank"]):
        match["selector_contains"] = ["ranking", "rank"]
    labels = [label for label in ["基本情報", "症例", "口コミ", "オファー", "キャンペーン", "店舗", "料金プラン", "矯正範囲", "エリア"] if label in feedback]
    if labels:
        match["text_contains"] = labels
    if _contains_any(feedback, ["一括比較表"]):
        match["detail_label"] = ["一括比較表"]
    return match


def _infer_feedback_effect(feedback: str, action: str) -> dict[str, Any]:
    if action == "label_override":
        return {"major_category": "個別候補詳細", "detail_label": "個別候補の詳細比較"}
    if action == "prefer_split":
        labels = []
        if _contains_any(feedback, ["基本情報", "料金"]):
            labels.append("個別候補の基本情報")
        if _contains_any(feedback, ["症例", "Before", "After"]):
            labels.append("効果/症例/Before After")
        if _contains_any(feedback, ["口コミ", "体験談"]):
            labels.append("口コミ/体験談")
        if _contains_any(feedback, ["オファー", "キャンペーン", "限定"]):
            labels.append("限定オファー")
        return {"split_labels": labels or ["個別候補の基本情報", "口コミ/体験談", "限定オファー"]}
    if action == "prefer_merge":
        return {"merge_preference": "semantic_visual_group"}
    return {"warning": "ユーザーフィードバックに基づく確認観点"}


def _test_suggestions_for_action(action: str) -> list[str]:
    if action == "label_override":
        return ["該当ブロックが個別候補詳細へラベル補正されること", "一括比較表の誤判定警告が消えること"]
    if action == "prefer_split":
        return ["親ランキングブロックではなく内部の意味ブロックが残ること", "過結合レビュー警告が消えること"]
    if action == "prefer_merge":
        return ["近接する見出し、本文、CTAが1つの意味ブロックにまとまること", "過分割レビュー警告が消えること"]
    return ["レビュー警告としてJSONに残ること"]


def _safe_choice(value: str, allowed: list[str], fallback: str) -> str:
    return value if value in allowed else fallback


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value]
    return []


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle.lower() in text.lower() for needle in needles)


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0] or "unknown"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
