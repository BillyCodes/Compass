from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from comparisons.scoring import Requirement, calculate


def req(skill, level=3, weight="1", mandatory=False):
    return Requirement(skill, level, Decimal(weight), mandatory)


class ScoringTests(SimpleTestCase):
    def test_agreed_weighted_example(self):
        result = calculate([req("python",4,"2"), req("sql",3), req("communication",2)], {"python":3,"sql":3,"communication":1})
        self.assertEqual(result.score, Decimal("75.00"))
        self.assertEqual(result.mandatory_status,"not_applicable")
        self.assertFalse(result.is_provisional)

    def test_excess_proficiency_is_capped(self):
        result = calculate([req("a",1),req("b",4)],{"a":5,"b":0})
        self.assertEqual(result.score,Decimal("50.00"))

    def test_unknown_and_explicit_zero_have_same_score_but_different_outcomes(self):
        requirements = [req("a"),req("b",mandatory=True)]
        unknown = calculate(requirements,{"a":3})
        zero = calculate(requirements,{"a":3,"b":0})
        self.assertEqual(unknown.score,zero.score)
        self.assertEqual(unknown.score,Decimal("50.00"))
        self.assertTrue(unknown.is_provisional)
        self.assertEqual(unknown.mandatory_status,"undetermined")
        self.assertEqual(unknown.outcomes[1].gap,None)
        self.assertFalse(zero.is_provisional)
        self.assertEqual(zero.mandatory_status,"not_met")
        self.assertEqual(zero.outcomes[1].gap,3)

    def test_known_mandatory_gap_precedes_unknown(self):
        result = calculate([req("a",mandatory=True),req("b",mandatory=True)],{"a":1})
        self.assertEqual(result.mandatory_status,"not_met")

    def test_zero_weight_mandatory_affects_status_and_completeness_only(self):
        result = calculate([req("a"),req("b",weight="0",mandatory=True),req("c",weight="0")],{"a":3})
        self.assertEqual(result.score,100)
        self.assertEqual(result.mandatory_status,"undetermined")
        self.assertEqual((result.reported_count,result.relevant_count),(1,2))

    def test_zero_required_level_is_automatically_met_and_not_scored(self):
        result = calculate([req("a"),req("b",0,"99",True)],{"a":3})
        self.assertEqual(result.score,100)
        self.assertEqual(result.mandatory_status,"met")
        self.assertEqual(result.outcomes[1].gap,0)
        self.assertFalse(result.is_provisional)

    def test_all_unknown_or_only_irrelevant_input_rejected(self):
        for levels in ({},{"other":5},{"optional":5}):
            with self.assertRaises(ValidationError):
                calculate([req("a"),req("optional",weight="0")],levels)

    def test_target_without_scored_requirement_rejected(self):
        for rows in ([],[req("a",0)],[req("a",weight="0")]):
            with self.assertRaises(ValidationError):
                calculate(rows,{"a":3})

    def test_partial_ratios_and_final_half_up_rounding(self):
        self.assertEqual(calculate([req("a",3)],{"a":1}).score,Decimal("33.33"))
        self.assertEqual(calculate([req("a",1,"1"),req("b",1,"31")],{"a":1,"b":0}).score,Decimal("3.13"))
        self.assertEqual(calculate([req("a",3),req("b",3)],{"a":1,"b":2}).score,Decimal("50.00"))

    def test_invalid_inputs_and_duplicate_requirements_rejected(self):
        for value in (True,1.5,-1,6,"3"):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                calculate([req("a")],{"a":value})
        for weight in ("NaN","Infinity","-1","1000000"):
            with self.assertRaises(ValidationError):
                calculate([req("a",weight=weight)],{"a":3})
        with self.assertRaises(ValidationError):
            calculate([req("a"),req("a")],{"a":3})
