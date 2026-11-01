# First ERD section: Django implementation mapping

Scope: ACCOUNT, STUDENT, ROLE, ACCOUNT_ROLE from the team's supplied diagram.
Email login supersedes the earlier username choice. This is the first development
milestone; skills, courses, comparisons, reference publication, and public
registration are not implemented here.

## Entity and field mapping

The models live in `src/backend/accounts/models.py`. Explicit `db_table` names
keep the logical table names recognizable in PostgreSQL.

| ERD | Django representation | Physical storage / behavior |
| --- | --- | --- |
| ACCOUNT | `Account(AbstractBaseUser, PermissionsMixin, TimestampedModel)` | `account` table; configured as `AUTH_USER_MODEL = "accounts.Account"` |
| account_id | `UUIDField(primary_key=True, default=uuid.uuid4)` | `account_id`; UUID rather than a username or email used as identity |
| login_email | `EmailField(unique=True)` and functional unique constraint on `Lower("login_email")` | `login_email`; case-insensitive database uniqueness |
| password_hash | Django attribute `password`, `db_column="password_hash"` | Hashed encoded credentials in `password_hash`; use `set_password` / `check_password` |
| status active/disabled | `is_active = BooleanField(default=True)` | `is_active`; true = active, false = disabled. No duplicate status field |
| created_at / updated_at | `DateTimeField(auto_now_add=True)` / `DateTimeField(auto_now=True)` | Set on creation / ordinary model saves, not automatically by raw SQL or bulk updates |
| STUDENT | `Student(TimestampedModel)` | `student` table |
| student_id | UUID primary key | `student_id` |
| STUDENT.account_id | `OneToOneField(settings.AUTH_USER_MODEL, ...)` named `account` | `account_id`; non-null and unique |
| display_name | `CharField(max_length=150)` | `display_name` |
| major | `CharField(max_length=150, blank=True)` | Optional text represented by an empty string, not SQL NULL |
| career_interests | `TextField(blank=True)` | Optional text represented by an empty string |
| graduation_year | `PositiveSmallIntegerField(null=True, blank=True)` | Optional numeric value, SQL NULL when absent |
| ROLE | `Role` | `role` table |
| role_id | UUID primary key | `role_id` |
| role_name | Unique `CharField`, choices and database CHECK | Only student, maintainer, administrator |
| ACCOUNT_ROLE | `AccountRole` | `account_role` table |
| (account_id, role_id) composite identity | Two foreign keys and `UniqueConstraint(fields=["account", "role"])` | Preserves uniqueness of each pair |
| Added assignment_id | UUID primary key | Extra surrogate identity for ordinary Django model relations; deliberate physical-model difference |
| assigned_by | Nullable account foreign key | `assigned_by_id`; SQL NULL allowed for trusted setup/system assignments |
| assigned_at | `DateTimeField(auto_now_add=True)` | Creation timestamp |

Django adds `_id` to foreign-key attribute names in database columns. In Python,
`student.account` accesses the related object; `student.account_id` accesses its
stored UUID without fetching that object. Foreign keys refer to the custom user
through `settings.AUTH_USER_MODEL`, not Django's default `User` class.

## Django infrastructure beyond the diagram

`AbstractBaseUser` supplies authentication behavior and `last_login`.
`PermissionsMixin` adds `is_superuser`, Groups, and user-permission relationships.
`is_staff` controls eligibility for Django admin access. Django also creates
framework tables for sessions, permissions, content types, and admin logs.
These are framework infrastructure, not additional Compass ERD sections.

The custom user is defined in `accounts/0001_initial.py`, before any initial
account migrations are applied. There is no separate `auth_user` account table.
`0002_seed_roles.py` inserts the three allowed roles with stable UUIDs and grants
no privileges to any account. Its reverse operation deliberately retains roles
rather than deleting potentially referenced data.

Django's admin URL is still not exposed and its model-registration UI is deferred.
Do not treat `createsuperuser` as a way to create a Compass business administrator.

## Login and email policy

- There is no username column. `USERNAME_FIELD = "login_email"` tells Django which
  attribute is used to identify accounts.
- The login form's internal field remains named `username` because Django's
  `AuthenticationForm` uses that name. Its label, widget, validation, and actual
  lookup use an email address. This is an integration detail, not username login.
- Compass deliberately treats the whole address as case-insensitive. Creation and
  login trim outside whitespace and lowercase it; database uniqueness on the
  lowercase value also protects writes bypassing model normalization.
- This is a product policy, not a claim that every email provider treats local-part
  capitalization identically. Email ownership verification is a separate future
  feature before public self-registration.
- `AccountManager.create_user` hashes passwords; it follows Django's convention of
  not automatically applying password-strength validators. The interactive demo
  command explicitly validates its password. Future registration/change-password
  forms must do so too.

## Roles, ownership, and deletion

`AccountRole` is authoritative for Compass business roles. Do not duplicate those
roles in Django Groups. Built-in flags/permissions remain separate infrastructure:
assigning a business role never changes `is_staff` or `is_superuser`.

`services.assign_role` requires an active account with the administrator business
role and records the assigning account. It is not exposed as a public endpoint.
A superuser flag alone does not pass this business check. Initial trusted role
bootstrapping is a future operational decision; no administrator login is seeded.

`services.create_student` atomically creates an account, its student profile, and
its student role. Other account types can exist without a profile. There are no
signals automatically creating student records for every account. Future account
updates must preserve this lifecycle through explicit services.

Student access always filters by `account=request.user`, including the explicit
student-UUID URL. Another student's record returns 404. A maintainer or business
administrator does not get routine access to other students' private profiles.
UUIDs do not replace ownership checks. No profile-write endpoint exists yet.

- Deleting an account cascades to its student and its own role assignments.
- Deleting the assigning account sets `assigned_by` to NULL on surviving assignments.
- Roles referenced by assignments are protected against deletion.

These are Django ORM deletion policies. Direct SQL is not the supported account
lifecycle; future shared-content relationships require separate deletion policies.

## Implemented flow and limits

Routes: `/accounts/login/`, `/accounts/profile/`, `/accounts/students/<uuid>/`,
and POST-only `/accounts/logout/`. Sign-in uses Django authentication and sessions,
CSRF protection, generic credential errors, safe post-login redirects, and no-cache
responses. Existing sessions lose authenticated access when an account is disabled.

A local, per-process IP throttle returns HTTP 429 after ten failed submissions in
five minutes. It uses the direct peer address, not untrusted forwarding headers,
and does not run password authentication when already throttled. This is for the
single-process development setup; multi-worker deployment needs a shared cache,
trusted-proxy configuration, and review of shared-IP behavior. Restarting the
process clears this local throttle. No email/password values are stored in it.

The placeholder sign-in/profile screens can be replaced with the programming
lead's templates while preserving form fields, CSRF tokens, errors, named routes,
and POST logout. Public registration, password-reset delivery, email verification,
profile editing, and role-management screens remain outside this first milestone.

## Run and verify

See [Team development setup](../development.md) for dependency installation,
PostgreSQL startup, migrations, synthetic accounts, and tests. All model and
ownership tests run against PostgreSQL, including real uniqueness constraints.
The PostgreSQL test runner needs permission to create/drop an isolated test database.

## References

- [Django custom users](https://docs.djangoproject.com/en/6.1/topics/auth/customizing/)
- [Django authentication forms and views](https://docs.djangoproject.com/en/6.1/topics/auth/default/)
- [Model constraints](https://docs.djangoproject.com/en/6.1/ref/models/constraints/)
