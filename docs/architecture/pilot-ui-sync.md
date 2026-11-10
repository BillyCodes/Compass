# Pilot UI sync (compass-test-launch)

The UI and view code match the local `compass-test-launch` build. Database, auth, audit and security layers are unchanged.

## What is kept from main
- 0-5 proficiency scale, `weighted_skill_match_v1` scoring, honesty wording ("Provisional", "Unreported proficiency").
- Draft -> review -> publish content workflow, DB triggers/constraints, role checks, audit allowlist, login throttle.
- Courses stay interest-only and never grant skills.

## Deviations from the local build
- No hard-coded demo credentials on the login page.
- Local 1-5 scale and its scoring text are not used; result pages describe main's algorithm.
- The course "term" field is dropped.

## New additive tables (`pilot` app, migration 0001)
SkillDetail, ResumeImport, ProgressSnapshot, StudentPosting, StudentPostingRequirement, PostingMatch, FieldNoteProfile. No existing table is altered.

## Setup
```
pip install -r requirements.txt   # adds pypdf, python-docx
python manage.py migrate
python manage.py seed_compass     # synthetic content via the normal publish workflow
python manage.py create_demo_accounts
```
Resume files are parsed in memory and never stored. The JSON API under `/api/*` reuses the web login throttle and CSRF.
