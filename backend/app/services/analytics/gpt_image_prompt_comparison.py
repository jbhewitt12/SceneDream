"""Compare approved vs rejected GPT Image 1.5 prompts."""

from __future__ import annotations

import argparse
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean, median

from sqlalchemy.orm import joinedload
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from models.generated_image import GeneratedImage

WORD_RE = re.compile(r"[A-Za-z0-9']+")
LABEL_RE = re.compile(
    r"\b("
    r"scene|subject|action|environment|details|style|style/medium|technical|"
    r"technical direction|constraints"
    r")\s*:",
    re.IGNORECASE,
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "its",
    "like",
    "no",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "this",
    "to",
    "under",
    "with",
}
PATTERN_GROUPS: dict[str, tuple[str, ...]] = {
    "structured_labels": ("scene:", "subject:", "action:", "details:", "constraints:"),
    "camera_terms": (
        "lens",
        "perspective",
        "close-up",
        "close up",
        "wide-angle",
        "wide angle",
        "low angle",
        "high-angle",
        "high angle",
        "macro",
        "panoramic",
        "shot",
        "composition",
        "pov",
    ),
    "technical_diagram": (
        "technical drawing",
        "schematic",
        "blueprint",
        "wireframe",
        "orthographic",
        "exploded-view",
        "diagrammatic",
        "drafting",
        "grid",
        "grids",
    ),
    "abstract_surreal": (
        "abstract",
        "conceptual",
        "surreal",
        "double exposure",
        "geometric",
        "fractured",
        "fractal",
        "cubism",
        "low-poly",
        "impossible",
    ),
    "craft_material": (
        "paper",
        "papercraft",
        "cardstock",
        "stained glass",
        "mosaic",
        "charcoal",
        "ink",
        "woodblock",
        "lithograph",
        "graphite",
    ),
    "negative_constraints": (
        "no photorealism",
        "no text",
        "no text overlays",
        "no modern",
        "no modern technology",
        "no borders",
        "no organic",
    ),
}


@dataclass(slots=True)
class PromptRecord:
    image_id: str
    approved: bool
    book_slug: str
    aspect_ratio: str | None
    prompt_version: str
    prompt_text: str
    word_count: int
    char_count: int
    sentence_count: int
    comma_count: int
    colon_count: int
    label_count: int
    no_phrase_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare reviewed GPT Image 1.5 prompts by approval outcome."
    )
    parser.add_argument(
        "--model",
        default="gpt-image-1.5",
        help="Generated image model to analyze (default: gpt-image-1.5).",
    )
    parser.add_argument(
        "--provider",
        default="openai_gpt_image",
        help="Generated image provider to analyze (default: openai_gpt_image).",
    )
    parser.add_argument(
        "--min-doc-frequency",
        type=int,
        default=2,
        help="Minimum prompt frequency for distinctive token/n-gram reporting.",
    )
    parser.add_argument(
        "--database-url",
        help="Override the database URL. Defaults to settings.SQLALCHEMY_DATABASE_URI.",
    )
    parser.add_argument(
        "--prompt-version",
        help="Restrict analysis to a single prompt version.",
    )
    parser.add_argument(
        "--show-prompts",
        action="store_true",
        help="Print every reviewed prompt grouped by approval outcome.",
    )
    return parser.parse_args()


def fetch_prompt_records(
    session: Session,
    *,
    provider: str,
    model: str,
    prompt_version: str | None,
) -> list[PromptRecord]:
    stmt = (
        select(GeneratedImage)
        .options(joinedload(GeneratedImage.image_prompt))
        .where(GeneratedImage.provider == provider)
        .where(GeneratedImage.model == model)
        .where(GeneratedImage.user_approved.is_not(None))
        .order_by(GeneratedImage.created_at.asc())
    )
    images = session.exec(stmt).unique().all()
    records: list[PromptRecord] = []

    for image in images:
        prompt = image.image_prompt
        if not prompt or not prompt.prompt_text:
            continue
        if prompt_version and prompt.prompt_version != prompt_version:
            continue
        prompt_text = prompt.prompt_text.strip()
        sentences = [s for s in re.split(r"[.!?]+", prompt_text) if s.strip()]
        records.append(
            PromptRecord(
                image_id=str(image.id),
                approved=bool(image.user_approved),
                book_slug=image.book_slug,
                aspect_ratio=image.aspect_ratio,
                prompt_version=prompt.prompt_version,
                prompt_text=prompt_text,
                word_count=len(WORD_RE.findall(prompt_text)),
                char_count=len(prompt_text),
                sentence_count=len(sentences),
                comma_count=prompt_text.count(","),
                colon_count=prompt_text.count(":"),
                label_count=len(LABEL_RE.findall(prompt_text)),
                no_phrase_count=len(
                    re.findall(r"\bno\s+[a-z]", prompt_text, re.IGNORECASE)
                ),
            )
        )

    return records


