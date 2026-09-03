"""The shapes file is the one artifact meant to leave the machine, so the
function that builds it is the whole security boundary: it must reduce every
value to a type, keeping only field names and enum-like constants.

These tests are adversarial on purpose -- they feed in the kinds of personal
data a real APA response carries and assert none of it survives.
"""

from __future__ import annotations

import json

from tools.capture_apa_graphql import summarize_shape

REALISTIC_RESPONSE = {
    "data": {
        "team": {
            "id": 13082948,
            "name": "Chalk It Up",
            "standing": 3,
            "isTied": False,
            "division": {"id": 436670, "nightOfPlay": "THURSDAY", "format": "EIGHT_BALL"},
            "roster": [
                {
                    "displayName": "Shawna Larsen",
                    "memberNumber": "80200640",
                    "email": "shawna.larsen@example.com",
                    "phone": "555-867-5309",
                    "skillLevel": 3,
                    "ppm": 2.33,
                    "member": None,
                },
                {
                    "displayName": "Robert Chen",
                    "memberNumber": "80200641",
                    "email": "rchen@example.com",
                    "phone": "555-123-4567",
                    "skillLevel": 5,
                    "ppm": 1.9,
                    "member": {"id": 7},
                },
            ],
        }
    }
}

PERSONAL_STRINGS = [
    "Chalk It Up", "Shawna Larsen", "Robert Chen",
    "shawna.larsen@example.com", "rchen@example.com",
    "555-867-5309", "555-123-4567", "80200640", "80200641",
]


class TestNoValuesSurvive:
    def test_no_personal_string_appears_anywhere_in_the_output(self):
        rendered = json.dumps(summarize_shape(REALISTIC_RESPONSE))
        for secret in PERSONAL_STRINGS:
            assert secret not in rendered, f"{secret!r} leaked into the shapes output"

    def test_numbers_become_types_not_values(self):
        rendered = json.dumps(summarize_shape(REALISTIC_RESPONSE))
        for number in ("13082948", "436670", "2.33", "1.9"):
            assert number not in rendered

    def test_field_names_are_kept(self):
        """Names are the schema -- they are the entire point of the file."""
        rendered = json.dumps(summarize_shape(REALISTIC_RESPONSE))
        for field in ("displayName", "skillLevel", "ppm", "standing", "division"):
            assert field in rendered


class TestTypesAreUseful:
    def test_scalars_map_to_type_names(self):
        assert summarize_shape("Shawna Larsen") == "str"
        assert summarize_shape(42) == "int"
        assert summarize_shape(2.33) == "float"
        assert summarize_shape(None) == "null"

    def test_bool_is_not_reported_as_int(self):
        """bool is a subclass of int in Python; checked first, or every flag
        in the schema would read as a number."""
        assert summarize_shape(True) == "bool"
        assert summarize_shape(False) == "bool"

    def test_nesting_is_preserved(self):
        shape = summarize_shape(REALISTIC_RESPONSE)
        assert shape["data"]["team"]["id"] == "int"
        assert shape["data"]["team"]["division"]["nightOfPlay"] == "THURSDAY"

    def test_lists_show_one_element_and_a_count(self):
        shape = summarize_shape(REALISTIC_RESPONSE)["data"]["team"]["roster"]
        assert len(shape) == 2
        assert shape[0]["displayName"] == "str"
        assert shape[1] == "...2 item(s)"

    def test_empty_list_stays_empty(self):
        assert summarize_shape([]) == []

    def test_null_nested_object_is_marked(self):
        shape = summarize_shape(REALISTIC_RESPONSE)["data"]["team"]["roster"][0]
        assert shape["member"] == "null"


class TestEnumHeuristic:
    """Enum values are worth keeping -- they are what the mapping code
    switches on -- and cannot collide with personal data."""

    def test_all_caps_enums_are_kept(self):
        for enum in ("COMPLETED", "HOME", "AWAY", "EIGHT_BALL", "THURSDAY", "SCHEDULED"):
            assert summarize_shape(enum) == enum

    def test_a_name_is_never_mistaken_for_an_enum(self):
        for name in ("Shawna Larsen", "SHAWNA LARSEN", "Chalk It Up",
                     "rchen@example.com", "555-867-5309"):
            assert summarize_shape(name) == "str", f"{name!r} was kept verbatim"

    def test_a_long_all_caps_string_is_not_treated_as_an_enum(self):
        """Length-capped, so a shouted sentence cannot slip through."""
        assert summarize_shape("THIS IS A VERY LONG SHOUTED STRING OF TEXT") == "str"

    def test_an_all_caps_id_like_string_is_not_kept(self):
        assert summarize_shape("80200640") == "str"
