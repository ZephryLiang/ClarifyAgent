# Release process

## Version bump

1. Update `APP_VERSION` in [`backend/app/config.py`](../backend/app/config.py)
2. Add section to [`CHANGELOG.md`](../CHANGELOG.md)
3. Write release note under `docs/releases/vX.Y.Z-<slug>.md`
4. Seed release in `SystemReleaseLog.ensure_seeded()` or insert via `system_releases` table

## H2 system change log

Product-facing changes (new modules, API routes, breaking UX) should append to `system_change_events` via `SystemReleaseLog.record_change()`.

User activity (JD pasted, match run) goes to **H1** `activity_events` only — never mix with H2.

## Checklist before release

- [ ] `pytest` passes in `backend/`
- [ ] `npm run build` passes in `frontend/`
- [ ] Copilot offline smoke: paste JD → ask intent → quick match
- [ ] CHANGELOG + release doc updated
- [ ] Version banner shows new version once (`GET /api/meta/version`)

## Current versions

| Version | Summary |
|---------|---------|
| 0.1.0 | Tab-driven baseline |
| 0.2.0 | Chat-first Copilot + Gap bridge + dual-track logging |
