# Wire Random Style Mix and Single Art Style Through Settings and Documents Dashboard

## Overview
Update the frontend so users can choose between `Random Style Mix` and a single custom art style in both:
- `Pipeline Defaults` on the Settings page
- `Launch Pipeline` on each document card in the Documents dashboard

This issue covers frontend copy, state management, API wiring, and UX clarity. It does not cover the prompt-builder implementation itself.

## Problem Statement
The current frontend still models art style as a dropdown backed by catalog IDs:
- Settings exposes `Default art style` as a select
- Documents dashboard exposes `Art style override` as a select with `Use global default`

That UI no longer matches the intended product:
- users need to choose a behavior, not just a list item
- `Use global default` is misleading because the current behavior is a random sampled mix, not a fixed style
- users must be able to enter any single art style as free text
- the UI should explicitly teach that `Random Style Mix` samples from the art styles configured in Settings

## Proposed Solution
Refactor both screens to use an explicit mode switch:
- `Random Style Mix`
- `Single art style`

When `Single art style` is selected, show a text input.
When `Random Style Mix` is selected, show high-clarity helper copy explaining that styles are randomly selected from the Settings lists.

## Codebase Research Summary

### Current Documents dashboard implementation
- `frontend/src/routes/_layout/documents.tsx`
  - stores a per-card `artStyleOverrideValue` string
  - renders `Art style override` as a `NativeSelect`
  - shows `Use global default` as the empty option

### Current Settings implementation
- `frontend/src/routes/_layout/settings.tsx`
  - stores `defaultArtStyleId`
  - renders `Default art style` as a `NativeSelect`
  - already contains explanatory copy about style sampling in the `Art Styles` section

### UX change required
- the product name for the sampled behavior is now `Random Style Mix`
- the default setting determines the default mode/value shown in the Documents dashboard

## Key Decisions
- Use the product label `Random Style Mix` everywhere in frontend copy.
- Replace "Use global default" wording in the Documents dashboard.
- Both Settings and Documents dashboard should use the same conceptual model:
  - mode selection first
  - conditional text input second
- The `Default art style` control in Settings defaults to `Random Style Mix`.
- Documents dashboard cards initialize from the saved default mode/text from Settings.
- Maximum-clarity helper copy should be visible when `Random Style Mix` is selected:
  - `Randomly samples from the art styles in Settings, weighted toward Recommended styles.`
- Add a second line or adjacent helper to point users to Settings:
  - `Manage the style lists in Settings.`
- Do not add a new frontend E2E test suite; manual browser verification belongs in a separate issue.

## Implementation Plan

### Phase 1: Update API client usage and local state models
**Goal**: align frontend state with the new backend contract.

**Tasks**:
- Update settings API wrappers and generated types after backend schema changes.
- Replace UUID-based frontend state with explicit mode/text state in:
  - Settings page
  - Documents dashboard card state
- Use a shared local type, for example:
  - `promptArtStyleMode: "random_mix" | "single_style"`
  - `promptArtStyleText: string`

**Verification**:
- [ ] Frontend compiles against the new API contract
- [ ] Card state and settings state both support mode/text

### Phase 2: Redesign `Pipeline Defaults` in Settings
**Goal**: make the saved default explicit and understandable.

**Tasks**:
- Update `Default art style` in `frontend/src/routes/_layout/settings.tsx` to render:
  - `Random Style Mix`
  - `Single art style`
- Show a text input only when `Single art style` is selected.
- Default the control to `Random Style Mix`.
- Add helper copy explaining that `Random Style Mix` uses the style lists configured below on the same page.
- Preserve existing save/reset behavior and dirty-state logic.

**Verification**:
- [ ] Users can save `Random Style Mix` as the default
- [ ] Users can save a custom single style as the default
- [ ] Reset returns the control to the last-saved mode/text

### Phase 3: Redesign Documents dashboard launch control
**Goal**: make per-run override behavior explicit and easy to use.

**Tasks**:
- Replace `Art style override` select in `frontend/src/routes/_layout/documents.tsx` with an `Art style` control section.
- Render the same two options:
  - `Random Style Mix`
  - `Single art style`
- When `Random Style Mix` is selected, show helper copy:
  - `Randomly samples from the art styles in Settings, weighted toward Recommended styles.`
  - `Manage the style lists in Settings.`
- When `Single art style` is selected, show a text input with placeholder examples.
- Initialize each card from the saved Settings default mode/text.
- Allow users to switch modes per document card without losing previously typed custom text on that card.

**Verification**:
- [ ] Documents dashboard cards load the saved default mode/text
- [ ] Per-card changes do not leak into other cards
- [ ] Switching between modes preserves typed custom style text locally

### Phase 4: Submit launch requests using the new mode/text fields
**Goal**: ensure the selected behavior actually reaches the backend.

**Tasks**:
- Update `frontend/src/api/pipelineRuns.ts` and launch payload creation in `documents.tsx`.
- When mode is `random_mix`, send mode and omit/clear style text.
- When mode is `single_style`, send mode and trimmed style text.
- Add client-side validation to prevent blank submissions in `single_style` mode.

**Verification**:
- [ ] Network payload matches the selected mode
- [ ] Blank custom style cannot be launched

### Phase 5: Rename user-facing copy consistently
**Goal**: eliminate ambiguous terminology.

**Tasks**:
- Replace frontend strings that imply "global default art style" with `Random Style Mix` or mode-aware text.
- Update any helper, placeholder, or summary text that still says `default art style` when it means sampled behavior.
- Preserve `Default art style` as the Settings field label if desired, but ensure the selectable default value is named `Random Style Mix`.

**Verification**:
- [ ] No user-facing Documents dashboard copy says `Use global default`
- [ ] Random sampled behavior is consistently named `Random Style Mix`

## Files to Modify
| File | Action |
|------|--------|
| `frontend/src/routes/_layout/settings.tsx` | Modify |
| `frontend/src/routes/_layout/documents.tsx` | Modify |
| `frontend/src/api/settings.ts` | Modify |
| `frontend/src/api/pipelineRuns.ts` | Modify |
| `frontend/src/client/types.gen.ts` | Regenerate |
| `frontend/src/client/sdk.gen.ts` | Regenerate if needed |

## Testing Strategy
- Frontend static checks:
  - `cd frontend && npm run lint`
- Manual local verification:
  - save defaults in Settings for both modes
  - reload and confirm persistence
  - confirm Documents dashboard picks up the saved default mode/text
  - confirm launch payload changes with the selected mode

## Acceptance Criteria
- [ ] Settings `Pipeline Defaults` supports `Random Style Mix` and `Single art style`
- [ ] Documents dashboard launch UI supports `Random Style Mix` and `Single art style`
- [ ] `Random Style Mix` is the user-facing name everywhere in the frontend
- [ ] Random mix helper text clearly explains that styles come from Settings
- [ ] Documents dashboard defaults are sourced from saved Settings mode/text
- [ ] `single_style` mode exposes a text input and prevents blank launches
- [ ] `cd frontend && npm run lint` passes
