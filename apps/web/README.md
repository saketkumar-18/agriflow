# AgriFlow — Farmer Web App (apps/web)

Mobile-first PWA decision-support app for Indian farmers. The #1 question it
answers on the home screen: **“Does my field need irrigation?”** — in seconds,
with a big status card (💧 Irrigation recommended / ✅ No irrigation needed /
⏸️ Review tomorrow), urgency shown as color **+ icon + text** (never color
alone), translated reasons, a confidence meter, and a highly visible 5-day
rain strip.

Built against the **frozen API contract** in [`docs/api-contract.md`](../../docs/api-contract.md).

## Stack

- Next.js 15 (App Router) + TypeScript `strict` (no `any`)
- Tailwind CSS v4 — hand-rolled accessible components, no component library
- PWA: `public/manifest.webmanifest` + `public/sw.js` (app shell cached
  network-first; latest successful API GET responses cached for offline reads)
- Offline write queue: writes made while `navigator.onLine === false` are
  stored in `localStorage` with a `crypto.randomUUID()` idempotency key and
  flushed via `POST /api/v1/sync/batch` on the browser `online` event
  (pending count shown as a badge in the header)
- i18n: every user-visible string goes through `t(key, params)`
  (`lib/i18n/`, dictionaries `en.json` / `hi.json`). The API sends
  reasons/warnings/time/confidence as `{key, params}` and the UI translates
  them; unknown keys render the raw key without crashing. `document.lang`
  follows the selected language (Hindi sets `lang="hi"`).
- Charts: hand-written SVG line/bar/min-max charts
  (`components/charts.tsx`), **lazy-loaded** with `next/dynamic` + `Suspense`;
  each chart has a `sr-only` data-table fallback.
- Demo mode: when the API server is unreachable (NetworkError), pages render
  fixture data from `lib/fixtures.ts` under a loud **“DEMO DATA”** banner —
  never silently faked.

## Environment variables

| Variable              | Default                | Purpose                                   |
| --------------------- | ---------------------- | ----------------------------------------- |
| `NEXT_PUBLIC_API_BASE`| `http://localhost:8000`| FastAPI backend base URL (all endpoints under `/api/v1`, plus `/api/health`) |

Create `.env.local` if you need a different backend:

```bash
NEXT_PUBLIC_API_BASE=http://192.168.1.10:8000
```

## npm scripts

| Script          | What it does                                        |
| --------------- | --------------------------------------------------- |
| `npm run dev`   | Start the dev server (Turbopack) on :3000           |
| `npm run build` | Production build (type-checked by Next)             |
| `npm run start` | Serve the production build                          |
| `npm run lint`  | ESLint (`eslint-config-next`)                       |
| `npm run typecheck` | `tsc --noEmit` — strict TypeScript gate         |
| `npm run gen-icons` | Regenerate PWA PNG icons (no dependencies)      |

## Auth flow

JWT stored in `localStorage` (`agriflow.token`), sent as
`Authorization: Bearer <jwt>`. Any 401 clears the session and redirects to
`/login?next=…`. Registration creates `farmer` role accounts only (server rule).

## Routes

| Route | Purpose |
| ----- | ------- |
| `/login`, `/register` | Auth |
| `/` | Dashboard — the irrigation question, rain strip, weather + soil tiles |
| `/farms/new` | Create farm |
| `/farms/[id]` | Farm detail + fields |
| `/fields` | All fields (bottom tab) |
| `/fields/new?farm=` | Create field (crop/soil/stage pickers) |
| `/fields/[id]` | Field detail + lazy charts (moisture, rain, temp, irrigation, ET₀/ETc) |
| `/fields/[id]/record-irrigation` | Record irrigation (mm **or** liters, offline-queued) |
| `/recommendations/[fieldId]` | Full explanation + feedback (`POST /feedback`) + refresh + agronomist override |
| `/history` | Irrigation events |
| `/analytics` | Water usage per farm per month |
| `/notifications` | Notification list + mark read |
| `/alerts` | Alert feed + alert settings (`PUT /auth/me/preferences`) |
| `/account` | Profile, language, logout, role links |
| `/agronomist` | Assigned farms, field review, advisories (`POST /advisories`), overrides |
| `/admin` | Stats, users table, audit log (role-gated) |

## Accessibility & UX rules honored

- 44–48px+ touch targets; bottom tab nav on mobile (Dashboard / Fields /
  History / Alerts / Account)
- All inputs have `<label>`s; visible focus rings; toasts in an `aria-live`
  region; skip-to-content link; status conveyed by icon + text + color
- Loading skeletons, empty states, and friendly error+retry for every fetch —
  no blank screens
- Language toggle persists per user (`localStorage`) and best-effort syncs to
  `PUT /auth/me/preferences` when logged in

## Offline behavior

1. `sw.js` caches the app shell (network-first) and the **last known
   successful response of every API GET** (stale-while-revalidate).
2. Writes (irrigation events, readings, feedback) while offline are queued in
   `localStorage` (`lib/queue.ts`) with `idempotency_key`.
3. On the `online` event (or badge tap / app load while online) the queue is
   flushed with `POST /api/v1/sync/batch`; `created`/`duplicate` results are
   removed, hard errors are dropped after one attempt and reported.
