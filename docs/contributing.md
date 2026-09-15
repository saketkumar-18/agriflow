# AgriFlow — Contributing Guide

For anyone sending code to this repo. Read docs/architecture.md first; the API surface is **frozen**
in docs/api-contract.md — changing it requires an explicit contract amendment PR reviewed before
any implementation.

## 1. Branching & PR flow

```
main ──── protected: always releasable, PRs only
  └─ feat/<area>-<summary>     e.g. feat/api-rain-deferral
  └─ fix/<area>-<summary>
  └─ docs/<summary>
```

1. Branch from fresh `main`. One logical change per PR; keep diffs reviewable (< ~400 lines where
   possible).
2. Commit messages: imperative, scoped — `api: clamp recommendation depth per method`, not
   `wip`, `updates`.
3. PR description must state: what/why, **spec sections touched** (§n refs), how tested, and any
   UI strings added → their i18n keys (§30).
4. Merge requires: CI green + review. No direct pushes to `main`; no self-merge on feature PRs.
5. Database changes ship **with an Alembic migration** in the same PR (§76.11); a model change
   without a migration revision closes the PR from CI.

## 2. Tests are required — no exceptions (§57, §75)

- New logic ⇒ new tests in the same PR. Bug fix ⇒ a regression test that fails before the fix.
- **The irrigation engine has the strictest bar**: every rule, threshold edge, water calculation,
  efficiency factor, confidence factor, and urgency mapping has unit tests (docs/irrigation-engine.md
  §12 lists the pinned cases). Engine math must stay pure/importable and testable without HTTP (§76.8).
- Minimum suite shapes (§57): unit (rules/math/thresholds/matching), integration
  (user→farm→field→weather→recommendation→irrigation event), E2E (critical farmer journey).
- Do not delete or skip tests to go green; fix the cause or raise the disagreement in review.
- Honesty property tests must keep passing: nothing emits measured labels for estimated values,
  `available:false` never produces fabricated weather rows, demo rows always carry `demo:true`
  (§72, §76.15–17).

Local run (see docs/setup.md §4):

```bash
cd services/api && pytest && ruff check . && mypy app
cd apps/web && npm run lint && npx tsc --noEmit && npm run test
```

## 3. i18n rule — no hard-coded user-facing strings (§30, §67)

**Every** user-visible string comes from translation files. This is enforced, not folklore:

- Backend never returns prose: reasons/warnings/confidence/labels ship as
  `{key, params}` against the shared namespaces (`reasons.*, warnings.*, conf.*, time.*, rec.*,
  alerts.*, errors.*, …`) defined in the contract's i18n section.
- Frontend reads from `i18n/en.json` + `i18n/hi.json` (single source of keys); components contain
  no string literals for UI text. ESLint rule flags JSX text/constants where a key is expected.
- Adding a string = adding the key to **both** en and hi in the same PR (CI fails on missing keys
  either direction; a recommendation whose reason key lacks a translation violates AC-10's
  contract, see irrigation-engine.md §10.5).
- New languages (Punjabi, Marathi, …) are just new files in `i18n/` — never fork logic per locale
  (§30). Numbers/units stay formatted per-locale at the render boundary.

## 4. Lint, format, types — commands

Backend (`services/api`, run from that dir; dev extras installed):

```bash
ruff check .            # lint
ruff check . --fix      # autofix
ruff format .           # format (black-compatible)
mypy app                # type hints required everywhere (§76.2)
pytest -x               # fast fail loop
```

Frontend (`apps/web`):

```bash
npm run lint            # eslint (TS strict; avoid `any` — §76.3)
npx prettier --write .  # format
npx tsc --noEmit        # strict type check
npm run build           # must stay green — production build is a DoD item (§75)
```

CI runs exactly these plus integration/E2E legs (§56): lint → type checks → unit → integration →
build. Formatting arguments are over: the formatter decides.

## 5. Code conventions (§76)

- **Layering**: routers thin → services (engine, weather, sync) → repositories/models. Business
  logic never in UI components (§76.7) or route handlers; providers only behind their interfaces
  (`WeatherProvider` etc., §70) — no provider-specific imports outside `app/providers/`.
- ML stays out of app code (§76.9); `ml/` is its own world feeding artifacts through the gate in
  docs/ml.md.
- Validate at every boundary (Pydantic in, DB CHECKs too, §76.4–5); **never trust client-side
  calculations** — unit conversions (mm⇄liters) happen server-side (§76.6).
- Structured logging with redaction of secrets/coordinates (§76.12, security.md §7); meaningful
  error messages via `errors.*` keys (§76.13).
- Timestamps: UTC always in code/DB/API; localize only in UI (§41).
- Naming mirrors the contract payloads (snake_case JSON). No abbreviations that need a decoder ring.
- Dependencies: add only with a stated reason in the PR (§55, §76.20); no secrets in code ever
  (§76.14) — env + `.env.example` update when a new config appears (deployment.md §2 table too).
- Simplicity bias (§76.19): if you're adding a framework for scale you don't have yet, open an ADR
  discussion in docs/architecture.md instead.

## 6. Documentation duty (§68, §74's IMPLEMENT→TEST→RUN→FIX→DOCUMENT→CONTINUE)

Behavior changes update the relevant doc **in the same PR**: engine rules → docs/irrigation-engine.md;
schema → docs/database.md; endpoints (contract amendment) → docs/api-contract.md + README; ops
 knobs → docs/deployment.md + `.env.example`. A PR that changes behavior and silently invalidates a
doc is incomplete, even if all tests pass.

## 7. What reviewers check

1. Does it keep the product honest? (no fake data, estimates labeled, no pump control, no advice
   claims — §72, §38, §66: these are product-critical, review-blocking.)
2. RBAC/object-ownership on every new endpoint (security.md §2 matrix updated?).
3. Migration + test + i18n keys + doc update present?
4. Spec traceability: §n references in code comments/docs where a rule comes from the master spec,
   so future readers know *why* a threshold exists.
5. CI green; demo flow still works (`demo:true` intact, AC-26 re-check).

Questions about product intent? docs/product-requirements.md §5–6 (scope / non-goals) is the
tie-breaker; if a feature is a non-goal, the answer is a link to §78 Phase 1 exclusions, not an
argument.
