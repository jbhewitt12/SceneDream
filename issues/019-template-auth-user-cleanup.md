# Template Auth/User Cleanup for Open-Source Release

## Overview
SceneDream is a local single-operator system and does not require users, login, signup, password recovery, or role-based access control. This plan removes leftover FastAPI template auth/user/item logic so the repository is easier for open-source contributors to understand and extend.

## Problem Statement
- **Current issue**: Legacy template modules still expose user/login/items/private APIs and related support code.
- **Contributor impact**: New contributors see two competing architectures (pipeline domain vs. template auth domain), which creates confusion and increases onboarding time.
- **Operational impact**: CI/workflows/env settings still carry superuser and auth assumptions that are not part of the product.

## Data Preservation Requirement
- Existing operational SceneDream data must be preserved (scene extractions, scene rankings, image prompts, generated images, documents, pipeline runs, generated assets, social posting data, and related records).
- Do not delete or truncate any database entries that represent SceneDream pipeline work.
- It is acceptable to remove template-only auth data structures and tables that are not part of SceneDream domain behavior (for example `user` and `item`) after verification.
- Initial cleanup should remove runtime references first and keep legacy template tables in place.
- A later explicit migration can archive/drop template-only tables after validation and rollback planning.

## Proposed Solution
- Remove unused auth/user/item API endpoints and dependencies.
- Remove template user/item models and CRUD/auth helpers.
- Remove superuser bootstrap and related environment variables.
- Remove frontend/template UI and generated client endpoints tied to auth/items.
- Remove stale auth test scaffolding and Playwright auth flows.
- Update docs and CI/workflows to match the no-auth architecture.

## Codebase Research Summary

### Backend auth/template surface still present
- Routes:
  - `backend/app/api/routes/login.py`
  - `backend/app/api/routes/users.py`
  - `backend/app/api/routes/items.py`
  - `backend/app/api/routes/private.py`
- Router registration:
  - `backend/app/api/main.py`
  - `backend/app/api/routes/__init__.py`
- Auth deps:
  - `backend/app/api/deps.py` (`OAuth2PasswordBearer`, current user/superuser helpers)
- Template model/CRUD layer:
  - `backend/app/models.py` (User/Item/Token/etc.)
  - `backend/app/crud.py`
  - `backend/app/core/security.py`
  - `backend/app/utils.py` (password reset/new account email helpers)
- Startup/bootstrap:
  - `backend/app/core/db.py` (`init_db` creates first superuser)
  - `backend/app/initial_data.py`
  - `backend/scripts/prestart.sh`

### Frontend/template surface still present
- Legacy items route/components:
  - `frontend/src/routes/_layout/items.tsx`
  - `frontend/src/components/Items/*`
  - `frontend/src/components/Common/ItemActionsMenu.tsx`
- Generated client still includes login/users/items/private endpoints:
  - `frontend/src/client/sdk.gen.ts`
  - `frontend/src/client/types.gen.ts`
  - `frontend/src/client/schemas.gen.ts`
  - `frontend/openapi.json`

### Infrastructure/docs/workflows still present
- Env + compose:
  - `.env`
  - `docker-compose.yml` (`FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`)
- Workflows:
  - `.github/workflows/deploy-staging.yml`
  - `.github/workflows/deploy-production.yml`
  - `.github/workflows/generate-client.yml`
  - `.github/workflows/playwright.yml` (template auth flows)
- Docs:
  - `README.md`
  - `backend/README.md`
  - `frontend/README.md`
  - `deployment.md`

## Key Decisions
- **Two-phase DB strategy**: runtime cleanup first, schema drop later.
- **No replacement auth**: endpoints remain open unless explicitly guarded for non-auth reasons.
- **Minimal shared primitives**: keep a small common response schema (e.g., `Message`) outside template model module.
- **Regenerate generated artifacts**: OpenAPI and frontend client must be regenerated after route removals.

## Implementation Plan

### Phase 1: Remove Legacy API Routes and Auth Deps
**Goal**: Remove all user/login/items/private endpoints and authentication dependency code.

