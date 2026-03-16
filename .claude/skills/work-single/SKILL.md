---
description: Work on the next incomplete phase of an issue
argument-hint: "[issue-number]"
---

# /work-single command

Work on only the next incomplete phase of an issue implementation plan.

1. Find the issue file in the `/issues` folder that starts with this number: $ARGUMENTS
2. Read the **entire** issue file before making any changes.

## Determine the next phase

3. Identify the earliest phase in the implementation plan that is not fully completed yet. Use the implementation notes at the bottom of the issue (if any exist from prior phases) and the current codebase to decide this. If a phase is partially complete, treat that phase as the next phase and finish only that phase. Do not start a later phase.

## Implement exactly that phase

4. Your job is to implement exactly that next incomplete phase, and only that phase.

### Working rules

- Inspect the current codebase first. Do not assume the issue notes are perfectly accurate -- the codebase is the source of truth.
- Stay inside the scope of the selected phase.
- Do not pull work forward from later phases, even if it seems related or convenient.
- Preserve existing behavior unless the selected phase explicitly changes it.
- If the selected phase depends on a missing prerequisite from an earlier phase, stop, explain the blocker, and record it in the issue notes instead of jumping ahead.
- Keep route handlers async/non-blocking as required by the repo guidelines.
- Follow the repo testing requirements for any new or changed services, routes, or repositories.
- Add or update the tests that belong to the selected phase.
- Run the relevant tests and verification commands for the selected phase. Do not claim they passed unless you actually ran them.
- If you discover the phase plan needs a small adjustment to match the real codebase, make the minimal safe adjustment and document it clearly in the issue notes.

## Completion standard

A phase is complete only when:
- Its scoped code changes are implemented.
- Its required tests are added or updated.
- The relevant verification for that phase has been run, or any failure/blocker is explicitly documented.

Do **not** mark a phase complete if major tasks from that phase remain unfinished.

## Update the issue notes

5. After implementation, update the issue file by appending a new section at the bottom with this exact structure:

```
## Phase Implementation Notes

### Phase N: <Phase Title>
- Status: completed | partially completed | blocked
- Summary: brief description of what was implemented
- Completed work:
  - ...
- Remaining work in this phase:
  - ...
- Deviations from plan:
  - none | ...
- Tests and verification run:
  - ...
- Known issues / follow-ups for next agent:
  - ...
- Files changed:
  - ...
```

### Rules for the notes

- Replace `Phase N` with the actual phase number and title from the plan.
- Be concrete and factual.
- Distinguish clearly between what is done and what is still not done.
- Mention any behavioral differences from the original plan.
- Mention exact tests/commands run and whether they passed or failed.
- Make the notes sufficient for the next agent to confidently pick up the next incomplete phase without re-discovering your intent.
- Do not edit or rewrite earlier implementation notes except to correct something clearly inaccurate and only if necessary.

## Commit

6. When finished, commit only the changes for this phase with a focused commit message.
