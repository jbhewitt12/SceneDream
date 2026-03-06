# Scrub Internal-Only Details From Public Docs

## Overview
Clean internal-only details from tracked markdown docs in preparation for a polished public repository launch.

## Problem Statement
Some tracked issue/planning docs include local absolute filesystem paths and sensitive-looking operational transcript content. Even when not actively secret, this lowers professionalism and can trigger avoidable concern during public review.

## Proposed Solution
Redact or rewrite internal-only details in docs while preserving technical intent:
- replace absolute local paths with repo-relative paths
- remove one-time auth transcript details
- normalize references to reusable, non-personal examples

## Codebase Research Summary

### Examples identified
- `issues/011-concurrent-remix-endpoints.md` contains `/Users/joshhewitt/...` path references
- `issues/014-auto-post-feature.md` includes local shell transcript details and one-time verifier code text
- Multiple planning docs contain localhost/manual transcript snippets

## Key Decisions
- Keep historical issue context, but sanitize environment-specific/private details.
- Prefer placeholders (`<repo-root>`, `<image_id>`) over personal-machine paths.
- Focus this issue on markdown/docs only, not test fixture strings.

## Implementation Plan

### Phase 1: Path sanitation in issue docs
**Goal**: Remove personal local path references.

**Tasks**:
- Replace `/Users/joshhewitt/dev/SceneDream/...` references with repo-relative paths.
- Use neutral placeholders where absolute paths are not needed.

**Verification**:
- [ ] No personal absolute paths remain in `issues/*.md`

### Phase 2: Transcript sanitation
**Goal**: Remove one-time auth/session details from tracked text.

**Tasks**:
- Rewrite copied command transcripts to safe examples.
- Remove verifier/token-like one-time values from markdown history docs.

**Verification**:
- [ ] No auth-verifier transcript values remain in tracked markdown

### Phase 3: Documentation consistency pass
**Goal**: Keep public docs clear and reusable.

**Tasks**:
- Normalize command examples to generic/local-first forms.
- Ensure docs remain technically accurate after sanitization.

**Verification**:
- [ ] Sanitized docs still provide actionable technical context

## Files to Modify
| File | Action |
|------|--------|
| `issues/011-concurrent-remix-endpoints.md` | Modify |
| `issues/014-auto-post-feature.md` | Modify |
| `issues/*.md` (as needed) | Modify |
| `open_source_plan.md` (as needed) | Modify |

## Testing Strategy
- `rg -n "/Users/joshhewitt|oauth_token|verifier code" issues open_source_plan.md`
- Manual read-through of modified issue files for clarity

## Acceptance Criteria
- [ ] No personal absolute filesystem paths remain in public markdown docs
- [ ] No one-time auth transcript values remain in tracked docs
- [ ] Doc examples are portable and repo-relative where possible