def metric_summary(records: list[PromptRecord], attr: str) -> dict[str, float]:
    values = [float(getattr(record, attr)) for record in records]
    return {
        "count": len(values),
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


def percent(value: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(value / total):.1%}"


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def document_terms(text: str) -> tuple[set[str], set[str]]:
    tokens = [
        token for token in tokenize(text) if token not in STOPWORDS and len(token) > 2
    ]
    unigrams = set(tokens)
    bigrams = {" ".join(pair) for pair in zip(tokens, tokens[1:], strict=False)}
    return unigrams, bigrams


def collect_doc_frequencies(
    records: list[PromptRecord],
) -> tuple[Counter[str], Counter[str], Counter[str], Counter[str]]:
    approved_uni: Counter[str] = Counter()
    rejected_uni: Counter[str] = Counter()
    approved_bi: Counter[str] = Counter()
    rejected_bi: Counter[str] = Counter()

    for record in records:
        unigrams, bigrams = document_terms(record.prompt_text)
        if record.approved:
            approved_uni.update(unigrams)
            approved_bi.update(bigrams)
        else:
            rejected_uni.update(unigrams)
            rejected_bi.update(bigrams)

    return approved_uni, rejected_uni, approved_bi, rejected_bi


def distinctive_terms(
    positive: Counter[str],
    negative: Counter[str],
    *,
    positive_total: int,
    negative_total: int,
    min_doc_frequency: int,
    top_n: int = 8,
) -> list[tuple[str, int, int, float]]:
    scores: list[tuple[str, int, int, float]] = []
    for term in set(positive) | set(negative):
        pos_count = positive.get(term, 0)
        neg_count = negative.get(term, 0)
        if max(pos_count, neg_count) < min_doc_frequency:
            continue
        pos_rate = pos_count / positive_total if positive_total else 0.0
        neg_rate = neg_count / negative_total if negative_total else 0.0
        diff = pos_rate - neg_rate
        if math.isclose(diff, 0.0, abs_tol=1e-9):
            continue
        scores.append((term, pos_count, neg_count, diff))

    scores.sort(key=lambda item: (item[3], item[1] - item[2], item[0]), reverse=True)
    return scores[:top_n]


def bucket_pattern_counts(records: list[PromptRecord]) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = defaultdict(
        lambda: {"approved": 0, "rejected": 0}
    )
    for record in records:
        lowered = record.prompt_text.lower()
        bucket = "approved" if record.approved else "rejected"
        for name, phrases in PATTERN_GROUPS.items():
            if any(phrase in lowered for phrase in phrases):
                results[name][bucket] += 1
    return dict(results)


def print_metric_block(
    title: str, approved: list[PromptRecord], rejected: list[PromptRecord]
) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for attr, label in (
        ("word_count", "Words"),
        ("char_count", "Characters"),
        ("sentence_count", "Sentences"),
        ("comma_count", "Commas"),
        ("colon_count", "Colons"),
        ("label_count", "Labeled sections"),
        ("no_phrase_count", '"No ..." constraints'),
    ):
        approved_stats = metric_summary(approved, attr)
        rejected_stats = metric_summary(rejected, attr)
        print(
            f"{label:<18} "
            f"approved mean {approved_stats['mean']:.1f} median {approved_stats['median']:.1f} "
            f"| rejected mean {rejected_stats['mean']:.1f} median {rejected_stats['median']:.1f}"
        )


def print_breakdowns(records: list[PromptRecord]) -> None:
    total = len(records)
    print("\nOutcome breakdowns")
    print("----------------")

    by_version: dict[tuple[str, bool], int] = Counter(
        (record.prompt_version, record.approved) for record in records
    )
    versions = sorted({record.prompt_version for record in records})
    print("Prompt versions:")
    for version in versions:
        approved_count = by_version.get((version, True), 0)
        rejected_count = by_version.get((version, False), 0)
        reviewed = approved_count + rejected_count
        print(
            f"  {version}: {approved_count} approved, {rejected_count} rejected "
            f"({percent(approved_count, reviewed)} approval, n={reviewed})"
        )

    by_aspect: dict[tuple[str, bool], int] = Counter(
        ((record.aspect_ratio or "unknown"), record.approved) for record in records
    )
    aspects = sorted({record.aspect_ratio or "unknown" for record in records})
    print("Aspect ratios:")
    for aspect in aspects:
        approved_count = by_aspect.get((aspect, True), 0)
        rejected_count = by_aspect.get((aspect, False), 0)
        reviewed = approved_count + rejected_count
        print(
            f"  {aspect}: {approved_count} approved, {rejected_count} rejected "
            f"({percent(approved_count, reviewed)} approval, n={reviewed})"
        )

    by_book: dict[tuple[str, bool], int] = Counter(
        (record.book_slug, record.approved) for record in records
    )
    books = sorted({record.book_slug for record in records})
    print("Books:")
    for book in books:
        approved_count = by_book.get((book, True), 0)
        rejected_count = by_book.get((book, False), 0)
        reviewed = approved_count + rejected_count
        print(
            f"  {book}: {approved_count} approved, {rejected_count} rejected "
            f"({percent(approved_count, reviewed)} approval, n={reviewed}, share {reviewed/total:.1%})"
        )


def print_pattern_counts(records: list[PromptRecord]) -> None:
    approved_total = sum(1 for record in records if record.approved)
    rejected_total = len(records) - approved_total
    pattern_counts = bucket_pattern_counts(records)

    print("\nPrompt pattern coverage")
    print("----------------------")
    for name in sorted(pattern_counts):
        approved_count = pattern_counts[name]["approved"]
        rejected_count = pattern_counts[name]["rejected"]
        print(
            f"{name:<20} "
            f"approved {approved_count}/{approved_total} ({percent(approved_count, approved_total)}) "
            f"| rejected {rejected_count}/{rejected_total} ({percent(rejected_count, rejected_total)})"
        )


def print_distinctive_terms(
    records: list[PromptRecord], min_doc_frequency: int
) -> None:
    approved_records = [record for record in records if record.approved]
    rejected_records = [record for record in records if not record.approved]
    approved_uni, rejected_uni, approved_bi, rejected_bi = collect_doc_frequencies(
        records
    )

    print("\nDistinctive vocabulary")
    print("---------------------")

    approved_terms = distinctive_terms(
        approved_uni,
        rejected_uni,
        positive_total=len(approved_records),
        negative_total=len(rejected_records),
        min_doc_frequency=min_doc_frequency,
    )
    rejected_terms = distinctive_terms(
        rejected_uni,
        approved_uni,
        positive_total=len(rejected_records),
        negative_total=len(approved_records),
        min_doc_frequency=min_doc_frequency,
    )
    approved_bigrams = distinctive_terms(
        approved_bi,
        rejected_bi,
        positive_total=len(approved_records),
        negative_total=len(rejected_records),
        min_doc_frequency=min_doc_frequency,
    )
    rejected_bigrams = distinctive_terms(
        rejected_bi,
        approved_bi,
        positive_total=len(rejected_records),
        negative_total=len(approved_records),
        min_doc_frequency=min_doc_frequency,
    )

    print("Approved leaning tokens:")
    for term, pos_count, neg_count, diff in approved_terms:
        print(
            f"  {term}: {pos_count}/{len(approved_records)} approved prompts vs "
            f"{neg_count}/{len(rejected_records)} rejected prompts (Δ{diff:+.1%})"
        )

    print("Rejected leaning tokens:")
    for term, pos_count, neg_count, diff in rejected_terms:
        print(
            f"  {term}: {pos_count}/{len(rejected_records)} rejected prompts vs "
            f"{neg_count}/{len(approved_records)} approved prompts (Δ{diff:+.1%})"
        )

    print("Approved leaning bigrams:")
    for term, pos_count, neg_count, diff in approved_bigrams:
        print(
            f"  {term}: {pos_count}/{len(approved_records)} approved prompts vs "
            f"{neg_count}/{len(rejected_records)} rejected prompts (Δ{diff:+.1%})"
        )

    print("Rejected leaning bigrams:")
    for term, pos_count, neg_count, diff in rejected_bigrams:
        print(
            f"  {term}: {pos_count}/{len(rejected_records)} rejected prompts vs "
            f"{neg_count}/{len(approved_records)} approved prompts (Δ{diff:+.1%})"
        )


def print_prompt_inventory(records: list[PromptRecord], *, approved: bool) -> None:
    title = "Approved prompts" if approved else "Rejected prompts"
    print(f"\n{title}")
    print("-" * len(title))
    for record in records:
        if record.approved != approved:
            continue
        print(
            f"{record.image_id} | {record.book_slug} | {record.aspect_ratio or 'unknown'} "
            f"| {record.prompt_version} | {record.word_count} words"
        )
        print(record.prompt_text)
        print()


def main() -> None:
    args = parse_args()
    engine = create_engine(args.database_url or str(settings.SQLALCHEMY_DATABASE_URI))

    with Session(engine) as session:
        records = fetch_prompt_records(
            session,
            provider=args.provider,
            model=args.model,
            prompt_version=args.prompt_version,
        )

    if not records:
        print("No reviewed prompts matched the supplied provider/model filters.")
        return

    approved_records = [record for record in records if record.approved]
    rejected_records = [record for record in records if not record.approved]

    print(
        f"Loaded {len(records)} reviewed prompts for provider={args.provider} "
        f"model={args.model}: {len(approved_records)} approved, {len(rejected_records)} rejected "
        f"({percent(len(approved_records), len(records))} approval)."
    )

    print_metric_block("Prompt complexity metrics", approved_records, rejected_records)
    print_breakdowns(records)
    print_pattern_counts(records)
    print_distinctive_terms(records, args.min_doc_frequency)

    if args.show_prompts:
        print_prompt_inventory(records, approved=True)
        print_prompt_inventory(records, approved=False)


if __name__ == "__main__":
    main()
