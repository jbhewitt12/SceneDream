# Document Dashboard Filtering and Sorting

## Overview
Add client-side filtering and sorting controls to the Documents dashboard that work seamlessly with the existing search bar. Preferences persist across sessions via localStorage.

## Problem Statement
The Documents dashboard currently shows all documents in alphabetical order with only a text search bar for narrowing results. As the document library grows, users need to quickly find documents by pipeline readiness, file type, or activity recency, and sort the list by meaningful metrics like last activity or image count.

## Proposed Solution
Add inline filter/sort controls next to the existing search bar:
- **Pipeline readiness toggle**: Two-state toggle ("Ready" / "Not Ready") filtering documents by whether both extraction and ranking are completed.
- **Source type filter**: Dropdown to filter by file extension (epub, docx, txt, etc.), dynamically populated from the documents currently loaded.
- **Sort dropdown**: Options for Last Updated, Alphabetical (A-Z), Alphabetical (Z-A), and Images Generated (most first).
- **Persistence**: All filter/sort selections saved to localStorage and restored on page load.

All filtering (search + readiness toggle + source type) and sorting are applied client-side via `useMemo`, composing with the existing search filter.

## Codebase Research Summary

### Current search implementation (`documents.tsx:281-292`)
- Client-side `useMemo` filter on `dashboardQuery.data?.data`
- Matches `display_name`, `source_path`, `slug` case-insensitively
- No server-side filtering; all data loaded upfront

### Available data per document (`DocumentDashboardEntry`)
- `stages.extraction.status` / `stages.ranking.status` - for readiness filter
- `source_type` - for file type filter (values: epub, mobi, azw, azw3, txt, md, docx)
- `last_run.updated_at` / `last_run.completed_at` - for "last updated" sort
- `counts.images_generated` - for images sort
- `display_name` - for alphabetical sort

### UI patterns in use
- Chakra UI v3: `HStack`, `Box`, `Input`, `Badge`, `NativeSelectRoot`/`NativeSelectField`/`NativeSelectIndicator`
- `SegmentedControl` from `@/components/ui/segmented-control` or Chakra recipes could be used for the toggle
- The settings page uses `NativeSelectRoot` for dropdowns (reference: `PromptArtStyleControl.tsx`)

### Settings persistence pattern
- `AppSettings` is DB-backed singleton for pipeline defaults
- Decision: Use `localStorage` for dashboard UI preferences (simpler, no migration needed, purely a UI concern)

### Dashboard service sort (`document_dashboard_service.py:147`)
- Backend currently sorts alphabetically by `source_path.lower()`
- All sorting will remain client-side since all data is already loaded

## Key Decisions
1. **Ready/Not Ready toggle** - "Ready" means both extraction AND ranking statuses are "completed". Everything else is "Not Ready". Toggle is two-state (not tri-state), with an "All" default when neither is selected.
2. **Unrun documents sort to bottom** when ordering by "Last Updated" (documents with no pipeline runs have no activity timestamp).
3. **localStorage persistence** - No backend changes needed. Preferences are stored under a single localStorage key and restored on mount.
4. **Inline layout** - Filter toggle + sort dropdown sit in the same row as the search bar (search left, controls right, badge at end).
5. **Source type filter** - Dynamically populated from the distinct `source_type` values in the current dashboard data, with an "All types" default.

## Implementation Plan

### Phase 1: Define filter/sort types and localStorage helpers
**Goal**: Create the data types and persistence layer for dashboard preferences.

**Tasks**:
- Create `frontend/src/features/documents/documentDashboardPreferences.ts` with:
  - Type `DocumentDashboardPreferences` containing `readinessFilter: "all" | "ready" | "not_ready"`, `sourceTypeFilter: string` (empty string = all), `sortOrder: "last_updated" | "alpha_asc" | "alpha_desc" | "images_desc"`
  - Default preferences constant: `{ readinessFilter: "all", sourceTypeFilter: "", sortOrder: "last_updated" }`
  - `loadDashboardPreferences(): DocumentDashboardPreferences` - reads from localStorage with fallback to defaults
  - `saveDashboardPreferences(prefs: DocumentDashboardPreferences): void` - writes to localStorage
- localStorage key: `"scenedream:document-dashboard-preferences"`

**Verification**:
- [ ] Types compile with `npm run build` (or `npx tsc --noEmit`)
- [ ] Unit-testable pure functions

### Phase 2: Add filter/sort controls to the documents page UI
**Goal**: Render the toggle, source type dropdown, and sort dropdown inline with the search bar.

