"""The classifier's verdicts, in memory: proven-safe, requires-review, invalid, with reasons (#39, #72, #35)."""
import copy
import hashlib
import json
import unittest

from tooling.practice_ci import compatibility as c

D = "https://json-schema.org/draft/2020-12/schema"


def schema(**kw):
    return dict({"$schema": D, "type": "object"}, **kw)


def review(old, new, tighten=()):
    r = c.classify(old, new, tighten)
    return r["verdict"], [x["path"] for x in r["reasons"]]


class Verdicts(unittest.TestCase):
    def test_same_is_proven_safe(self):
        s = schema(properties={"a": {"type": "string"}})
        self.assertEqual(c.classify(s, copy.deepcopy(s))["verdict"], c.PROVEN_SAFE)

    def test_reasons_name_the_rule(self):
        r = c.classify(schema(maxItems=3), schema(maxItems=4))
        self.assertEqual(r["reasons"], [{"path": "maxItems", "rule": "maximum-raised"}])

    def test_unknown_keyword_changed_means_review(self):
        self.assertEqual(review(schema(**{"x-new": 1}), schema(**{"x-new": 2})), (c.REQUIRES_REVIEW, ["x-new"]))

    def test_type_removed_or_widened(self):
        self.assertEqual(review(schema(properties={"a": {"type": "string"}}), schema(properties={"a": {}}))[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(schema(properties={"a": {"type": "string"}}),
                                schema(properties={"a": {"type": ["string", "null"]}}))[0], c.REQUIRES_REVIEW)

    def test_type_narrowed_is_safe(self):
        self.assertEqual(review(schema(properties={"a": {"type": ["string", "null"]}}),
                                schema(properties={"a": {"type": "string"}}))[0], c.PROVEN_SAFE)

    def test_ref_removed_or_retargeted(self):
        old = schema(properties={"a": {"$ref": "#/$defs/x"}}, **{"$defs": {"x": {"type": "string"}}})
        gone = schema(properties={"a": {}}, **{"$defs": {"x": {"type": "string"}}})
        root = schema(properties={"a": {"$ref": "#"}}, **{"$defs": {"x": {"type": "string"}}})
        self.assertEqual(review(old, gone)[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(old, root)[0], c.REQUIRES_REVIEW)

    def test_composition_changes(self):
        base = schema(properties={"a": {"anyOf": [{"type": "string"}]}})
        grown = schema(properties={"a": {"anyOf": [{"type": "string"}, {"type": "null"}]}})
        self.assertEqual(review(base, grown)[0], c.REQUIRES_REVIEW)

    def test_property_added_under_closed_object(self):
        old = schema(additionalProperties=False, properties={})
        new = schema(additionalProperties=False, properties={"x": {}})
        self.assertEqual(review(old, new), (c.REQUIRES_REVIEW, ["properties/x"]))

    def test_false_property_schema_opened(self):
        old = schema(additionalProperties=False, properties={"x": False})
        new = schema(additionalProperties=False, properties={"x": {}})
        self.assertEqual(review(old, new)[0], c.REQUIRES_REVIEW)

    def test_change_under_not_means_review_even_when_tighter(self):
        old = schema(properties={"s": {"not": {"maxLength": 5}}})
        new = schema(properties={"s": {"not": {"maxLength": 3}}})
        verdict, paths = review(old, new)
        self.assertEqual(verdict, c.REQUIRES_REVIEW)
        self.assertIn("properties/s/not", paths)

    def test_disallow_is_reversing(self):
        pair = ["^a+$", "^a{2,}$"]
        listed = [{"sha256": hashlib.sha256(json.dumps(pair, separators=(",", ":")).encode()).hexdigest(), "why": "narrower"}]
        d3 = {"$schema": "http://json-schema.org/draft-03/schema#", "disallow": [{"pattern": pair[0]}]}
        d3n = {"$schema": "http://json-schema.org/draft-03/schema#", "disallow": [{"pattern": pair[1]}]}
        self.assertEqual(review(d3, d3n, listed)[0], c.REQUIRES_REVIEW)

    def test_reference_under_not_in_the_new_file_only(self):
        pair = ["^a+$", "^a{2,}$"]
        listed = [{"sha256": hashlib.sha256(json.dumps(pair, separators=(",", ":")).encode()).hexdigest(), "why": "narrower"}]
        old = schema(properties={"a": {"pattern": pair[0]}})
        new = schema(properties={"a": {"pattern": pair[1]}, "b": {"not": {"$ref": "#/$defs/x"}}}, **{"$defs": {"x": {}}})
        self.assertEqual(review(old, new, listed)[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(old, schema(properties={"a": {"pattern": pair[1]}}), listed), (c.PROVEN_SAFE, []))

    def test_malformed_tighten_list_is_invalid(self):
        self.assertEqual(c.classify(schema(), schema(), [{"sha256": "x", "why": "y"}])["verdict"], c.INVALID)


class Siblings(unittest.TestCase):
    def test_min_contains_below_one_added_is_review_one_is_safe(self):
        old = schema(contains={"type": "string"})
        self.assertEqual(review(old, dict(old, minContains=0))[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(old, dict(old, minContains=1)), (c.PROVEN_SAFE, []))

    def test_keyword_added_beside_a_reference_under_not_is_review(self):
        base = {"$defs": {"x": {}}, "properties": {"n": {"not": {"$ref": "#/$defs/x"}}}}
        self.assertEqual(review(schema(**base), schema(propertyNames={"maxLength": 3}, **base)),
                         (c.REQUIRES_REVIEW, ["propertyNames"]))
        self.assertEqual(review(schema(properties={}), schema(propertyNames={"maxLength": 3}, properties={})), (c.PROVEN_SAFE, []))


class AllOfInContext(unittest.TestCase):
    """#72: an allOf that only gains branches at its end accepts nothing more."""
    A, B = {"required": ["a"]}, {"required": ["b"]}

    def test_appended_branch_is_safe(self):
        self.assertEqual(review(schema(allOf=[self.A]), schema(allOf=[self.A, self.B])), (c.PROVEN_SAFE, []))

    def test_inserted_or_reordered_or_shrunk_is_review(self):
        self.assertEqual(review(schema(allOf=[self.A, self.B]), schema(allOf=[self.A, {"required": ["c"]}, self.B]))[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(schema(allOf=[self.A, self.B]), schema(allOf=[self.B, self.A]))[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(schema(allOf=[self.A, self.B]), schema(allOf=[self.A]))[0], c.REQUIRES_REVIEW)

    def test_appended_beside_unevaluated_properties_is_review(self):
        self.assertEqual(review(schema(allOf=[self.A], unevaluatedProperties=False),
                                schema(allOf=[self.A, self.B], unevaluatedProperties=False)), (c.REQUIRES_REVIEW, ["allOf"]))

    def test_appended_under_not_is_review(self):
        old = schema(properties={"s": {"not": {"allOf": [self.A]}}})
        new = schema(properties={"s": {"not": {"allOf": [self.A, self.B]}}})
        self.assertEqual(review(old, new), (c.REQUIRES_REVIEW, ["properties/s/not"]))

    def test_anyof_and_prefixitems_growth_stay_review(self):
        self.assertEqual(review(schema(anyOf=[self.A]), schema(anyOf=[self.A, self.B]))[0], c.REQUIRES_REVIEW)
        self.assertEqual(review(schema(prefixItems=[{}]), schema(prefixItems=[{}, {}]))[0], c.REQUIRES_REVIEW)


class CheckProfile(unittest.TestCase):
    ROWS = [{"schema": "schema.json", "instances": "examples"},
            {"schema": "schema.json", "instances": "counter-examples", "expect": "fail", "each": "true"}]

    def test_unchanged_is_safe(self):
        self.assertEqual(c.classify_check(self.ROWS, copy.deepcopy(self.ROWS))["verdict"], c.PROVEN_SAFE)

    def test_any_change_needs_review(self):
        for mutate in (lambda r: r.pop(), lambda r: r[1].update(expect="pass"), lambda r: r[1].update(schema="x.json"),
                       lambda r: r[1].pop("each"), lambda r: r.append({"schema": "s", "instances": "i"})):
            new = copy.deepcopy(self.ROWS)
            mutate(new)
            self.assertEqual(c.classify_check(self.ROWS, new)["verdict"], c.REQUIRES_REVIEW)

    def test_policy_check_object(self):
        old = {"schema": "constants.schema.json", "instances": "constants.json"}
        self.assertEqual(c.classify_check(old, dict(old, schema="other.json"))["verdict"], c.REQUIRES_REVIEW)

    def test_not_a_profile_is_invalid(self):
        self.assertEqual(c.classify_check("x", self.ROWS)["verdict"], c.INVALID)


if __name__ == "__main__":
    unittest.main()
