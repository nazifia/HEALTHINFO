# Health Knowledge Platform — Backend (thin slice)

Runnable spine of the multi-tenant health platform. Proves the hard part —
**tenant isolation** — end to end, plus RBAC, eight content modules (diseases,
medications, symptoms, drug interactions, specialties, procedures, lab tests,
articles), DB-agnostic substring search, draft/review workflow + audit log,
knowledge-graph traversal, semantic search + RAG, Celery, analytics, Swagger.
Everything else from the full spec (Flutter, i18n, remaining content modules)
layers on top of this without changing it.

## Stack
Django 5 · DRF · JWT (simplejwt) · drf-spectacular · Celery · Docker
Default DB is **sqlite** (zero-config dev). Set `DB_HOST` for PostgreSQL or
MySQL (`DB_ENGINE`). Embeddings live in a JSON column and ranking is cosine in
Python — fully DB-agnostic, no pgvector or vector column on any backend.

## Run with Docker
```bash
cp .env.example .env
docker compose up --build
# create a super admin:
docker compose exec web python manage.py createsuperuser
```

## Run locally
```bash
pip install -r requirements.txt
cp .env.example .env          # set DB_HOST=localhost
python manage.py makemigrations tenants accounts catalog governance analytics
python manage.py migrate        # embeddings stored as JSON — portable, no pgvector extension needed
python manage.py runserver
```

## API
- `POST /api/auth/token/` — JWT login with `{phone, password}` → `{access, refresh}`
- `POST /api/auth/register/` — self-register into a tenant with `{phone, password}`
- `GET  /api/users/me/`
- `GET/POST /api/diseases/`, `/api/medications/`, `/api/symptoms/`,
  `/api/interactions/`, `/api/specialties/`, `/api/procedures/`,
  `/api/lab-tests/`, `/api/articles/`
- `GET  /api/search/?q=headache` — substring (`icontains`) search across all
  content modules, tenant-scoped, returns disclaimer
- `GET  /api/graph/diseases/{id}/`, `/api/graph/medications/{id}/` — graph traversal
- `POST /api/diseases/{id}/transition/` `{to,note}` · `GET .../history/` — workflow
- `GET  /api/ai/semantic-search/?q=...` — embedding cosine nearest-neighbour
  (computed in Python over the tenant's rows)
- `GET  /api/ai/ask/?q=headache and fever` — RAG (answer + sources + disclaimer)
- `GET  /api/health/` (alias `/healthz`) — DB-backed liveness probe (200/503), no auth
- `GET  /api/docs/` — Swagger UI

## AI / RAG
Embeddings stored as JSON, cosine ranking computed in Python (O(n) per-tenant
scan, no vector index). Runs with **no API key** by default (`AI_EMBED_PROVIDER=fake`,
deterministic non-semantic vectors) so dev/tests work offline. For real use:
```
AI_EMBED_PROVIDER=openai   OPENAI_API_KEY=sk-...     # real embeddings
ANTHROPIC_API_KEY=sk-ant-...                          # RAG answer synthesis
```
Without `ANTHROPIC_API_KEY`, `/api/ai/ask/` returns retrieval-only (sources, no
generated answer — no fabrication). Build the index:
```bash
python manage.py reindex      # embeds published content for every tenant
```

## Celery (async embedding + analytics)
`docker compose up` starts `worker` (tasks) and `beat` (nightly reindex at 03:00).
- **Embedding** is enqueued automatically on content save/delete via a
  post-commit signal — publish a disease and its vector appears without a
  manual `reindex`. Unpublish/delete removes it.
- **Analytics** events (`search`, `view`) are recorded fire-and-forget; a broker
  outage never breaks the request.

Run a worker locally: `celery -A config worker -l info` (needs Redis).
Set `CELERY_TASK_ALWAYS_EAGER=1` to run tasks inline without a broker.

## Analytics dashboards
All dashboards accept `?from=YYYY-MM-DD&to=YYYY-MM-DD` to window the rollup.
- `GET /api/analytics/tenant/` — searches, top queries, active users (30d),
  popular diseases/medications, AI feedback, search trend. Tenant-scoped.
- `GET /api/analytics/platform/` — super-admin: tenant/user/search totals,
  searches per tenant, search trend, ADR rollup.
- `GET /api/analytics/funnel/` — search→view→case counts + conversion ratios.
- `GET /api/analytics/ai-quality/` — RAG answered vs retrieval-only, downvote
  rate, top downvoted questions.
- `GET /api/analytics/retention/` — distinct active users per week (8w).
- `GET /api/analytics/benchmark/` — your case load vs anonymized platform median.

## Health surveillance, reporting & collation
- `GET  /api/analytics/surveillance/` · `/api/analytics/platform/surveillance/`
  — outbreak alerts: diseases whose latest week spikes vs trailing baseline.
- `GET/POST /api/case-reports/` — file/list cases (clinical staff). Filter by
  severity, outcome, disease, age group, region.
- `GET  /api/analytics/cases/` · `/api/analytics/platform/cases/` — case rollups
  (severity/outcome/age/region/trend); platform view collates by ICD-10 code
  across tenants (fixes free-text name collisions).
- `GET  /api/analytics/cases/export/` — case reports as CSV (respects range).
- `GET/POST /api/adverse-reactions/` — pharmacovigilance (ADR) reports.
- `GET  /api/analytics/adr/` · `/api/analytics/platform/adr/` — ADR rollups.
- `GET  /api/reports/notifiable/` — cases of notifiable diseases (regulator
  report); add `?format=csv` for a file.
- `GET  /api/analytics/idsr/` · `/api/analytics/platform/idsr/` — IDSR weekly
  epidemiological summary (epi-week × disease: cases, deaths, case-fatality
  rate, notifiable flag). `?weeks=N` windows it; `?format=csv` downloads the
  line-list. Platform view pools every tenant and rolls totals up the gov
  hierarchy to national (the NCDC central collation). Case rollups now carry
  `deaths` + `case_fatality_rate`, and platform rollups reach `by_national`.
- `POST /api/interactions/check/` `{medication_ids:[...]}` — drug-interaction checker.
- `POST /api/differential/` `{symptom_ids:[...]}` — symptoms → ranked diseases.

A weekly Celery beat task (`weekly_tenant_report`, Mondays 04:00) emails each
tenant admin their rollup + any outbreak alerts.

## Tenant resolution (any of)
1. Header `X-Tenant-ID: hospital-a`
2. Custom domain match (`Tenant.domain`)
3. Subdomain of `BASE_DOMAIN` → slug (`hospital-a.health.com`)

## How isolation works
`TenantOwnedModel` uses `TenantManager`, which filters every query by the
request's tenant (bound by `TenantMiddleware` via a thread-local). No tenant
bound → empty queryset, so a misconfig fails closed instead of leaking.
Super-admin bypass via `Model.all_objects`.

## Tests
```bash
pytest                 # runs on the default sqlite DB, no server needed
```
`tests/test_tenant_isolation.py` is the guard rail — keep it green.

## Next steps
Done: content modules, draft/review workflow + audit log, knowledge-graph
relations, semantic search + RAG, Celery (async embeddings, analytics).
Remaining roadmap: Flutter client → i18n → CI/CD + Nginx/Gunicorn prod compose.
Add new content modules by copying the catalog app pattern.
"# HEALTHINFO" 
