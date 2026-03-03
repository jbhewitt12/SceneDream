"""add app settings and art style catalog

Revision ID: b7a3c1d9e5f2
Revises: f0c9f8a2b321
Create Date: 2026-03-03 14:00:00.000000

"""

from __future__ import annotations

from datetime import datetime, timezone
import re
import uuid

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

# revision identifiers, used by Alembic.
revision = "b7a3c1d9e5f2"
down_revision = "f0c9f8a2b321"
branch_labels = None
depends_on = None


_RECOMMENDED_STYLES: tuple[str, ...] = (
    "90's anime",
    "Ukiyo-e woodblock",
    "stained glass mosaic",
    "Art Nouveau",
    "Impressionism",
    "Cubism",
    "knolling",
    "wood burned artwork",
    "smudged oil painting",
    "3D voxel art",
    "technical drawing",
    "Neo-Expressionist",
    "electric luminescent low-poly",
    "3D drawing",
    "neon cubism",
    "watercolor pixel art",
    "smudged charcoal",
    "smudged Chinese ink painting",
    "anime-style watercolor",
    "3D Pixar-style cartoon",
    "illuminated manuscript",
    "psychedelic art",
    "double exposure",
    "fractal art",
)

_OTHER_STYLES: tuple[str, ...] = (
    "neon-line drawing",
    "miniature diorama",
    "sci-fi fantasy art",
    "isometric LEGO",
    "Abstract art",
    "abstract geometry",
    "Art Deco",
    "Bauhaus",
    "bokeh art",
    "Brutalism",
    "Byzantine art",
    "Celtic art",
    "chiptune visuals",
    "concept art",
    "Constructivism",
    "Cyber Folk",
    "cybernetic art",
    "cyberpunk",
    "Dadaism",
    "data art",
    "digital collage",
    "digital cubism",
    "digital Impressionism",
    "digital painting",
    "dreamy fantasy",
    "etching",
    "Expressionism",
    "Fauvism",
    "flat design",
    "Futurism",
    "glitch art",
    "Gothic art",
    "Greco-Roman art",
    "ink wash painting",
    "isometric art",
    "lithography",
    "low-poly art",
    "macabre art",
    "Magic Realism",
    "Minimalism",
    "Modernism",
    "mosaic art",
    "neon graffiti",
    "neon noir",
    "origami art",
    "paper sculpture",
    "papercraft",
    "parallax art",
    "pastel drawing",
    "pixel art",
    "pointillism",
    "polyart",
    "Pop Art",
    "Renaissance painting",
    "Baroque painting",
    "Retro Wave",
    "Romanticism",
    "scratchboard art",
    "steampunk",
    "stippling",
    "Surrealism",
    "Symbolism",
    "trompe-l'oeil",
    "Vaporwave",
    "vector art",
    "watercolor painting",
    "Zen doodle",
    "graffiti art",
    "manga style",
    "comic book style",
    "cartoon style",
    "black-and-white",
    "sepia tone",
    "vintage style",
    "Dutch Golden Age",
    "Tibetan thangka",
    "botanical illustration",
    "visionary art",
    "mandala art",
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "style"


def upgrade() -> None:
    op.create_table(
        "art_styles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column(
            "display_name",
            sqlmodel.sql.sqltypes.AutoString(length=255),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_recommended", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_art_styles_slug"),
    )
    op.create_index(op.f("ix_art_styles_slug"), "art_styles", ["slug"], unique=False)
    op.create_index(
        op.f("ix_art_styles_is_recommended"),
        "art_styles",
        ["is_recommended"],
        unique=False,
    )
    op.create_index(
        op.f("ix_art_styles_is_active"), "art_styles", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_art_styles_created_at"), "art_styles", ["created_at"], unique=False
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "singleton_key",
            sqlmodel.sql.sqltypes.AutoString(length=32),
            nullable=False,
        ),
        sa.Column("default_scenes_per_run", sa.Integer(), nullable=False),
        sa.Column("default_art_style_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["default_art_style_id"],
            ["art_styles.id"],
            name="fk_app_settings_default_art_style_id_art_styles",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("singleton_key", name="uq_app_settings_singleton_key"),
    )
    op.create_index(
        op.f("ix_app_settings_singleton_key"),
        "app_settings",
        ["singleton_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_settings_default_art_style_id"),
        "app_settings",
        ["default_art_style_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_app_settings_created_at"),
        "app_settings",
        ["created_at"],
        unique=False,
    )

    styles_table = sa.table(
        "art_styles",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String(length=255)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("description", sa.Text()),
        sa.column("is_recommended", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    used_slugs: set[str] = set()
    style_rows: list[dict[str, object]] = []
    default_art_style_id: uuid.UUID | None = None

    def _append_rows(styles: tuple[str, ...], *, is_recommended: bool) -> None:
        nonlocal default_art_style_id
        base_order = len(style_rows)
        for offset, display_name in enumerate(styles):
            base_slug = _slugify(display_name)
            slug = base_slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{suffix}"
                suffix += 1
            used_slugs.add(slug)
            style_id = uuid.uuid4()
            if default_art_style_id is None and is_recommended:
                default_art_style_id = style_id
            style_rows.append(
                {
                    "id": style_id,
                    "slug": slug,
                    "display_name": display_name,
                    "description": None,
                    "is_recommended": is_recommended,
                    "is_active": True,
                    "sort_order": base_order + offset,
                    "created_at": now,
                    "updated_at": now,
                }
            )

    _append_rows(_RECOMMENDED_STYLES, is_recommended=True)
    _append_rows(_OTHER_STYLES, is_recommended=False)

    op.bulk_insert(styles_table, style_rows)

    if default_art_style_id is None:
        raise RuntimeError("Failed to seed default art style")

    app_settings_table = sa.table(
        "app_settings",
        sa.column("id", sa.Uuid()),
        sa.column("singleton_key", sa.String(length=32)),
        sa.column("default_scenes_per_run", sa.Integer()),
        sa.column("default_art_style_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        app_settings_table,
        [
            {
                "id": uuid.uuid4(),
                "singleton_key": "global",
                "default_scenes_per_run": 5,
                "default_art_style_id": default_art_style_id,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    bind = op.get_bind()
    styles_count = bind.execute(sa.text("SELECT COUNT(*) FROM art_styles")).scalar_one()
    if styles_count <= 0:
        raise RuntimeError("Art style seed verification failed")

    settings_row = bind.execute(
        sa.text(
            """
            SELECT default_scenes_per_run, default_art_style_id
            FROM app_settings
            WHERE singleton_key = 'global'
            """
        )
    ).mappings().first()
    if settings_row is None:
        raise RuntimeError("App settings seed verification failed")
    if settings_row["default_scenes_per_run"] != 5:
        raise RuntimeError("Default scenes-per-run seed verification failed")
    if settings_row["default_art_style_id"] is None:
        raise RuntimeError("Default art-style seed verification failed")


def downgrade() -> None:
    op.drop_index(op.f("ix_app_settings_created_at"), table_name="app_settings")
    op.drop_index(
        op.f("ix_app_settings_default_art_style_id"),
        table_name="app_settings",
    )
    op.drop_index(op.f("ix_app_settings_singleton_key"), table_name="app_settings")
    op.drop_table("app_settings")

    op.drop_index(op.f("ix_art_styles_created_at"), table_name="art_styles")
    op.drop_index(op.f("ix_art_styles_is_active"), table_name="art_styles")
    op.drop_index(op.f("ix_art_styles_is_recommended"), table_name="art_styles")
    op.drop_index(op.f("ix_art_styles_slug"), table_name="art_styles")
    op.drop_table("art_styles")
