# Repeatable synthetic sample data

The team has agreed to use Mockaroo for synthetic development data. The account
and domain models are still being finalized, so this directory defines the
convention; it does not yet contain an importer or runnable seed command.

## Database lead workflow

1. Align the ERD with reviewed Django models and committed migrations. Django
   migrations create and modify tables; Mockaroo exports do not define the schema.
2. Save the Mockaroo generation schema/settings with a documented version. Export
   CSV or JSON containing synthetic records only. Retain the exact reviewed export
   used for a demo/test dataset: regenerating random data need not reproduce it.
3. Document field mappings, allowed values, and stable synthetic keys that connect
   profiles, skills, courses, and comparisons. Import parent records before child
   records and resolve relationships through those keys.
4. Once the models exist, implement an app-owned Django management command that
   validates the export and creates or updates records using stable keys. Re-running
   the same import should not create duplicates. Reject invalid references and
   incompatible dataset versions, and use a transaction for each logical import.
5. Create synthetic accounts through Django's user manager/password methods. Do
   not import Mockaroo-generated strings directly into password-hash fields.
6. Keep a small set of manually calculated comparison examples with expected
   results, alongside any larger random dataset. Random rows do not establish
   scoring correctness.

Raw Mockaroo JSON is not automatically a Django fixture. A fixture or importer
must use the agreed model/field structure. Keep raw exports and mapping metadata
distinct when those files are added. No real student records or credentials belong
in these datasets, and no automatic seeding runs when Compose starts.
