"""Print approved and rejected prompt texts in plain blocks."""

from __future__ import annotations

from sqlmodel import Session, create_engine, select

from app.core.config import settings
from models.generated_image import GeneratedImage
from models.image_prompt import ImagePrompt


def _fetch_prompt_texts(session: Session, approved: bool) -> list[str]:
    stmt = (
        select(ImagePrompt.prompt_text)
        .join(GeneratedImage, GeneratedImage.image_prompt_id == ImagePrompt.id)
        .where(GeneratedImage.user_approved.is_(approved))
        .order_by(
            GeneratedImage.approval_updated_at.desc(),
            GeneratedImage.created_at.desc(),
        )
    )
    prompts: list[str] = []
    for prompt_text in session.exec(stmt):
        if prompt_text:
            prompts.append(prompt_text.strip())
    return prompts


def _print_block(title: str, prompts: list[str]) -> None:
    print(f"=== {title} ===\n")
    print("\n\n".join(prompts))
    print()


def main() -> None:
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    with Session(engine) as session:
        approved_prompts = _fetch_prompt_texts(session, approved=True)
        rejected_prompts = _fetch_prompt_texts(session, approved=False)

    _print_block("APPROVED PROMPTS", approved_prompts)
    _print_block("REJECTED PROMPTS", rejected_prompts)


if __name__ == "__main__":
    main()