**Tasks**:
1. Delete:
   - `backend/app/api/routes/login.py`
   - `backend/app/api/routes/users.py`
   - `backend/app/api/routes/items.py`
   - `backend/app/api/routes/private.py`
2. Update:
   - `backend/app/api/main.py` (remove router includes)
   - `backend/app/api/routes/__init__.py` (remove module exports)
3. Simplify `backend/app/api/deps.py` to DB session dependency only.
4. Update any routes still importing auth/superuser helpers (notably `utils` route behavior).

**Verification**:
- [ ] OpenAPI no longer contains `/login`, `/users`, `/items`, `/private` paths
- [ ] Backend imports resolve without auth modules
- [ ] Existing pipeline routes still load

---

### Phase 2: Remove Template Model, CRUD, and Security Helpers
**Goal**: Eliminate template user/item domain code and keep only needed shared schemas/utilities.

**Tasks**:
1. Remove template model module usage:
   - `backend/app/models.py`
2. Move any still-needed generic response schema (e.g., `Message`) into a non-template location (e.g., `backend/app/schemas/common.py`) and update imports.
3. Delete:
   - `backend/app/crud.py`
   - `backend/app/core/security.py` (if no longer referenced)
4. Remove auth/password-reset/new-account helpers in:
   - `backend/app/utils.py`
5. Update Alembic metadata wiring in:
   - `backend/app/alembic/env.py`
   to avoid relying on template model imports.

**Verification**:
- [ ] No runtime imports from `app.models` for User/Item/Token types
- [ ] No references to password hashing/JWT helpers unless required elsewhere
- [ ] Alembic env still resolves metadata correctly

---

### Phase 3: Remove Superuser Bootstrap and Auth Env Settings
**Goal**: Remove automatic superuser creation and related configuration requirements.

**Tasks**:
1. Remove startup bootstrap logic:
   - `backend/app/core/db.py`
   - `backend/app/initial_data.py`
   - `backend/scripts/prestart.sh` (skip initial user seeding)
2. Remove auth-specific settings from:
   - `backend/app/core/config.py`
   - `.env`
3. Update compose env wiring in `docker-compose.yml` to remove `FIRST_SUPERUSER*`.

**Verification**:
- [ ] Backend starts without `FIRST_SUPERUSER*` env vars
- [ ] Prestart/migrations still execute successfully
- [ ] No startup path attempts to create users

---

### Phase 4: Remove Frontend Template Items/Auth Surface
**Goal**: Remove legacy items UI and generated auth client methods from frontend.

**Tasks**:
1. Delete legacy items route/components:
   - `frontend/src/routes/_layout/items.tsx`
   - `frontend/src/components/Items/AddItem.tsx`
   - `frontend/src/components/Items/EditItem.tsx`
   - `frontend/src/components/Items/DeleteItem.tsx`
   - `frontend/src/components/Common/ItemActionsMenu.tsx`
2. Regenerate route tree and OpenAPI client artifacts:
   - `frontend/src/routeTree.gen.ts`
   - `frontend/src/client/*`
   - `frontend/openapi.json`
   - root `openapi.json`
3. Remove any lingering references to items route imports/usages.

**Verification**:
- [ ] Frontend builds without items route/components
- [ ] Generated client has no auth/items/private service methods
- [ ] Navigation only includes active SceneDream features

---

### Phase 5: Remove Auth Test Scaffolding and Template E2E Flows
**Goal**: Drop test code that depends on login/users/superuser assumptions.

**Tasks**:
1. Cleanup backend test fixtures/utils:
   - `backend/app/tests/conftest.py`
   - `backend/app/tests/utils/user.py`
   - `backend/app/tests/utils/item.py`
   - `backend/app/tests/utils/utils.py`
2. Remove Playwright auth/signup/reset-password template tests:
   - `frontend/tests/login.spec.ts`
   - `frontend/tests/sign-up.spec.ts`
   - `frontend/tests/reset-password.spec.ts`
   - `frontend/tests/user-settings.spec.ts`
   - related helpers in `frontend/tests/utils/*`
