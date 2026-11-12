# Curated catalog source shortlist

Reviewed November 12, 2026. Research only: no records have been imported or
published. Career identifiers were checked against the downloaded
[occupation_data.csv](../../data/reference/onet/31.0/occupation_data.csv);
software examples were checked in
[software_skills.csv](../../data/reference/onet/31.0/software_skills.csv).
The original downloads and their source information are kept under
[`data/reference/onet/31.0/`](../../data/reference/onet/31.0/README.md).

## Career profile sources

Use O*NET occupation codes as stable source identifiers. BLS pages supplement
O*NET descriptions with education, duties, wages and outlook. These are occupation
profiles, not current employer job announcements.

| Compass career | O*NET-SOC code | BLS Occupational Outlook Handbook source | Curation note |
| --- | --- | --- | --- |
| Software Developers | 15-1252.00 | [Software Developers, Quality Assurance Analysts, and Testers](https://www.bls.gov/ooh/computer-and-information-technology/software-developers.htm) | The page covers several occupations; use software developer figures rather than QA/tester or combined-group figures. |
| Information Security Analysts | 15-1212.00 | [Information Security Analysts](https://www.bls.gov/ooh/computer-and-information-technology/information-security-analysts.htm) | Capture education and experience context alongside the duties. |
| Data Scientists | 15-2051.00 | [Data Scientists](https://www.bls.gov/ooh/math/data-scientists.htm) | Distinguish occupational context from a promise that a short course establishes readiness. |
| Computer Systems Analysts | 15-1211.00 | [Computer Systems Analysts](https://www.bls.gov/ooh/computer-and-information-technology/computer-systems-analysts.htm) | Include systems analysis and organizational needs, rather than treating this as a programming-only role. |
| Database Architects | 15-1243.00 | [Database Administrators and Architects](https://www.bls.gov/ooh/computer-and-information-technology/database-administrators.htm) | Select architect-specific figures; do not substitute administrator or combined-group figures. |

Before publishing wage or outlook values, record the wage reference year,
projection period, geography, occupation code and retrieval date. National median
pay is not an entry-level salary estimate or a Mississippi-specific estimate.

## Learning resource shortlist

Career and skill mappings below are proposed Compass editorial decisions. They
are not MIT endorsements, guaranteed outcomes or automatic proficiency awards.
Academic course level is not a Compass 0–5 proficiency level.

| Resource | Topic coverage suitable for review | Proposed career associations | Placement |
| --- | --- | --- | --- |
| [6.0001 Introduction to Computer Science and Programming in Python, Fall 2016](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/) | Python and programming foundations | Shared foundation across the five careers | Introductory |
| [6.005 Software Construction, Spring 2016](https://ocw.mit.edu/courses/6-005-software-construction-spring-2016/) | Testing, specifications, abstraction, object-oriented design and concurrency | Software Developers; Computer Systems Analysts | Follow-up after programming foundations |
| [6.0002 Introduction to Computational Thinking and Data Science, Fall 2016](https://ocw.mit.edu/courses/6-0002-introduction-to-computational-thinking-and-data-science-fall-2016/) | Python-based computational problem solving and data science | Data Scientists; Software Developers | Continuation of 6.0001 |
| [6.036 Introduction to Machine Learning, Fall 2020](https://ocw.mit.edu/courses/6-036-introduction-to-machine-learning-fall-2020/) | Modeling, prediction, generalization and machine learning | Data Scientists | Undergraduate; review prerequisites before recommending |
| [6.033 Computer System Engineering, Spring 2018](https://ocw.mit.edu/courses/6-033-computer-system-engineering-spring-2018/) | Operating systems, networks, modularity, security and fault tolerance | Computer Systems Analysts; Software Developers; Information Security Analysts | Systems foundation for students with prior computing experience |
| [6.858 Computer Systems Security, Fall 2014](https://ocw.mit.edu/courses/6-858-computer-systems-security-fall-2014/) | Threat models, OS/network security and web application security | Information Security Analysts; Software Developers | Graduate-level advanced resource |
| [6.830 Database Systems, Fall 2010](https://ocw.mit.edu/courses/6-830-database-systems-fall-2010/pages/syllabus/) | Relational models, query processing/optimization, transactions and recovery | Database Architects; Software Developers; Data Scientists | Advanced database internals; not an introductory SQL course |

The downloaded software file includes examples such as Python, SQL, PostgreSQL,
Git, Linux and Docker for the selected careers. The MIT shortlist covers relevant
foundations but does not provide a dedicated beginner tutorial for every product.
Do not assign PostgreSQL, Docker or Git coverage simply because a course is
associated with a career that uses them. Review specific lessons and assignments.

These are archived course editions. Preserve the course year and review software
setup instructions before publishing a recommendation. Some assignments depend
on institutional infrastructure or external resources; do not imply everything
is runnable unchanged. Begin with links to source pages rather than copying
complete courses or third-party materials into Compass.

## Reuse and attribution

- [BLS OOH FAQ](https://www.bls.gov/ooh/about/OOH-FAQs.htm): BLS describes its
  public-domain material as reusable and requests attribution. Check separately
  credited photography or other third-party material before copying it.
- [MIT OCW terms](https://ocw.mit.edu/pages/privacy-and-terms-of-use/): the general
  content license is CC BY-NC-SA 4.0, with attribution, noncommercial and
  share-alike requirements for covered copies/adaptations. Respect separate
  notices on individual resources. Record instructors and the applicable license
  when copying or adapting material; do not imply MIT affiliation.
- [O*NET database license](https://www.onetcenter.org/license_db.html): follow the
  database's CC BY 4.0 terms and stated exceptions. Credit the dataset version and
  USDOL/ETA, link the license, and identify modifications.

## Proposed first publication batch

1. Five career drafts with O*NET identifiers and matching BLS citations.
2. Seven external learning-resource drafts, recording provider, edition year,
   source URL, license information and prerequisites.
3. Normalize selected software examples into Compass skills, preserving source
   wording/identifiers and recording any aliases or consolidation decisions.
4. Review learning mappings against actual course content. Mark coverage levels,
   career requirement levels, weights and mandatory flags as Compass-authored
   interpretations; the presence of an O*NET software example does not establish
   any of those values.
5. Publish through the existing maintainer workflow in the curated database.

External MIT materials fit the existing resource kind. Keep university course
selections distinct unless the team explicitly decides to broaden that feature.
This shortlist does not supply real job postings or professional Field Notes.
