# Curated content and presentation readiness checklist

Created November 12, 2026. This is an implementation plan; unchecked items are
not implemented. Companion research: [curated catalog sources](curated-catalog-sources.md).

## Scope and proposed decisions

- Focus the curated presentation on five computing careers, sourced skills,
  linked learning resources and original Field Notes.
- Use the downloaded O*NET database for occupation/technology associations, BLS
  Occupational Outlook Handbook for career context, and MIT OpenCourseWare for
  external learning resources.
- Keep synthetic employer postings in the development dataset. Real employer
  postings, scraping and live job feeds are outside this batch. Retain existing
  comparison/history functionality; avoid empty job-first presentation in the
  curated experience.
- Keep `seed_compass` optional for development. Do not load it into the curated
  database. A curated catalog and personally configured accounts can support the
  presentation without collecting other students' resumes or academic records.
- Retain direct publication by active content maintainers/administrators. Keep
  immutable published editions, successor drafts, retirement, revision checks,
  ownership boundaries and audit events.
- A maintainer is an explicitly authorized Compass editor, initially a trusted
  project team member. The role does not require being a working professional,
  and it does not grant access to students' private records. Author biographies
  must accurately describe the person rather than imply professional credentials.

## Starting implementation facts (before Phase 1)

- `AccountRole` governs business permissions. Active maintainers and business
  administrators pass `require_content_editor`; public registration creates a
  student account. Django staff/superuser flags alone do not grant these roles.
- The normal login page already sends maintainers/administrators to
  `/maintainer/`, unless a safe explicit `next` destination takes precedence.
  The demo email address is not what grants maintainer access.
- Audited `assign_role`, `remove_role` and account-activation services already
  exist. Role changes require a business administrator. There is no non-demo
  provisioning UI/command or registered Django account-admin interface yet.
- `ReferenceSource` currently stores only a title, URL/identifier and collection
  date. It cannot express the complete licensing/provenance plan below.
- Student learning/Field Note detail pages do not currently render a complete
  source/attribution section.
- Publication currently requires at least one reference source for every kind,
  including `insight`, in PostgreSQL as well as application workflows. An
  original-note option must change that rule explicitly rather than fabricate a
  source or merely hide a form field.

## Phase 1 — Define provenance and original-content rules

- [x] Define origin categories: curated external content, original Field Note,
      and synthetic demonstration content. Separate origin from content type:
      career/resource/insight and draft/published/retired still have distinct roles.
- [x] Extend source metadata with publisher/author, source URL, license name and
      URL, attribution text, dataset/course edition, and retrieval date. Preserve
      source identifiers separately from editable titles.
- [x] Record how each edition uses a source: link only, copied excerpt, adapted
      content, or team-authored interpretation. Record changes and applicable
      credit/notice per source usage rather than assigning one license to an
      entire mixed-source career profile.
- [x] Track import identity/version and file checksum for O*NET files, plus
      stable occupation IDs and software example mappings. Retain the raw source
      values separately from Compass normalizations and scoring interpretations.
- [x] Define migration/backfill behavior for existing sources and published
      editions. Preserve historical content and guards; do not invent missing
      license information or mutate frozen source records in place.
- [x] Permit an original motivational/reflection Field Note without an external
      citation when authorship and original-content status are recorded. Require
      appropriate citations/permission for borrowed quotations or externally
      derived factual material; a free-draft option is not a citation bypass.
- [x] Label personal reflection clearly. Do not present it as professional advice,
      verified labor-market evidence, or a source of scoring requirements.
- [x] Implement original-note publication eligibility consistently in forms,
      services and a new PostgreSQL guard migration. Require provenance for
      externally sourced records; preserve direct publication without independent
      approval. Establish how existing insight editions are classified on upgrade.

Phase 1 foundation implemented: `reference/0009_content_provenance` adds the
fields and labels existing editions `legacy`; `reference/0010` extends the SQL
publication/history guards. Unknown historical rights remain unknown. Existing
published content remains readable and immutable; a legacy successor must be
classified before publication. New internal/demo drafts default to synthetic,
while the maintainer create form defaults to curated external content.

Source records now support provider, publisher, author, canonical URL, license
name/URL, attribution, edition, external ID, SHA-256 and raw JSON metadata. Each
source link records usage, changes and additional credit. These are storage and
validation foundations; populating import identities and reviewed software-skill
mappings is part of the later importer batch. Raw metadata must be a JSON object.
The existing collection timestamp records retrieval time; source correction keeps
that time rather than falsely implying a fresh retrieval.

