# Audit event database batch

Implemented November 1, 2026. The `auditing` app implements the final ERD table,
AUDIT_EVENT, and relationships D1–D3. All 21 planned application tables now have
Django models and migrations. This is schema/backend completion; frontend forms,
management screens, representative data, and full browser workflows remain.

## Agreed policy

- Record role assignment/removal, account activation/disablement, and content
  review, publication, and retirement.
- Store event type, timestamp, actor, optional subject account/content version,
  and only minimal structured metadata.
- Only active Compass administrators can read events through application services.
- Record each event inside its business action's transaction. Logging failure
  rolls back the action; action failure leaves no success event.
- Retain events for one calendar year. Eligible events can then be purged by a
  trusted maintenance command. No automatic purge schedule is installed locally.

## ERD-to-Django mapping

| ERD field | Django/PostgreSQL mapping |
| --- | --- |
| Event primary key | `AuditEvent.event_id`, UUID primary key |
| Actor account | Nullable `actor_account` FK; column `actor_account_id`; ACCOUNT -> AUDIT_EVENT D1 |
| Subject account | Nullable `subject_account` FK; column `subject_account_id`; ACCOUNT -> AUDIT_EVENT D2 |
| Content version | Nullable `content_version` FK; column `content_version_id`; CONTENT_VERSION -> AUDIT_EVENT D3 |
| Event type | Controlled `event_type` choices and PostgreSQL CHECK |
| Occurred at | Timezone-aware `occurred_at` timestamp |
| Minimal metadata | JSON `metadata` with event-specific allowlists in Python and PostgreSQL |

The physical table is `audit_event`. Indexes support event-type/time filtering
and age-based maintenance. All three FKs use Django `SET_NULL`. Deleting an
otherwise deletable account or draft clears its event links and preserves the
event. Existing review/publication history may independently protect reference
accounts/editions against deletion; audit links do not override that policy.
There is no duplicate email, display name, or UUID copied into metadata.

## Event catalog and integration

| Event type | Existing/new service | Metadata |
| --- | --- | --- |
| `role.assigned` | `accounts.services.assign_role`; trusted `create_student` and demo setup | `role_name` from the fixed role vocabulary |
| `role.removed` | New `accounts.services.remove_role` | `role_name` |
| `account.activated` | New `accounts.services.set_account_active(is_active=True)` | Empty object |
| `account.disabled` | New `accounts.services.set_account_active(is_active=False)` | Empty object |
| `content.reviewed` | `reference.services.review_content_version` | `decision`, `reviewed_revision` |
| `content.published` | `reference.services.publish_content_version` | Empty object |
| `content.retired` | `reference.services.retire_content_version` | Empty object |

Role/status administration requires the administrator business role, not Django
staff/superuser flags. Role assignment/removal serializes through the affected
account row; no-op assignments, absent removals, and unchanged activation states
do not produce duplicate events. Role checks also verify persisted active status,
so a stale in-memory account cannot retain disabled privileges.

Trusted initial account setup has no signed-in actor: its `role.assigned` event
uses a null actor and the newly created account as subject. Other new events
require an actor. Account events require a subject; content events require a
version. Those links can later become null through parent deletion.

Review events include both approvals and requests for changes, without copying
review notes. Content retirement here means the implemented version-retirement
service. Skill retirement, draft text edits, profile edits, sign-in attempts,
comparison reads/creation, and account deletion are outside this initial catalog.
Add event types deliberately if the team later expands the scope.

This batch audits supported services and the existing demo setup command. Direct
ORM/SQL business mutations do not automatically emit events. Future views,
imports, or management tools must call the supported services to retain coverage.
Do not use Django signals or `transaction.on_commit` to substitute for the atomic
recording policy. Old actions are not backfilled as if they occurred today.

## Read access and event protection

```python
from auditing.services import get_audit_event, list_audit_events

events = list_audit_events(actor=request.user)
reviews = list_audit_events(actor=request.user, event_type="content.reviewed")
event = get_audit_event(actor=request.user, event_id=event_id)
```

No audit HTTP routes or screens are exposed in this batch. Administrators read
through these services; there is no public event-creation or editing endpoint.
The internal `_record_event` writer is reserved for already-authorized business
services and requires an enclosing transaction.

PostgreSQL rejects changes to event identity, event type, timestamp, and metadata;
reference links can only stay unchanged or become null, never be reassigned or
restored. This exception supports Django's deletion collector, which clears links
before deleting parents. Ordinary SQL can also clear a link; the guard is not
proof that every cleared link came from parent deletion.

Metadata allowlists reject additional keys and arbitrary strings such as review
notes, passwords, session tokens, evidence text, and profile information. The
fixed event catalog and limited fields are also enforced for direct event writes.
The database rejects deletion of events still within the one-year retention floor.
These controls support application history; database administrators still control
DDL, triggers, and direct inserts. This is not a tamper-proof external audit log
or database-level authorization system.

## One-year retention and maintenance

Use one calendar year in UTC, with February 29 mapping to February 28 in the
previous year. Delete only events strictly older than the cutoff. Python computes
the maintenance filter; PostgreSQL independently enforces the same retention floor.
Only event rows are purged; accounts, content, and comparison records are untouched.

From the repository root:

```sh
# Preview eligible events; makes no changes.
.venv/bin/python src/backend/manage.py purge_audit_events

# Trusted maintenance operation: delete only events beyond retention.
.venv/bin/python src/backend/manage.py purge_audit_events --execute
```

Before deployment, schedule the execute command daily using the hosting platform's
scheduler and the deployment's configured environment/interpreter. For example,
a scheduler running with the repository as its working directory can invoke the
second command at 03:00 UTC daily. No process or crontab is installed by this
schema batch; until scheduling is configured, run maintenance manually. A daily
schedule means an eligible row may remain until the next successful run. Monitor
job failures and apply the same retention decision to backup handling separately.

## Migrations and verification

`auditing.0001_initial` creates AUDIT_EVENT, its nullable references, indexes, and
event-type CHECK. `auditing.0002_event_guards` adds the metadata, attribution,
immutable-history, and retention trigger, with explicit reverse SQL.

```sh
.venv/bin/python src/backend/manage.py test core accounts skills reference comparisons auditing
.venv/bin/python src/backend/manage.py check
.venv/bin/python src/backend/manage.py makemigrations --check --dry-run
```

The 22 audit tests cover role/status changes and no-ops, permission denial,
stale disabled-account privileges, content events, rollback on action/logging
failure, outer rollback, nullable links, minimal metadata, direct SQL protections,
calendar/leap-day retention, purge preview/execution, and migration reversal.
The full project suite now contains 199 tests and uses an isolated PostgreSQL test
database. Local migrations preserve existing application data and create an empty
audit table, without fabricating historical events or granting administrator roles.
