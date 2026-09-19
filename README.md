# Northstar · نورث ستار

Northstar is a mobile-first, bilingual (English/Arabic), offline-first personal life dashboard built with Flask and SQLite. It combines lifetime-to-week goal planning, unlimited task nesting, scheduled habits, a calm Islamic nightly muḥāsabah, factual weekly reflection, statistics, and a scoped API intended for personal agents.

## What works

- Email/password registration, login and logout with Werkzeug password hashing, CSRF protection, expiring secure sessions, generic login errors and per-record ownership checks.
- Lifetime → year → quarter → month → week goals with strict parent validation. Tasks attach to goals and may nest without a depth limit; circular nesting is rejected.
- Mobile Today and one-day-at-a-time Week experiences with instant checkboxes, quick add, prayer/Quran/routine habits and real calculated progress.
- Arabic and English profile preference, correct `lang`/`dir`, RTL-aware logical CSS, bilingual default content and locally available system font fallbacks.
- Versioned, editable muḥāsabah templates with Arabic/English labels, prompt order, required flags and six field types. Each recap stores an immutable prompt snapshot.
- Private recap drafts, completion/reopening API, deterministic weekly reflection, Arabic and mixed-language answers.
- Categories, habits, tags schema, resource/course attachments, soft deletion/restoration, audit history and authenticated JSON export.
- High-entropy, hash-only agent tokens with visible prefixes, expiry, revocation and granular scopes. The full token is shown once.
- Versioned REST API and atomic hierarchy creation. OpenAPI is served at `/api/openapi.json`; human documentation is at `/api-docs`.
- Installable PWA shell, service worker, IndexedDB page snapshots, authenticated-user outbox, offline Today/Week reads, offline task/recap/habit writes, retry, cursor sync, idempotency and structured conflicts.

## Architecture

The project is a Flask modular monolith. Blueprints own browser authentication, dashboard pages and `/api/v1`; `services.py` contains domain rules/statistics; `db.py` owns SQLite connections and migrations. There is deliberately no ORM. SQL is parameterized, transactions protect hierarchy batches, foreign keys are enabled on every connection, and WAL mode improves small-instance concurrency.

```text
northstar/
├── app/
│   ├── __init__.py          application factory
│   ├── auth.py              browser authentication
│   ├── dashboard.py         server-rendered pages/settings/export
│   ├── api.py               scoped JSON API and synchronization
│   ├── db.py                connection and migration commands
│   ├── i18n.py              bundled Arabic/English strings
│   ├── security.py          CSRF, auth and token hashing
│   ├── services.py          domain validation, seeds and statistics
│   ├── templates/           Jinja pages
│   └── static/              CSS, IndexedDB JS, SW, manifest, icons, OpenAPI
├── migrations/001_initial.sql
├── tests/
├── config.py
├── run.py
├── requirements.txt
└── .env.example
```

## Local setup

Python 3.11+ is recommended.

```bash
cd northstar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate a real local secret instead of using the development fallback:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Put that value in your environment as `SECRET_KEY`. Flask does not automatically load `.env` without an optional dotenv package, so export the variables in your shell or process manager.

## Initialize, seed, run and test

```bash
# Initialize or migrate the database
flask --app run.py db-migrate

# Start the development server, then register through /auth/register
flask --app run.py run --debug

# In another terminal, seed the editable routine for every existing user.
# This command intentionally never creates an account or password.
flask --app run.py seed-routine

# Run all automated tests
pytest -q
```

The seed creates the requested Monday–Friday work block, gym, SecOps, finance, marriage preparation, Friday family/review, Quran, five prayers, twice-daily teeth brushing and nightly recap. It is idempotent for users who already have habits.

## PWA and offline behavior

Open the app online, log in, visit Today and Week once, then use the browser’s “Install app” action. The service worker caches only the application shell and static assets. It does **not** put recap answers or authenticated HTML in the service-worker asset cache. Today/Week snapshots and private drafts live in the authenticated device’s IndexedDB database; logout sends `Clear-Site-Data: "storage"` so browsers clear that private device storage.

Checkboxes update immediately. Offline task additions, habit entries and recap drafts are placed in an outbox with mutation UUID, entity UUID, operation, base version and client timestamp. Reconnection or **Sync now** sends them to `/api/v1/sync`. The server stores each mutation UUID once, continues past conflicts and returns changes after a numeric cursor. A base-version mismatch returns both the current server record and the client mutation; a client may keep the server copy or resend with `force: true`, which is audited as a conflict resolution.

Limitations: background sync depends on reopening the PWA because the MVP does not request the browser Background Sync permission. The current device has one IndexedDB namespace, so users sharing a browser profile should explicitly log out between accounts. Conflict data is stored for presentation, but the first UI exposes status rather than a full side-by-side field merge editor.

## Agent API tokens

Create a token in Settings, give it a name, choose only the needed scopes and optionally set an expiry. Recap scopes are marked as access to private reflections. Copy the secret immediately; only its SHA-256 hash and a short non-secret prefix are retained.

```bash
export NORTHSTAR_TOKEN='northstar_copy_the_one_time_secret_here'