**Tasks**:
- In `frontend/src/routes/_layout/documents.tsx`:
  - Import `DocumentDashboardPreferences`, `loadDashboardPreferences`, `saveDashboardPreferences` from the new module
  - Add state: `const [preferences, setPreferences] = useState(loadDashboardPreferences)`
  - Create helper `updatePreference(patch: Partial<DocumentDashboardPreferences>)` that merges into state and calls `saveDashboardPreferences`
  - Compute `distinctSourceTypes` via `useMemo` from `dashboardQuery.data?.data` (sorted unique `source_type` values)
  - In the search bar `HStack` row, after the search `Input` and before the `Badge`, add:
    - **Readiness filter**: Three-segment control or three `Button` variants ("All", "Ready", "Not Ready") using Chakra's `SegmentedControl` or simple button group. Value bound to `preferences.readinessFilter`, onChange calls `updatePreference`.
    - **Source type dropdown**: `NativeSelectRoot` with options "All types" + each distinct source type. Value bound to `preferences.sourceTypeFilter`, onChange calls `updatePreference`.
    - **Sort dropdown**: `NativeSelectRoot` with options "Last Updated", "A-Z", "Z-A", "Most Images". Value bound to `preferences.sortOrder`, onChange calls `updatePreference`.

**Verification**:
- [ ] Controls render correctly on the documents page
- [ ] Selecting a filter/sort updates state and persists to localStorage
- [ ] Refreshing the page restores the saved preferences

### Phase 3: Wire up filtering and sorting logic
**Goal**: Compose the new filters with the existing search filter and apply the selected sort.

**Tasks**:
- In `frontend/src/routes/_layout/documents.tsx`, replace the existing `filteredEntries` useMemo with a combined filter+sort pipeline:
  1. Start with `dashboardQuery.data?.data ?? []`
  2. Apply text search filter (existing logic)
  3. Apply readiness filter: if `"ready"`, keep only entries where `stages.extraction.status === "completed" && stages.ranking.status === "completed"`; if `"not_ready"`, keep entries where either is NOT "completed"; if `"all"`, no filter
  4. Apply source type filter: if non-empty, keep only entries where `source_type === preferences.sourceTypeFilter`
  5. Apply sort:
     - `"last_updated"`: sort by `last_run?.updated_at` descending (nulls to bottom)
     - `"alpha_asc"`: sort by `display_name.toLowerCase()` ascending
     - `"alpha_desc"`: sort by `display_name.toLowerCase()` descending
     - `"images_desc"`: sort by `counts.images_generated` descending
- Add `preferences` to the `useMemo` dependency array

**Verification**:
- [ ] Text search + readiness filter + source type filter compose correctly (AND logic)
- [ ] Each sort order works as expected
- [ ] "N shown" badge reflects the combined filtered count
- [ ] Documents with no pipeline runs sort to the bottom in "Last Updated" mode

### Phase 4: Polish and edge cases
**Goal**: Handle edge cases and responsive layout.

**Tasks**:
- Ensure the controls wrap gracefully on small screens (use `wrap="wrap"` on the HStack)
- If the source type dropdown has only one unique type, still show the dropdown but it's effectively a no-op
- If `preferences.sourceTypeFilter` references a source type that no longer exists in the data (e.g., document was removed), treat it as "All types" gracefully
- Run `cd frontend && npm run lint` and fix any Biome issues

**Verification**:
- [ ] Layout doesn't break on narrow viewports
- [ ] Stale source type preference doesn't cause errors
- [ ] `npm run lint` passes
- [ ] `npm run build` passes (or `npx vite build`)

## Files to Modify
| File | Action |
|------|--------|
| `frontend/src/features/documents/documentDashboardPreferences.ts` | Create |
| `frontend/src/routes/_layout/documents.tsx` | Modify |

## Testing Strategy
- **Unit Tests**: None required (pure frontend, no new API endpoints or backend changes)
- **Manual Verification**:
  - Toggle "Ready"/"Not Ready" and confirm only matching documents appear
  - Select a source type and confirm only that type shows
  - Change sort order and confirm document card order changes
  - Combine search text + readiness filter + source type filter and confirm AND behavior
  - Refresh the page and confirm preferences are restored
  - Clear localStorage and confirm defaults are applied

## Acceptance Criteria
- [ ] Readiness toggle filters documents by extraction+ranking completion status
- [ ] Source type dropdown filters by file extension
- [ ] Sort dropdown orders by last updated, alphabetical (asc/desc), or images generated
- [ ] All filters compose with the existing text search (AND logic)
- [ ] Selected preferences persist in localStorage and restore on page load
- [ ] "N shown" badge reflects the combined filtered+sorted result count
- [ ] Controls sit inline with the search bar and wrap on small screens
- [ ] `npm run lint` passes
- [ ] `npx vite build` passes
