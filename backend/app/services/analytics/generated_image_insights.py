"""Analyze generated image approvals to surface prompt tuning insights.

Run with:
    uv run python -m app.services.analytics.generated_image_insights
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy.orm import joinedload
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from models.generated_image import GeneratedImage


@dataclass(slots=True)
class ImageRecord:
    """Flattened view over generated images for analytics."""

    id: str
    approved: bool | None
    book_slug: str
    chapter_number: int
    prompt_version: str
    variant_index: int
    style_tags: tuple[str, ...]
    references: tuple[str, ...]
    aspect_ratio: str | None
    lens: str | None
    camera: str | None
    prompt_length_words: int
    prompt_length_chars: int
    execution_time_ms: int | None
    provider: str
    model: str
    style: str
    quality: str
    created_at: datetime
    scene_word_count: int | None


@dataclass(slots=True)
class GroupEntry:
    """Aggregated approval stats for a single categorical value."""

    raw_label: Any
    label: str
    approved: int
    total: int
    rate: float
    diff: float
    share: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate approval/disapproval analytics for DALL·E outputs."
    )
    parser.add_argument(
        "--book",
        help="Filter to a single book slug.",
    )
    parser.add_argument(
        "--provider",
        help="Filter by image provider (e.g. openai).",
    )
    parser.add_argument(
        "--model",
        help="Filter by image model (e.g. dall-e-3).",
    )
    parser.add_argument(
        "--prompt-version",
        help="Filter to an exact prompt version.",
    )
    parser.add_argument(
        "--prompt-version-prefix",
        help="Filter to prompt versions starting with this prefix.",
    )
    parser.add_argument(
        "--only-reviewed",
        action="store_true",
        help="Skip images that have not been approved or rejected.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of records (most recent first).",
    )
    parser.add_argument(
        "--database-url",
        help="Override the database URL. Defaults to settings.SQLALCHEMY_DATABASE_URI.",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=3,
        help="Minimum sample size required for subgroup reporting (default: 3).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top/bottom performing subgroups to display (default: 5).",
    )
    return parser.parse_args()


def fetch_records(
    session: Session,
    *,
    book: str | None,
    provider: str | None,
    model: str | None,
    prompt_version: str | None,
    prompt_version_prefix: str | None,
    only_reviewed: bool,
    limit: int | None,
) -> tuple[list[ImageRecord], dict[str, dict[Any, str]]]:
    stmt = (
        select(GeneratedImage)
        .options(
            joinedload(GeneratedImage.image_prompt),
            joinedload(GeneratedImage.scene_extraction),
        )
        .order_by(GeneratedImage.created_at.desc())
    )
    if book:
        stmt = stmt.where(GeneratedImage.book_slug == book)
    if provider:
        stmt = stmt.where(GeneratedImage.provider == provider)
    if model:
        stmt = stmt.where(GeneratedImage.model == model)
    if only_reviewed:
        stmt = stmt.where(GeneratedImage.user_approved.is_not(None))
    if limit:
        stmt = stmt.limit(limit)

    images = session.exec(stmt).unique().all()

    style_tag_display: dict[str, Counter[str]] = defaultdict(Counter)
    reference_display: dict[str, Counter[str]] = defaultdict(Counter)
    records: list[ImageRecord] = []

    for image in images:
        prompt = image.image_prompt
        if not prompt:
            continue

        if prompt_version and prompt.prompt_version != prompt_version:
            continue
        if prompt_version_prefix and not prompt.prompt_version.startswith(
            prompt_version_prefix
        ):
            continue

        style_tags: list[str] = []
        for raw_tag in prompt.style_tags or []:
            cleaned = str(raw_tag).strip()
            if not cleaned:
                continue
            normalized = cleaned.lower()
            style_tag_display[normalized][cleaned] += 1
            style_tags.append(normalized)

        references: list[str] = []
        prompt_attributes = prompt.attributes or {}
        raw_refs = prompt_attributes.get("references")
        if isinstance(raw_refs, Iterable) and not isinstance(raw_refs, (str, bytes)):
            for raw_ref in raw_refs:
                cleaned_ref = str(raw_ref).strip()
                if not cleaned_ref:
                    continue
                normalized_ref = cleaned_ref.lower()
                reference_display[normalized_ref][cleaned_ref] += 1
                references.append(normalized_ref)

        aspect_ratio_value = prompt_attributes.get("aspect_ratio") or image.aspect_ratio
        aspect_ratio = _clean_optional_str(aspect_ratio_value)
        lens = _clean_optional_str(prompt_attributes.get("lens"))
        camera = _clean_optional_str(prompt_attributes.get("camera"))

        prompt_text = prompt.prompt_text or ""
        prompt_length_words = len(prompt_text.split())
        prompt_length_chars = len(prompt_text)

        scene = image.scene_extraction
        scene_word_count = None
        if scene:
            scene_word_count = scene.refined_word_count or scene.raw_word_count

        records.append(
            ImageRecord(
                id=str(image.id),
                approved=image.user_approved,
                book_slug=image.book_slug,
                chapter_number=image.chapter_number,
                prompt_version=prompt.prompt_version,
                variant_index=prompt.variant_index,
                style_tags=tuple(style_tags),
                references=tuple(references),
                aspect_ratio=aspect_ratio,
                lens=lens,
                camera=camera,
                prompt_length_words=prompt_length_words,
                prompt_length_chars=prompt_length_chars,
                execution_time_ms=prompt.execution_time_ms,
                provider=image.provider,
                model=image.model,
                style=image.style,
                quality=image.quality,
                created_at=image.created_at,
                scene_word_count=scene_word_count,
            )
        )

    style_display = {
        label: counts.most_common(1)[0][0] for label, counts in style_tag_display.items()
    }
    reference_display_map = {
        label: counts.most_common(1)[0][0]
        for label, counts in reference_display.items()
    }

    display_maps: dict[str, dict[Any, str]] = {
        "style_tags": style_display,
        "references": reference_display_map,
    }

    return records, display_maps


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def basic_overview(records: Sequence[ImageRecord]) -> tuple[str, dict[str, Any]]:
    approved = sum(1 for rec in records if rec.approved is True)
    rejected = sum(1 for rec in records if rec.approved is False)
    pending = sum(1 for rec in records if rec.approved is None)
    reviewed = approved + rejected
    baseline = (approved / reviewed) if reviewed else 0.0
    created_dates = sorted(rec.created_at for rec in records)
    span_text = (
        f"{created_dates[0]:%Y-%m-%d} → {created_dates[-1]:%Y-%m-%d}"
        if created_dates
        else "n/a"
    )
    overview_text = (
        f"Loaded {len(records)} images | reviewed {reviewed}"
        f" (approved {approved}, disapproved {rejected}, pending {pending})"
        f" | overall approval {baseline:.1%}"
        f" | time span {span_text}"
    )
    data = {
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "reviewed": reviewed,
        "baseline": baseline,
    }
    return overview_text, data


def group_counts(
    records: Sequence[ImageRecord],
    extractor: Callable[[ImageRecord], Iterable[Any] | Any | None],
) -> dict[Any, list[int]]:
    counts: dict[Any, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        if record.approved is None:
            continue
        values = extractor(record)
        if values is None:
            continue
        if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
            values_iterable: Iterable[Any] = (values,)
        else:
            values_iterable = values
        for value in values_iterable:
            if value is None:
                continue
            key: Any = value
            if isinstance(key, str):
                key = key.strip()
                if not key:
                    continue
            counts[key][0] += 1 if record.approved else 0
            counts[key][1] += 1
    return counts


def prepare_group_entries(
    counts: dict[Any, list[int]],
    *,
    baseline: float,
    total_samples: int,
    min_count: int,
    top_n: int,
    display_map: dict[Any, str] | None = None,
) -> dict[str, list[GroupEntry]]:
    entries: list[GroupEntry] = []
    for raw_label, (approved, total) in counts.items():
        if total < min_count:
            continue
        rate = approved / total if total else 0.0
        diff = rate - baseline
        share = total / total_samples if total_samples else 0.0
        label = (
            display_map.get(raw_label, raw_label)
            if display_map is not None
            else raw_label
        )
        label_text = str(label)
        entries.append(
            GroupEntry(
                raw_label=raw_label,
                label=label_text,
                approved=approved,
                total=total,
                rate=rate,
                diff=diff,
                share=share,
            )
        )

    if not entries:
        return {"entries": [], "positives": [], "negatives": []}

    sorted_by_diff = sorted(
        entries, key=lambda entry: (entry.diff, entry.total), reverse=True
    )
    positives = [entry for entry in sorted_by_diff if entry.diff >= 0][:top_n]
    seen_labels = {entry.raw_label for entry in positives}
    negatives: list[GroupEntry] = []
    for entry in sorted(entries, key=lambda entry: (entry.diff, -entry.total)):
        if entry.diff > 0:
            continue
        if entry.raw_label in seen_labels:
            continue
        negatives.append(entry)
        if len(negatives) >= top_n:
            break

    return {"entries": entries, "positives": positives, "negatives": negatives}


def print_group_analysis(
    title: str,
    analysis: dict[str, list[GroupEntry]],
    *,
    baseline: float,
) -> None:
    print(f"\n{title}:")
    entries = analysis["entries"]
    if not entries:
        print("  Not enough data for this grouping.")
        return

    print(f"  Baseline approval: {baseline:.1%}")

    if analysis["positives"]:
        print("  Outperforming segments:")
        for entry in analysis["positives"]:
            print(
                f"    + {entry.label}: {entry.rate:.1%} ({entry.approved}/{entry.total}, "
                f"Δ{entry.diff:+.1%}, share {entry.share:.1%})"
            )
    else:
        print("  No segments outperform the baseline.")

    if analysis["negatives"]:
        print("  Underperforming segments:")
        for entry in analysis["negatives"]:
            print(
                f"    - {entry.label}: {entry.rate:.1%} ({entry.approved}/{entry.total}, "
                f"Δ{entry.diff:+.1%}, share {entry.share:.1%})"
            )
    else:
        print("  No segments underperform the baseline.")


def numeric_summary(
    records: Sequence[ImageRecord],
    value_getter: Callable[[ImageRecord], int | float | None],
) -> dict[str, dict[str, float | int]] | None:
    buckets: dict[str, list[float]] = {"approved": [], "disapproved": []}
    for record in records:
        if record.approved is None:
            continue
        value = value_getter(record)
        if value is None:
            continue
        bucket_key = "approved" if record.approved else "disapproved"
        buckets[bucket_key].append(float(value))

    if not any(buckets.values()):
        return None

    summary: dict[str, dict[str, float | int]] = {}
    for bucket, values in buckets.items():
        if not values:
            continue
        summary[bucket] = {
            "count": len(values),
            "mean": mean(values),
            "median": median(values),
            "min": min(values),
            "max": max(values),
        }
    return summary


def print_numeric_summary(title: str, summary: dict[str, dict[str, float | int]] | None):
    print(f"\n{title}:")
    if not summary:
        print("  No data available.")
        return
    for bucket, stats in summary.items():
        mean_value = stats["mean"]
        median_value = stats["median"]
        min_value = stats["min"]
        max_value = stats["max"]
        count_value = stats["count"]
        label = "Approved" if bucket == "approved" else "Disapproved"
        print(
            f"  {label:<12} n={count_value:>3} | mean {mean_value:.1f} | median {median_value:.1f} | "
            f"min {min_value:.1f} | max {max_value:.1f}"
        )


def derive_insights(
    *,
    baseline: float,
    style_analysis: dict[str, list[GroupEntry]],
    reference_analysis: dict[str, list[GroupEntry]],
    aspect_analysis: dict[str, list[GroupEntry]],
    prompt_length_summary: dict[str, dict[str, float | int]] | None,
    scene_length_summary: dict[str, dict[str, float | int]] | None,
    min_count: int,
) -> list[str]:
    insights: list[str] = []

    for entry in style_analysis["negatives"]:
        if entry.total >= min_count and entry.diff <= -0.15:
            insights.append(
                f"Style tag '{entry.label}' trails baseline by {entry.diff:+.1%} "
                f"(approval {entry.rate:.1%}, {entry.approved}/{entry.total})."
            )
    for entry in reference_analysis["negatives"]:
        if entry.total >= min_count and entry.diff <= -0.15:
            insights.append(
                f"Reference '{entry.label}' underperforms with approval {entry.rate:.1%} "
                f"(Δ{entry.diff:+.1%}, {entry.approved}/{entry.total})."
            )
    for entry in aspect_analysis["negatives"]:
        if entry.total >= max(2, min_count // 2) and entry.diff <= -0.15:
            insights.append(
                f"Aspect ratio '{entry.label}' shows approval {entry.rate:.1%} "
                f"(Δ{entry.diff:+.1%}, n={entry.total})."
            )
    def _diff_from_summary(summary: dict[str, dict[str, float | int]] | None) -> float | None:
        if not summary or "approved" not in summary or "disapproved" not in summary:
            return None
        approved_mean = float(summary["approved"]["mean"])
        disapproved_mean = float(summary["disapproved"]["mean"])
        return disapproved_mean - approved_mean

    prompt_diff = _diff_from_summary(prompt_length_summary)
    if prompt_diff is not None and abs(prompt_diff) >= 3:
        insights.append(
            f"Disapproved prompts average {prompt_diff:+.1f} words relative to approved ones."
        )

    scene_diff = _diff_from_summary(scene_length_summary)
    if scene_diff is not None and abs(scene_diff) >= 15:
        insights.append(
            f"Scenes linked to disapproved images differ in length by {scene_diff:+.1f} words on average."
        )

    return insights[:8]


def main() -> None:
    args = parse_args()
    engine = create_engine(args.database_url or str(settings.SQLALCHEMY_DATABASE_URI))

    with Session(engine) as session:
        records, display_maps = fetch_records(
            session,
            book=args.book,
            provider=args.provider,
            model=args.model,
            prompt_version=args.prompt_version,
            prompt_version_prefix=args.prompt_version_prefix,
            only_reviewed=args.only_reviewed,
            limit=args.limit,
        )

    if not records:
        print("No generated images matched the supplied filters.")
        return

    overview_text, overview_data = basic_overview(records)
    print(overview_text)

    reviewed_records = [rec for rec in records if rec.approved is not None]
    total_reviewed = len(reviewed_records)
    if not total_reviewed:
        print("No approved or disapproved images were found. Nothing to analyze yet.")
        return

    baseline = overview_data["baseline"]
    min_count = max(1, args.min_count)

    # Grouped analyses
    prompt_version_counts = group_counts(
        reviewed_records, lambda rec: (rec.prompt_version,)
    )
    prompt_version_analysis = prepare_group_entries(
        prompt_version_counts,
        baseline=baseline,
        total_samples=total_reviewed,
        min_count=min_count,
        top_n=args.top_n,
    )
    print_group_analysis("Prompt versions", prompt_version_analysis, baseline=baseline)

    style_counts = group_counts(reviewed_records, lambda rec: rec.style_tags)
    style_analysis = prepare_group_entries(
        style_counts,
        baseline=baseline,
        total_samples=total_reviewed,
        min_count=min_count,
        top_n=args.top_n,
        display_map=display_maps.get("style_tags"),
    )
    print_group_analysis("Style tags", style_analysis, baseline=baseline)

    reference_counts = group_counts(reviewed_records, lambda rec: rec.references)
    reference_analysis = prepare_group_entries(
        reference_counts,
        baseline=baseline,
        total_samples=total_reviewed,
        min_count=min_count,
        top_n=args.top_n,
        display_map=display_maps.get("references"),
    )
    print_group_analysis("Reference mentions", reference_analysis, baseline=baseline)

    aspect_counts = group_counts(
        reviewed_records,
        lambda rec: (rec.aspect_ratio,) if rec.aspect_ratio else (),
    )
    aspect_analysis = prepare_group_entries(
        aspect_counts,
        baseline=baseline,
        total_samples=total_reviewed,
        min_count=max(2, min_count),
        top_n=args.top_n,
    )
    print_group_analysis("Aspect ratios", aspect_analysis, baseline=baseline)

    # Numeric summaries
    prompt_length_summary = numeric_summary(
        reviewed_records, lambda rec: rec.prompt_length_words
    )
    print_numeric_summary("Prompt length (words)", prompt_length_summary)

    scene_length_summary = numeric_summary(
        reviewed_records, lambda rec: rec.scene_word_count
    )
    print_numeric_summary("Source scene length (words)", scene_length_summary)

    # Derived insights to guide prompt improvements.
    insights = derive_insights(
        baseline=baseline,
        style_analysis=style_analysis,
        reference_analysis=reference_analysis,
        aspect_analysis=aspect_analysis,
        prompt_length_summary=prompt_length_summary,
        scene_length_summary=scene_length_summary,
        min_count=min_count,
    )
    if insights:
        print("\nPotential next experiments:")
        for insight in insights:
            print(f"  - {insight}")
    else:
        print("\nNo actionable deltas surfaced yet. Consider gathering more reviews.")


if __name__ == "__main__":
    main()
