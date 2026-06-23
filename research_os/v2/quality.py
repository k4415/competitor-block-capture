from __future__ import annotations

from dataclasses import dataclass

from .models import ResearchV2Bundle
from .profiles import GenreProfile, resolve_genre_profile


class QualityGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class QualityReport:
    profile: GenreProfile
    counts: dict[str, int]
    source_count: int
    missing: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing

    @property
    def status(self) -> str:
        return "passed" if self.passed else "failed"

    def message(self) -> str:
        if self.passed:
            return "品質基準達成"
        return "品質基準未達: " + " / ".join(self.missing) + "。" + self.current_counts_text()

    def current_counts_text(self) -> str:
        return (
            f"現在 category={self.counts['category_facts']}, "
            f"target={self.counts['target_facts']}, "
            f"players={self.counts['players']}, "
            f"competitor_sites={self.counts['competitors']}, "
            f"source_count={self.source_count}"
        )


def evaluate_v2_quality(category_name: str, bundle: ResearchV2Bundle, *, expected_competitors: int | None = None) -> QualityReport:
    profile = resolve_genre_profile(category_name)
    counts = _quality_counts(bundle)
    threshold = profile.thresholds
    competitor_threshold = max(threshold.competitors, expected_competitors or 0)
    missing = []
    if counts["category_facts"] < threshold.category_facts:
        missing.append(f"カテゴリー{threshold.category_facts}件以上")
    if counts["target_facts"] < threshold.target_facts:
        missing.append(f"ターゲット{threshold.target_facts}件以上")
    if counts["players"] < threshold.players:
        missing.append(f"メインプレイヤー{threshold.players}社以上")
    if counts["competitors"] < competitor_threshold:
        missing.append(f"競合サイト{competitor_threshold}件以上")
    if bundle.source_count < threshold.source_count:
        missing.append(f"収集ソース{threshold.source_count}件以上")
    category_majors = {fact.major_category for fact in bundle.category_facts if fact.is_usable()}
    target_majors = {fact.major_category for fact in bundle.target_facts if fact.is_usable()}
    for major in profile.required_category_majors:
        if major not in category_majors:
            missing.append(f"必須カテゴリー: {major}")
    for major in profile.required_target_majors:
        if major not in target_majors:
            missing.append(f"必須ターゲット項目: {major}")
    if not profile.known and missing:
        missing.insert(0, "未対応カテゴリのため十分な明示ソースまたはOpenAI/APIリサーチ結果が必要")
    return QualityReport(profile=profile, counts=counts, source_count=bundle.source_count, missing=tuple(missing))


def validate_v2_quality(category_name: str, bundle: ResearchV2Bundle, *, expected_competitors: int | None = None) -> QualityReport:
    report = evaluate_v2_quality(category_name, bundle, expected_competitors=expected_competitors)
    if not report.passed:
        raise QualityGateError(report.message())
    return report


def _quality_counts(bundle: ResearchV2Bundle) -> dict[str, int]:
    counts = bundle.counts()
    counts["competitors"] = sum(
        1
        for competitor in bundle.competitors
        if competitor.normalized_verification_status() != "取得失敗" and competitor.direct_competitor
    )
    return counts
