"""SQL selection must agree with the scoring oracle and load only winners."""
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from comparisons.scoring import Requirement, calculate
from comparisons.tests.factories import approve, setup_actors, target
from pilot.services import presenter
from reference.models import ContentRequirement, ContentVersion
from reference.selectors import latest_available
from reference.services import create_successor_draft, retire_content_version, set_requirement


class DashboardJobMatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        setup_actors(cls)
        for n in range(18):
            target(cls, "job", requirements=[
                (cls.python, n % 6, "0" if n % 4 == 0 else "999999.9999", n % 2 == 0),
                (cls.sql, (n * 3 + 1) % 6, "0.0001" if n % 3 else "3.1415", n % 3 == 0),
            ])
        # Exactly halfway between hundredths: SQL and Python both round up.
        target(cls, "job", requirements=[(cls.python, 1, "1", False), (cls.sql, 1, "19999", False)])
        # Relevant zero-weight mandatory skills still permit a provisional score.
        target(cls, "job", requirements=[(cls.python, 3, "0", True), (cls.sql, 3, "1", False)])

    def oracle(self, levels, limit):
        results = []
        for version in latest_available("job").prefetch_related("requirements"):
            try:
                calc = calculate([
                    Requirement(r.skill_id, r.required_level, r.weight, r.mandatory)
                    for r in version.requirements.all()
                ], levels)
            except ValidationError:
                continue
            results.append((version.pk, calc))
        results.sort(key=lambda row: -row[1].score)
        return results[:limit]

    def test_ranking_and_card_fields_match_full_catalog_scoring(self):
        for levels in (
            {self.python.pk: 0}, {self.python.pk: 1}, {self.python.pk: 5},
            {self.sql.pk: 0}, {self.sql.pk: 2},
            {self.python.pk: 2, self.sql.pk: 5},
            {self.python.pk: 5, self.sql.pk: 3},
            {self.python.pk: None, self.sql.pk: 4},
        ):
            for limit in (1, 3, 25):
                with self.subTest(levels=levels, limit=limit):
                    expected = self.oracle(levels, limit)
                    actual = presenter.live_job_matches(levels, limit)
                    self.assertEqual([card["pk"] for card in actual], [pk for pk, _ in expected])
                    for card, (_, calc) in zip(actual, expected):
                        for field in ("score", "mandatory_status", "reported_count", "relevant_count", "is_provisional"):
                            self.assertEqual(card[field], getattr(calc, field))
        halfway = [card for card in presenter.live_job_matches({self.python.pk: 1}, 25)
                   if card["score"] == Decimal("0.01")]
        self.assertTrue(halfway)

    def test_only_winners_are_loaded_and_scored_with_constant_query_count(self):
        levels = {self.python.pk: 3, self.sql.pk: 3}
        loaded = {"editions": 0, "requirements": 0}
        load_edition = ContentVersion.from_db
        load_requirement = ContentRequirement.from_db

        def edition_from_db(cls, *args, **kwargs):
            loaded["editions"] += 1
            return load_edition(*args, **kwargs)

        def requirement_from_db(cls, *args, **kwargs):
            loaded["requirements"] += 1
            return load_requirement(*args, **kwargs)

        with (patch.object(presenter, "calculate", wraps=calculate) as scoring,
              patch.object(ContentVersion, "from_db", classmethod(edition_from_db)),
              patch.object(ContentRequirement, "from_db", classmethod(requirement_from_db))):
            with self.assertNumQueries(3):
                cards = presenter.live_job_matches(levels)
        self.assertEqual(len(cards), 3)
        self.assertEqual(scoring.call_count, 3)
        self.assertEqual(loaded, {"editions": 3, "requirements": 6})

    def test_empty_inputs_or_nonpositive_limit_do_not_query(self):
        with self.assertNumQueries(0):
            self.assertEqual(presenter.live_job_matches({}), [])
            self.assertEqual(presenter.live_job_matches({self.python.pk: None}), [])
            self.assertEqual(presenter.live_job_matches({self.python.pk: 3}, 0), [])
            self.assertEqual(presenter.live_job_matches({self.python.pk: 3}, -1), [])

    def test_latest_edition_selected_before_relevance_and_retirement(self):
        old = target(self, "job", requirements=[(self.python, 1, "1", True)])
        new = create_successor_draft(actor=self.author, version_id=old.pk)
        ContentRequirement.objects.filter(version=new).delete()
        new.refresh_from_db()
        set_requirement(actor=self.author, version_id=new.pk, expected_revision=new.draft_revision,
                        skill_id=self.sql.pk, required_level=1, weight="1", mandatory=True)
        new = approve(self, new)
        levels = {self.python.pk: 5}
        ids = {card["pk"] for card in presenter.live_job_matches(levels, 100)}
        self.assertNotIn(old.pk, ids)
        self.assertNotIn(new.pk, ids)
        retire_content_version(actor=self.author, version_id=new.pk)
        ids = {card["pk"] for card in presenter.live_job_matches(levels, 100)}
        self.assertIn(old.pk, ids)
        self.assertNotIn(new.pk, ids)

    def test_retired_skill_exclusion_matches_existing_availability(self):
        self.python.status = "retired"
        self.python.save(update_fields=["status"])
        with self.assertNumQueries(1):
            self.assertEqual(presenter.live_job_matches({self.sql.pk: 3}), [])
