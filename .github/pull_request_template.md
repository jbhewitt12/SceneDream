## Summary

Describe what changed and why.

## Related Issues

Link issues using closing keywords when applicable (for example: `Closes #123`).

## Validation

List checks run locally and their results.

- [ ] `cd backend && uv run bash scripts/lint.sh`
- [ ] `cd backend && uv run pytest`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run build`
- [ ] `./scripts/generate-client.sh` (if API contract changed)

## Screenshots / Recordings (UI changes)

Add before/after screenshots or a short recording when relevant.

## Checklist

- [ ] Scope is focused and does not include unrelated refactors.
- [ ] New behavior includes tests or docs updates as needed.
- [ ] External API calls in unit tests are mocked.
- [ ] No secrets were added to source control.
