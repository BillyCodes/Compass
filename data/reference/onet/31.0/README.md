# O*NET 31.0 source files

Original public reference data for Compass's curated career catalog, separate
from the synthetic development data described in `seeds/`.

| File | Purpose | Official download |
| --- | --- | --- |
| `occupation_data.csv` | Occupation codes, titles and descriptions | [Occupation Data CSV](https://www.onetcenter.org/dl_files/database/db_31_0_csv/occupation_data.csv) |
| `software_skills.csv` | Software examples associated with occupations | [Software Skills CSV](https://www.onetcenter.org/dl_files/database/db_31_0_csv/software_skills.csv) |

Source: [O*NET 31.0 Database](https://www.onetcenter.org/database.html), U.S.
Department of Labor, Employment and Training Administration (USDOL/ETA).
Used under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), subject to
the [database license and exceptions](https://www.onetcenter.org/license_db.html).
O*NET is a trademark of USDOL/ETA.

The downloaded files are unmodified. Keep raw source files intact; store curated
subsets and Compass-authored mappings separately. Future releases belong in their
own version directories rather than overwriting this one. These files are not
Django fixtures and are not automatically imported or published.

See the [source shortlist](../../../../docs/architecture/curated-catalog-sources.md)
and [implementation checklist](../../../../docs/architecture/curated-content-checklist.md)
for planned review, attribution and import workflows.
