# Personal accounts and content-maintainer access

Run all commands from the project root with PostgreSQL running. Commands apply
to the database selected by `POSTGRES_DB` in the shell or `.env`; provisioning
commands print that database name before prompting. Migrate that database first:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py migrate
```

The example email addresses below are placeholders. Replace them with addresses
or aliases you control. On macOS/Linux substitute `.venv/bin/python` and
`src/backend/manage.py`. Passwords are prompted without display, validated and
hashed by Django; no password command-line option is provided. Use an interactive
terminal: commands stop if hidden input is unavailable.

## Create your student account

Use `/accounts/register/` to create your personal student account and enter your
own display name, interests and self-reported skills. Public registration grants
only the student role. It cannot select administrator or maintainer privileges.
No demo accounts, synthetic catalog or real resume upload are required.

## Bootstrap the first administrator

An authorized person with local management-command/database access runs this
once in each newly configured Compass database:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py bootstrap_administrator admin@your-domain.edu
```

Enter and confirm a new password. The command creates a new active account with
the Compass administrator role and records the assignment in the audit log.
There is no authenticated actor for this initial trusted setup event. It creates
no student profile and grants neither Django staff nor superuser privileges.

Bootstrap refuses an existing email or any existing administrator assignment,
including one belonging to a disabled account. It never resets a password,
reactivates an account, or promotes an existing student. Competing invocations
serialize so only one first administrator can be created.

For an existing administrator who has forgotten a password, the trusted local
operator can use Django's existing password-change command:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py changepassword admin@your-domain.edu
```

That changes the password only; it does not reactivate a disabled account or
restore removed roles. Bootstrap is not an account-recovery bypass.

## Create a maintainer

Authenticate the existing Compass administrator, then create a separate editor
account:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py manage_maintainer create editor@your-domain.edu --administrator admin@your-domain.edu
```

The command prompts first for the administrator password, then for the new
maintainer password and its confirmation. The target must be a new email. Account
creation and the audited role assignment succeed or roll back together. No
student profile, catalog content, staff flag or superuser flag is created.

The administrator account itself can also access content maintenance. Provision
a separate maintainer when you want to demonstrate the editor's narrower role.

## Grant or revoke existing maintainer access

To grant the role to an existing non-student account without changing credentials:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py manage_maintainer grant editor@your-domain.edu --administrator admin@your-domain.edu
```

To revoke it:

```powershell
.\.venv\Scripts\python.exe src\backend\manage.py manage_maintainer revoke editor@your-domain.edu --administrator admin@your-domain.edu
```

Both commands authenticate an active business administrator. A staff/superuser
account without that business role is insufficient. Repeat grants/revocations do
not duplicate assignments or audit events. Revocation preserves the account,
password, authored content and other roles. An administrator retains maintenance
access through its administrator role even if its maintainer role is removed.

This provisioning workflow refuses to add the maintainer role to a student account
or profile. Use a separate email/alias for each role in the presentation. If an
account deliberately receives both roles through another authorized workflow,
the existing login gives editor roles precedence over the student default;
an explicit safe `next` destination still takes precedence over either default.

## Sign in and verify

Use the shared `/accounts/login/` page for every account:

| Account | Default destination | Access |
| --- | --- | --- |
| Personal student | `/dashboard/` | Own profile, skills, comparisons and progress |
| Maintainer | `/maintainer/` | Content drafts, sources, publication and lifecycle actions |
| Business administrator | `/maintainer/` | Content maintenance plus authorized role-management commands |

Use separate browser profiles or sign out before switching accounts. Revoking
maintainer access blocks subsequent maintainer requests, including from an
existing session, unless another editor role still grants access. Account
deactivation through the existing administrator service also blocks access.
Account activation UI/commands are outside this narrow provisioning batch.
Maintainer access never grants permission to read another student's private data.

## Presentation database

Student registration and provisioning operate independently in each database.
After creating `compass_curated`, select it, run migrations and repeat the setup
above. Keep `create_demo_accounts` and `seed_compass` for the synthetic development
database. These new commands do not create any accounts automatically on startup.
Do not commit account credentials or place passwords in shell command history.
