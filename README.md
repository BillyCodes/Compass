# COMPASS — Test Launch 01

Digital Corsairs senior project. This is the first integrated build of COMPASS, made from the **Test Launch 01 Engineering Blueprint**.

A student can:

- create an account and log in
- upload a resume (PDF, .docx or .txt) and confirm the skills it finds
- add skills and courses by hand
- see a Skillprint radar chart and top-skills view
- compare against a career profile, a sample job posting, or a posting they paste in
- see strengths, skills to improve, major gaps, and a route to close them
- save progress and see it on a Journey timeline
- read sample Field Notes from (fictional) professionals
- log out, after which every private page and API route is denied

All data is synthetic. Companies and professionals are fictional pilot content.

---

## Run it (any teammate, about 2 minutes)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # optional for local SQLite
python manage.py migrate
python manage.py seed_compass
python manage.py runserver
```

Open http://127.0.0.1:8000.

### Use PostgreSQL instead of SQLite

```bash
createdb compass                                     # or use pgAdmin
echo "DATABASE_URL=postgres://USER:PASS@localhost:5432/compass" >> .env
python manage.py migrate && python manage.py seed_compass
```

### Demo accounts (synthetic, development only)

| Account | Email | Password | Purpose |
|---|---|---|---|
| Student A | `student.a@compass.test` | `CompassDemo-A1` | Full profile, history, saved results |
| Student B | `student.b@compass.test` | `CompassDemo-B2` | Cross-account denial tests |
| Disabled | `disabled@compass.test` | `CompassDemo-X9` | Login must fail |

`python manage.py seed_compass --reset` recreates them. Create an admin with `python manage.py createsuperuser` and open `/admin/` for reference content (skills, courses, career profiles, sample postings, Field Notes).

### Run the tests

```bash
python manage.py test core
```

33 tests cover blueprint §12.2 (trial-run script), §12.3 (negative test matrix), and hand-computed comparison examples.

---

## Trial-run script (blueprint §12.2)

| # | Do this | You should see |
|---|---|---|
| 1 | `migrate`, `seed_compass`, `runserver` | No errors; seed prints counts |
| 2 | Register a new account | Redirect to the welcome page |
| 3 | Log out, try a wrong password | "That email and password don't match an active account." |
| 4 | Log in as Student A | Dashboard loads with Jordan's data |
| 5 | Open My Skillprint | Student A's skills only |
| 6 | Change a skill level, reload | Change persists |
| 7 | As A, open `/results/<one of B's result IDs>/` | 404 |
| 8 | Compare → Cloud Engineer | Score, strong areas, gaps, route |
| 9 | Log out | Back on home page |
| 10 | Press Back / reopen `/dashboard/` | Redirected to login; `/api/me` returns 401 |

---

## Project layout

```
compass_site/settings.py      env-driven settings, SQLite/Postgres switch, hardened sessions
core/models.py                Account ≠ Student, catalog, StudentSkill, versioned targets, MatchResult, snapshots, Field Notes
core/security.py              student_required, owned(), login throttle, JSON response shapes
core/middleware.py            disabled accounts lose live sessions
core/services/comparison.py   comparison engine (algorithm tl01-v1)
core/services/skillprint.py   category scores, radar SVG, snapshots
core/services/resume.py       resume text extraction + skill detection
core/services/postings.py     pasted posting → requirements
core/services/skill_matcher.py catalog matching with word boundaries
core/views.py                 pages
core/api.py                   JSON contract (blueprint §7)
core/templates/core/          Compass-styled templates
core/static/core/compass.css  design tokens, light + dark
core/management/commands/seed_compass.py   synthetic data
core/tests.py                 acceptance tests
docs/DECISIONS.md             what this build assumed — needs team sign-off
```

## Who owns what (blueprint §10)

| Lead | Start here |
|---|---|
| Billy (Programming) | `services/comparison.py`, `services/resume.py`, `views.py`, `api.py`, `tests.py` |
| Richshard (Database) | `models.py`, `migrations/`, `seed_compass.py`, the Postgres switch in `settings.py` |
| Luis (Software Engineering) | `templates/`, `static/`, `urls.py`, this README's setup steps |
| Kershad (Cybersecurity) | `security.py`, `middleware.py`, `settings.py` session/cookie block, `NegativeTests` in `tests.py` |

## JSON API (blueprint §7)

Every response is `{"ok": true, "data": …}` or `{"ok": false, "error": {"code", "message", "fields"?}}`. Get a CSRF token from `GET /api/csrf` and send it as `X-CSRFToken`.

| Method | Route | Notes |
|---|---|---|
| GET | `/api/csrf` | CSRF token |
| POST | `/api/register` | `name, email, password, major?` (anything else is rejected) |
| POST | `/api/login` | `email, password` |
| POST | `/api/logout` | |
| GET/PATCH | `/api/me` | PATCH accepts `name, major, career_interests` |
| GET | `/api/dashboard-data` | |
| GET | `/api/skills` | catalog |
| GET | `/api/me/skills` | own skills |
| POST/PUT/DELETE | `/api/me/skills/<skill_id>` | `level` 1–5, `evidence?` |
| GET/POST | `/api/comparisons` | POST `career_id` or `posting_id` |