Original reflections require the `insight` kind, an author name and an originality/
borrowed-material confirmation. External content still needs citations; any cited
material on an original note also receives provenance validation. Link-only uses
require provider, publisher and source URL without inventing a reuse license;
copies, adaptations and interpretations also require license/credit fields, with
change notes for adaptations/interpretations. O*NET citations additionally require
version, external ID and file checksum. These checks establish required metadata,
not the truth of a license claim; source-specific review remains in Phase 3.

The generic create/edit/source forms expose these fields now. Successor drafts
copy source usage and provenance but require a fresh originality confirmation.
Source corrections preserve published references. Original-note detail pages
label personal reflection, and reference-result/learning/note detail pages render
source credits. Provider-specific dashboard actions, full attribution coverage
across cards/exports, real imports and account provisioning remain unchecked below.

## Phase 2 — Source-aware maintainer workflow

- [ ] Offer clear starting actions: **Import O*NET careers/skills**, **Add BLS
      career context**, **Add learning resource**, and **Write original Field Note**.
      Retain general draft editing for corrections and other supported content.
- [ ] Add dashboard search and filters for origin/provider, content kind, status
      and missing required metadata. Keep pagination and lifecycle actions.
- [ ] Provide a reusable source picker and provider-specific forms with license
      guidance. Prepopulated templates assist the maintainer; they do not certify
      that every resource or third-party asset has the same reuse rights.
- [ ] Support Field Note author details and optional skill tags through the
      maintainer UI. Do not require invented employers, years of experience,
      technical projects or quotes to publish a motivational note.
- [ ] Preview student-facing content, source credits, original-note labels and
      external links before publication. List concrete missing fields when blocked.
- [ ] Import a small selected set into drafts, with validation and a dry-run
      preview. Repeated imports must not duplicate careers/skills, silently
      overwrite published editions, or auto-publish changed external data.
- [ ] Make future external revisions create reviewable successor drafts. Keep
      separate import/source versions and Compass edition numbers.

## Phase 3 — Source-specific requirements and attribution

### O*NET downloadable database