curl -H "Authorization: Bearer $NORTHSTAR_TOKEN" \
  http://127.0.0.1:5000/api/v1/today

curl -X POST http://127.0.0.1:5000/api/v1/tasks \
  -H "Authorization: Bearer $NORTHSTAR_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Review threat model","due_date":"2026-09-20"}'

curl -X POST http://127.0.0.1:5000/api/v1/goals/tree \
  -H "Authorization: Bearer $NORTHSTAR_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"goals":[{"type":"lifetime","title":"Lifelong learning","children":[{"type":"year","title":"2026","children":[{"type":"quarter","title":"SecOps course Q4","children":[{"type":"month","title":"Foundation modules","children":[{"type":"week","title":"Complete module one"}]}]}]}]}]}'
```

Resource URLs can then be attached with `POST /api/v1/resources`. API responses keep English machine keys in both locales. Browser forms use sessions plus CSRF; agents use Bearer tokens and do not use account passwords.

## Statistics formulas

- **Daily completion:** completed tasks due that date ÷ all non-deleted tasks due that date.
- **Weekly adherence:** completed tasks due Monday–Sunday ÷ all non-deleted tasks in that interval.
- **Category completion:** completed tasks in a category ÷ all tasks in that category.
- **Current habit streak:** consecutive completed calendar dates ending today. **Longest streak:** longest run of consecutive completed dates.
- **Recap consistency:** completed recaps in the current Monday–Sunday interval ÷ 7.
- Prayer/Quran/gym/study reporting is derived from dated habit entries and stable habit keys. No religious score or theological judgment is calculated.
- Goal progress uses descendant task completion as its intended MVP mode; the current visual surfaces task and category completion while the API preserves `progress_mode` for richer aggregation.

## Privacy and security decisions

- Passwords use Werkzeug’s salted adaptive hash. Token secrets are random, shown once and stored only as SHA-256 hashes.
- Login failures do not reveal whether an email exists. Cookies are HTTP-only and SameSite=Lax; set `SESSION_COOKIE_SECURE=true` behind HTTPS.
- Every owned lookup includes `user_id`; cross-user IDs return 404. Token scope failures return 403. Expired and revoked tokens return 401.
- Recap answers never enter audit metadata, server logs, statistics telemetry or the service-worker asset cache. Agent recap access requires explicit `recaps:read`/`recaps:write`.
- SQL value input is parameterized. Dynamic table/column names only come from hardcoded allowlists.
- Mutations record safe field names and identifiers, not passwords, cookies, token secrets or private recap answer values.

## Production deployment

Use HTTPS, a long random `SECRET_KEY`, `SESSION_COOKIE_SECURE=true`, and a production WSGI server such as Gunicorn behind a reverse proxy. Forward the original scheme and configure trusted proxy handling at the deployment boundary. Do not expose Flask debug mode. Restrict the instance directory to the service account.

The included Fly configuration runs one Gunicorn worker (appropriate for a single SQLite writer), mounts the existing compatibility-named `hayat_data` volume at `/data`, forces HTTPS and keeps one machine running. The infrastructure identifier is retained so renaming the product does not risk the live database:

```bash
flyctl apps create hayat-dashboard-20260919
flyctl volumes create hayat_data --region ams --size 1 --app hayat-dashboard-20260919
python -c 'import secrets; print("SECRET_KEY=" + secrets.token_hex(32))' | flyctl secrets import --app hayat-dashboard-20260919
flyctl deploy --app hayat-dashboard-20260919
flyctl status --app hayat-dashboard-20260919
```

Back up SQLite with its online backup API or `sqlite3 instance/hayat.sqlite3 '.backup backup.sqlite3'`; keep backups encrypted because recaps are sensitive. SQLite is a good fit for a personal or low-concurrency deployment: it is simple, transactional and has no separate database service. Move to PostgreSQL when there are multiple web workers performing sustained concurrent writes, growing multi-user traffic, cross-region operation, or operational requirements for replicas and point-in-time recovery.

## Deliberate MVP tradeoffs and next improvements

- The UI supports the main mobile workflow, creation and settings editing; some advanced moves, bulk edits and resource operations are API-first.
- Locale-aware Arabic/English strings cover the primary experience and Islamic recap. A production translation catalog (Babel/gettext) should replace the compact dictionary before adding more languages.
- Dates are stored as stable dates and timestamps as UTC ISO strings. A production pass should use full IANA timezone conversion for every scheduled-time edge case and localized number formatting.
- Add WebAuthn or TOTP, encrypted-at-rest recap fields, per-device IndexedDB encryption, and a user-visible session revocation screen for higher-threat environments.
- Add a dedicated side-by-side conflict resolver, richer deterministic recurring-pattern grouping, and end-to-end browser tests for offline/RTL behavior.

No credentials, token secrets or database files are committed.
