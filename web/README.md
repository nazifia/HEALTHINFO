# HEALTH INFO — Web Frontend

Static SPA (plain HTML/CSS/JS, no build step) over the Django REST API.
Lives entirely in `web/`; the Flutter app in `mobile/` is untouched.

## Run locally

Any static server works:

```bash
cd web
python -m http.server 5500
# open http://localhost:5500
```

Point it at a local backend from the login screen → Advanced → API base URL
(e.g. `http://localhost:8000`).

## Deploy to Firebase Hosting

```bash
npm install -g firebase-tools
cd web
firebase login
firebase init hosting   # pick/create a project, keep public dir = "." , SPA rewrite not needed (hash routing)
firebase deploy
```

`firebase init` writes `.firebaserc` with your project id; `firebase.json` is already here.

## Backend CORS (required for prod)

The API only allows configured origins in prod mode. Add your Firebase domain
to the backend env:

```
CORS_ALLOWED_ORIGINS=https://<your-project>.web.app,https://<your-project>.firebaseapp.com
```

(Dev mode — toggled in Django admin → Governance → Runtime config — reflects any origin.)

## What's covered

- Auth: login (JWT, phone), register, org onboarding (+ jurisdictions), logout, profile (`/api/users/me/`)
- Catalog CRUD: diseases, medications, symptoms, drug interactions, specialties, procedures, lab tests, articles — plus workflow transitions + audit history
- Reports CRUD: case reports, ADRs, lab results, immunizations, vital events, stock, CHW, facility metrics, insurance claims, appointments
- Tools: global search, semantic search, Ask AI (with feedback votes), differential diagnosis, interaction check, notifiable-cases report (+ CSV)
- Knowledge graph pages for diseases / medications / procedures / specialties
- Analytics: tenant dashboard + all stats endpoints; platform variants for super admins; CSV exports
- Admin: user management, tenant approve/reject/suspend (super admin)

- Charts: analytics arrays render as SVG bar/line charts automatically (one label
  column + 1–4 numeric columns → chart; anything wider stays a table). Hover
  tooltips everywhere; a "Table view" toggle under every chart keeps values
  reachable without color or hover.
- PWA: installable (manifest + icons), app shell cached by `sw.js` so the UI
  loads offline. API responses are never cached. **Bump `VERSION` in `sw.js`
  whenever you change shell files** so clients pick up the update.

Create/edit forms are generated at runtime from DRF `OPTIONS` metadata, so new
serializer fields show up without frontend changes.

Drug orders are the exception, because a visit rarely calls for one drug:
"Add another drug" repeats the drug fields, and the rows POST as a list that
the API writes as one prescription (whole, or not at all). The drugs of one
prescription share a `group`, so the list shows one row per prescription — each
drug with its own directions, and a Cancel button on the row — a detail page
lists what was prescribed with the drug on screen, and cancelling stops every
drug on the prescription, bar anything already dispensed. `node prescription.test.js` self-checks the payload the form
builds; `node picker.test.js` the patient type-ahead.
