# Compass — Digital Corsairs Senior Project

Compass helps students connect their skills and coursework to career opportunities. The planned application will compare student skills with career profiles and job listings, identify skill gaps, and suggest learning resources and professional insights while keeping student profiles and comparison results private.

## Current status

The working application is a static HTML/CSS/JavaScript prototype. It includes a skill explorer, career pathways, professional insights, and a sample student dashboard. All displayed data comes from `frontend/js/data.js`; professional insights are sample content.

The Python backend is a scaffold: its files are placeholders. Authentication, a database connection, job-listing comparisons, personalized guidance, and AI features are not implemented yet. The dashboard does not represent a real logged-in student.

## Project structure

```text
Compass/
├── frontend/
│   ├── pages/              HTML pages; index.html is the landing page
│   ├── css/                Shared styles
│   ├── js/                 Page rendering and mock data
│   └── services/           Reserved for frontend API calls
├── src/
│   └── backend/
│       ├── __init__.py
│       ├── main.py         Future application entry point
│       ├── config.py       Future backend configuration
│       ├── database.py     Future database connection setup
│       ├── models.py       Future database models
│       ├── schemas.py      Future request/response schemas
│       ├── routers/        Request handlers
│       ├── services/       Business logic, including skill comparisons
│       └── security/       Authentication and access controls
├── migrations/             Database schema changes
├── seeds/                  Sample development data
├── tests/
│   ├── comparisons/        Skill comparison correctness
│   ├── permissions/        Student data access boundaries
│   └── user_flows/         End-to-end student journeys
├── docs/
│   ├── requirements/
│   ├── architecture/
│   ├── api/
│   └── security_guide/
├── scripts/                Development and maintenance utilities
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

Empty directories contain `.gitkeep` files so Git preserves the scaffold.

## Run the prototype locally

From the repository root, with Python 3 installed:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory frontend
```

Open <http://localhost:8000/pages/index.html>. Stop the server with `Ctrl+C`.

Alternatively, open `frontend/pages/index.html` directly in a browser, or use VS Code's Live Server on that file. Serving over HTTP will also support future API requests.

No build step, npm packages, or third-party Python dependencies are required for the current prototype. There is no runnable backend yet.

## Team development conventions

- Keep page rendering in `frontend/js/` and add API request helpers under `frontend/services/` when the backend is ready. Loading API data will require adapting the current synchronous mock-data initialization.
- Put request handling in backend `routers/` and comparison/recommendation logic in `services/`.
- Keep database schema migrations and sample seed data in their root directories. Use synthetic student data for development.
- Add backend dependencies with version constraints to `requirements.txt` when the team chooses the framework.
- Document new configuration names with example values in `.env.example`. Keep real credentials in an ignored `.env` file; backend environment loading still needs to be implemented. Frontend assets must never contain secrets.
- Enforce student data access on the backend. As accounts are implemented, add permission tests proving a student cannot read or modify another student's profile or comparison results, plus comparison and user-flow tests.
- Keep requirements, architecture decisions, API contracts, and the security design in their respective `docs/` directories. The test directories are placeholders; no automated tests exist yet.