- [ ] Record the dataset version and exact files used, retaining O*NET-SOC codes.
- [ ] Credit the versioned O*NET database and USDOL/ETA, link CC BY 4.0, and
      identify adaptations under the [database license](https://www.onetcenter.org/license_db.html).
      Check its stated exceptions and follow its trademark/non-endorsement guidance.
- [ ] Show source credits wherever imported career/skill content is presented,
      including appropriate attribution access on skill browsing and student pages.
- [ ] Label canonical-name consolidation, aliases, skill categories, requirement
      levels, mandatory flags and weights as Compass-authored where applicable.
      An occupation/software association or demand flag is not a required 0–5
      proficiency level or a mandatory hiring requirement.

### BLS Occupational Outlook Handbook

- [ ] Record and display BLS citations with source links and retrieval dates;
      distinguish direct excerpts from team summaries.
- [ ] Record the wage reference year, geography, SOC code and projection period.
      Use the correct developer/architect figures on combined-occupation pages.
      Do not label national median wages as starting salaries or Mississippi wages.
- [ ] Follow [BLS reuse guidance](https://www.bls.gov/ooh/about/OOH-FAQs.htm): BLS
      describes its public-domain material as reusable and requests attribution.
      Check separate rights before copying third-party photos or other assets.
- [ ] Decide whether the first batch stores contextual text with provenance or
      adds typed wage/outlook fields. Add structured fields only if needed for
      display, validation or comparison; do not strip source dates/units.

### MIT OpenCourseWare

- [ ] Start with external resource links, edition year, provider and accurate
      topic/prerequisite summaries. Do not mirror complete courses in this batch.
- [ ] For copied/adapted covered material, record instructor/author credits, link
      the applicable license, indicate modifications, and satisfy attribution,
      noncommercial and share-alike conditions. Check individual resource notices
      and third-party exceptions under [MIT OCW terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/).
      Linking and copying/adapting are distinct uses.
- [ ] Label advanced database/security resources and review old setup instructions.
      Do not imply MIT enrollment, academic credit, certification or endorsement.
- [ ] Map coverage only to topics actually taught. A linked course never changes
      the student's self-reported proficiency automatically.

### Shared presentation

- [ ] Render human-readable citations, license links and adaptation notices on
      detail pages and suitable attribution access from cards, search and exports.
- [ ] Keep source attribution associated with the published edition when sources
      are corrected, content is retired, or saved comparisons are opened later.
- [ ] Use an honest mix-of-content disclosure: curated public sources, clearly
      marked original reflections and any explicitly labeled synthetic records.
      Replace blanket home-page wording that says all sample content is fictional.

## Phase 4 — Personal accounts and maintainer authorization

- [x] Document the presentation roles: one personal student account and a
      separately provisioned maintainer account for demonstrating content editing.
      Use names/emails chosen by their owners and unique passwords; keep credentials
      outside source control. Existing demo accounts remain development fixtures.
- [x] Use normal registration for the personal student account. Allow realistic
      self-reported skills, interests and optional evidence without requiring real
      resumes, sensitive academic data or other people's information.
- [x] Add an explicit local setup command to bootstrap the first business
      administrator with a securely prompted password. Never promote an account
      automatically at startup, by email domain, or through public registration.
      Define repeat-command behavior without overwriting passwords or privileges.
- [x] Add an administrator-authorized way to provision/grant/revoke maintainer
      access using the existing audited role services. Start with a narrow command;
      add a small role-management UI only if needed. Full Django admin is optional.
- [x] Keep student-only and maintainer-only accounts distinct initially; document
      the routing policy if an account is deliberately assigned both roles later.
- [x] Verify a provisioned maintainer logs in through the normal login page and
      lands at `/maintainer/`. Role revocation and account deactivation must take
      effect on subsequent requests, including an existing session.
- [x] Keep role management administrator-only and student records owner-only.
      Maintainers cannot grant themselves privileges or view other students' data.

Provisioning implemented: see [personal accounts and maintainer access](../account-provisioning.md).
`bootstrap_administrator` creates only the first new business administrator, with
concurrent setup serialized on the administrator role. Existing accounts and
administrator assignments (including disabled ones) are never overwritten.
`manage_maintainer create|grant|revoke` authenticates an active administrator and
uses audited role services. Passwords are hidden prompts, never command-line
arguments. New account creation rolls back if role assignment/auditing fails.
The grant path refuses student accounts/profiles; student registration remains
unchanged. Administrator accounts can already edit content through their own role.

Session revocation, account deactivation and owner-only student access are covered
by tests. Account activation/deactivation services already exist; a broader user
management UI/command is outside this provisioning batch. This phase implements
and documents the workflow; no personal accounts or credentials have been created
on behalf of the user, and the curated database remains a later setup task.

## Phase 5 — Curated database and presentation experience

- [ ] Create/configure `compass_curated` and apply the complete Django migration
      history. Preserve the existing synthetic development database.
- [ ] Add five career drafts and seven linked resource drafts from the research
      shortlist, then validate sources and publish through normal services.
- [ ] Add a small number of clearly attributed original Field Notes, without
      claiming fictional professionals wrote them.
- [ ] Support a useful career-first dashboard when no employer postings exist.
      Make optional job sections unobtrusive and empty states actionable.
- [ ] Ensure course-only labels/claims are not applied to external MIT resources.
      University course selections and external learning resources remain distinct.
- [ ] Add a short setup/demo guide naming the active database, account provisioning
      steps, provenance requirements and reproducible demonstration sequence.

## Verification and completion criteria

- [ ] Fresh install and upgrade migrations preserve sources, editions and history.
- [ ] Original notes publish without fake external sources; curated external
      records with incomplete required provenance cannot publish.
- [ ] Imported copies/adaptations display the correct attribution and license;
      student cards/details and saved results retain access to appropriate credits.
- [ ] Imports validate malformed input, preserve identifiers and remain repeatable.
- [ ] New source metadata and author/profile edits respect published immutability,
      draft revision checks and audit behavior.
- [ ] Shared login works for personal students and provisioned maintainers; public
      registration cannot select privileged roles; unauthorized role changes fail.
- [ ] Curated career comparisons, learning recommendations and original Field
      Notes work with zero synthetic employer postings and no demo accounts.
- [ ] Run the full suite, Django checks and migration consistency checks. Exercise
      the entire workflow at desktop and mobile widths with the curated database.

## Recommended implementation order

1. Provenance schema and original-note publication policy (Phase 1).
2. Non-demo account provisioning and audited maintainer authorization (Phase 4).
3. Source-aware dashboard/forms and student attribution display (Phases 2–3).
4. Small draft import, curated database and career-first presentation (Phase 5).
5. End-to-end verification and documentation.

These changes require additive migrations and workflow updates, not replacement
or simplification of the current database. The checklist does not implement them
or grant reuse permission beyond the applicable source licenses.
