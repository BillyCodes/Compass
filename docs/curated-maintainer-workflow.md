# Curated maintainer workflow

Use `compass_curated` for the local presentation and keep synthetic seeds in the
separate development database. From the repository root on macOS:

```sh
export POSTGRES_DB=compass_curated
.venv/bin/python src/backend/manage.py migrate
.venv/bin/python src/backend/manage.py runserver 127.0.0.1:8000
```

Sign in with a separately provisioned maintainer or business administrator and
open `/maintainer/`. Public registration still creates students only.

## Starting actions

- **Import O*NET careers/skills** previews the five selected computing careers
  from the preserved O*NET 31.0 occupation and software CSVs. GET is read-only;
  the CSRF-protected import POST creates drafts, sources and 16 selected software
  skills per career: the six shared examples plus ten additional occupation-specific
  examples. Shared skills are deduplicated across the catalog. Existing
  skill names/categories are preserved. No proficiency requirements are inferred.
- **Add BLS career context** filters to career editions. On a draft, **Add BLS
  source** prepopulates the matching profile link and occupation code where an
  O*NET source is present. Review the actual BLS page; a preset is not evidence
  that its context or reuse terms have been reviewed. Use a successor for changes
  to published editions. Link-only is the starting usage; change it if text is
  copied, adapted or interpreted and complete the corresponding credits.
- **Add learning resource** creates an MIT OCW link draft, resource details and
  citation together. Enter the actual archived URL, edition and reviewed
  prerequisites/placement. Write your own short introduction, rather than pasting
  course text into the link-only workflow. Review topic coverage before adding
  skill mappings. This is an external resource, not a university course selection,
  enrollment, certification or automatic proficiency award.
- **Write original Field Note** starts an original insight draft. Enter an
  accurate author name and confirm originality/citation of borrowed material.
  Author details and skill tags are edited separately with revision checks.
  Employer, years of experience, quotes and projects are optional; unknown
  experience is stored as null, not an invented professional biography. Original
  Changing the attributed author requires fresh originality confirmation. Original
  notes keep their explicit personal-reflection label and may publish without
  fabricated external sources.

The general editor remains available. Draft source actions offer provider presets
and a reusable existing-source picker. Existing source reuse adds an edition's
usage, change notes and additional credit without rewriting shared metadata.
Published source corrections still use the existing replacement workflow.

## Import behavior

The optional local management command previews by default:

```sh
.venv/bin/python src/backend/manage.py import_onet_careers --actor YOUR_MAINTAINER_EMAIL
.venv/bin/python src/backend/manage.py import_onet_careers --actor YOUR_MAINTAINER_EMAIL --apply
```

This is a trusted local database-management command, not a web authentication
endpoint. It requires the named account to be an active content editor. It never
creates accounts or publishes records. `--source-dir` is for another preserved
copy of the two **31.0** CSVs; other releases need an explicit importer update.

A persistent occupation-code identity and a transaction-scoped PostgreSQL advisory
lock serialize imports. Raw occupation rows, software rows, exact file SHA-256
hashes, source edition, IDs and Compass normalization notes are retained in the
edition's sources. Retrieval time records local file ingestion, not a claimed
new download from O*NET. The original CSV files remain untouched.

Repeated unchanged imports skip existing careers, including edited drafts, while
adding missing selected skills to the catalog. This catalog refresh does not change
edition bodies, requirements, publication state, source snapshots or draft revisions. Changed
files produce successor drafts for previously published/retired editions of active
items. Existing draft conflicts stop the entire batch rather than replacing work.
Retired content items are skipped. The whole import is atomic. Source-file changes
between the browser preview and import require a fresh preview.

Imported career drafts deliberately have no scoring requirements. In each draft,
review software associations and use **Add or update requirement** to choose
Compass-authored levels (0–5), weights and mandatory flags. These values are not
O*NET ratings. At least one positive-level, positive-weight requirement is required
for publication. Do not invent source support for editorial choices.

## Review and publication

Search/filter by title/body/source ID, kind, origin, provider, status, or drafts
with blockers. Pagination preserves filters. **Preview & checks** displays content,
external learning links, original authorship, requirements/coverage and source
credits, including occupation IDs and downloadable-file hashes. It lists concrete
missing metadata before opening publication confirmation.

Readiness diagnostics guide editing; existing PostgreSQL publication guards remain
authoritative at submission time. Direct publication still requires an active
editor and the exact draft revision. No second-person approval is introduced.
Published bodies, source history, author profiles/tags and saved comparisons retain
the existing immutable-edition protections.

## Source review references

- [O*NET 31.0 database license and exceptions](https://www.onetcenter.org/license_db.html):
  dataset/USDOL credit, CC BY 4.0 link, specific Compass changes and non-endorsement.
- [BLS OOH FAQs](https://www.bls.gov/ooh/about/OOH-FAQs.htm): cite the exact profile;
  before including wage/outlook values record wage year, geography, SOC code and
  projection period in raw metadata. Use developer/architect figures on combined
  pages. Check separately credited third-party material.
- [MIT OCW terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/): linking and
  copying/adapting are separate uses. Covered copies/adaptations need applicable
  instructor credits, license and modifications, with resource-specific exceptions.

See the [source shortlist](architecture/curated-catalog-sources.md) for the initial
five careers and seven candidate MIT resources. This batch adds the workflows and
five career drafts; it does not automatically import the seven resources, write
personal reflections, supply BLS wage statistics or publish any content. Broader
skill/card/export attribution and the career-first student dashboard remain later
work in the [checklist](architecture/curated-content-checklist.md).

## Career-specific skill picker

On a career draft, open **Add or update requirement**. The picker defaults to the
16 selected examples associated with that career's preserved O*NET source rows.
Use search (normalized name or original source name), the in-demand filter, or
**All active skills** to browse outside that shortlist. “Choose skill” preselects
the entry; saving still requires your reviewed proficiency level, weight and
mandatory flag. In-demand and hot-technology indicators describe source software
associations, not hiring mandates or proficiency levels.

The versioned selection policy is in `reference/career_skills.py`. It records
exact raw names and explicit Compass name normalizations (for example Oracle Java
to Java, and Microsoft PowerShell to PowerShell). Each career gets ten extra
examples beyond the shared six, with overlapping tools deduplicated. Suggestions
are derived from the edition's source snapshot; they do not silently use software
examples from a newer source file. Historical source metadata remains unchanged.

To refresh missing catalog skills for existing careers, preview the normal importer
then run it with `--apply`, or use the browser import action. A career marked
“unchanged” remains unchanged while missing selected skills become available.

The local curated catalog was refreshed and verified: 48 unique active skills
cover the five sets of 16 selected associations. All five requirement pages rendered
successfully. Existing career bodies, statuses, revisions, requirement rows and
source records were compared before/after and preserved. A repeated refresh added
no duplicate skills.