3. Update workflow assumptions for removed tests.

**Verification**:
- [ ] Backend tests do not request auth tokens
- [ ] No frontend test references `/login` or `/signup`
- [ ] CI test jobs pass with updated test scope

---

### Phase 6: Update CI, Deployment Config, and Documentation
**Goal**: Align automation and docs with the no-auth open-source architecture.

**Tasks**:
1. Update workflows to remove superuser secrets/vars:
   - `.github/workflows/deploy-staging.yml`
   - `.github/workflows/deploy-production.yml`
   - `.github/workflows/generate-client.yml`
2. Remove/replace Playwright auth workflow if no longer needed:
   - `.github/workflows/playwright.yml`
3. Refresh docs to remove template auth language:
   - `README.md`
   - `backend/README.md`
   - `frontend/README.md`
   - `deployment.md`

**Verification**:
- [ ] No workflow expects `FIRST_SUPERUSER*`
- [ ] Docs describe SceneDream architecture (not template auth)
- [ ] New contributor setup has no login/user prerequisites

---

### Phase 7: Optional Post-Cleanup DB Migration
**Goal**: Safely retire template-only tables (for example `user`/`item`) after runtime is fully migrated off them, without deleting SceneDream project-work data.

**Tasks**:
1. Create explicit migration plan:
   - pre-check row counts
   - archive/export strategy (if needed)
   - FK/index checks
2. Add migration to drop legacy tables only after verification.
3. Record before/after validation in issue completion notes.

**Verification**:
- [ ] Data preservation checks documented
- [ ] Migration tested on a DB snapshot
- [ ] No runtime references to dropped tables remain
- [ ] No SceneDream domain records were deleted or truncated as part of cleanup

## Acceptance Criteria
- [ ] Backend has no user/login/items/private routes
- [ ] Backend has no JWT/superuser bootstrap requirements
- [ ] Frontend has no items/auth template UI
- [ ] OpenAPI/client artifacts are regenerated and clean
- [ ] CI/workflows/docs are aligned with no-auth architecture
- [ ] Existing operational pipeline features remain functional
- [ ] No SceneDream project-work database entries are deleted during this cleanup

## Quick Reference Commands
```bash
# Backend checks
cd backend && uv run pytest
cd backend && uv run bash scripts/lint.sh

# Regenerate OpenAPI + frontend client
./scripts/generate-client.sh

# Frontend checks
cd frontend && npm run lint
cd frontend && npm run build
```

## 3-Session Execution Status
- [x] Macro-Phase 1: Backend cleanup
- [x] Macro-Phase 2: Frontend/client/tests cleanup
- [x] Macro-Phase 3: CI/docs + optional template-table retirement

## Completion Notes

### Phase Completion Notes Structure
- Phase name
- Date completed
- Files changed
- Validation run
- Any deviations from plan

### Macro-Phase 1: Backend cleanup
- Date completed: 2026-03-03
- Files changed: `issues/019-template-auth-user-cleanup.md` (status tracking update only in this session)
- Validation run:
  - `./scripts/generate-client.sh` (failed: system `python` missing `fastapi`)
  - Equivalent regeneration run manually with `uv run` backend OpenAPI export + frontend client generation (succeeded; no artifact diffs)
  - `cd backend && uv run pytest` (failed: test scaffolding still imports removed `init_db` from `app.core.db`)
  - `cd backend && uv run bash scripts/lint.sh` (failed: pre-existing mypy issues, including legacy test imports of removed `app.models`)
- Deviations from plan:
  - Backend phase 1-3 code cleanup already existed before this session; this session re-verified and updated execution tracking.

### Macro-Phase 2: Frontend/client/tests cleanup
- Date completed: 2026-03-03
- Files changed:
  - `frontend/src/routes/_layout/items.tsx` (deleted)
  - `frontend/src/components/Items/AddItem.tsx` (deleted)
  - `frontend/src/components/Items/EditItem.tsx` (deleted)
  - `frontend/src/components/Items/DeleteItem.tsx` (deleted)
  - `frontend/src/components/Common/ItemActionsMenu.tsx` (deleted)
  - `frontend/src/routeTree.gen.ts` (regenerated; items route removed)
  - `frontend/src/client/schemas.gen.ts` (deleted stale generated artifact)
  - `frontend/tests/auth.setup.ts` (deleted)
  - `frontend/tests/config.ts` (deleted)
  - `frontend/tests/login.spec.ts` (deleted)
  - `frontend/tests/sign-up.spec.ts` (deleted)
  - `frontend/tests/reset-password.spec.ts` (deleted)
  - `frontend/tests/user-settings.spec.ts` (deleted)
  - `frontend/tests/utils/mailcatcher.ts` (deleted)
  - `frontend/tests/utils/privateApi.ts` (deleted)
  - `frontend/tests/utils/random.ts` (deleted)
  - `frontend/tests/utils/user.ts` (deleted)
  - `frontend/playwright.config.ts` (removed auth setup dependency/storage state)
  - `backend/app/tests/conftest.py` (removed auth/superuser fixture and template model references)
  - `backend/app/tests/utils/item.py` (deleted)
  - `backend/app/tests/utils/user.py` (deleted)
  - `backend/app/tests/utils/utils.py` (deleted)
- Validation run:
  - `./scripts/generate-client.sh` (failed: system `python` missing `fastapi`)
  - Equivalent regeneration run manually with `uv run` backend OpenAPI export + frontend `npm run generate-client` (succeeded)
  - `cd frontend && npx vite build` (succeeded; route tree regenerated)
  - `cd frontend && npm run lint` (succeeded; auto-fixed 1 file)
  - `cd frontend && npm run build` (failed due pre-existing TypeScript/Chakra typing issues unrelated to items/auth cleanup)
  - `cd backend && uv run pytest` (succeeded: 113 passed, 7 deselected)
  - `cd backend && uv run bash scripts/lint.sh` (failed: pre-existing mypy issues in non-auth files)
- Deviations from plan:
  - `npm run build` did not pass due unrelated pre-existing frontend type errors; no additional fixes made outside this macro-phase scope.

### Macro-Phase 3: CI/docs + optional template-table retirement
- Date completed: 2026-03-03
- Files changed:
  - `.github/workflows/deploy-staging.yml` (removed `FIRST_SUPERUSER*` secret wiring)
  - `.github/workflows/deploy-production.yml` (removed `FIRST_SUPERUSER*` secret wiring)
  - `.github/workflows/generate-client.yml` (removed `FIRST_SUPERUSER_PASSWORD` env for client generation)
  - `README.md` (replaced template-auth docs with SceneDream no-auth project docs)
  - `backend/README.md` (updated backend guide to current SceneDream structure and no-auth behavior)
  - `frontend/README.md` (updated frontend guide and client generation instructions)
  - `deployment.md` (removed superuser/auth assumptions and documented no-auth deployment vars)
  - `issues/019-template-auth-user-cleanup.md` (status + completion notes)
- Validation run:
  - `cd backend && uv run pytest` (succeeded: 113 passed, 7 deselected)
  - `cd backend && uv run bash scripts/lint.sh` (failed: pre-existing mypy issues in non-auth files)
  - `./scripts/generate-client.sh` (failed: script uses system `python`, missing `fastapi`)
  - Equivalent regeneration run manually with `uv run` backend OpenAPI export + frontend `npm run generate-client` (succeeded)
  - `cd frontend && npm run lint` (succeeded; auto-fixed 1 file)
  - `cd frontend && npm run build` (failed due pre-existing TypeScript/Chakra typing issues unrelated to this macro-phase)
- Deviations from plan:
  - Optional template-table retirement (`user`/`item`) was intentionally deferred in this session. Safe checks for destructive schema changes on a protected DB snapshot were not performed here, so no table-drop migration was created or applied.
