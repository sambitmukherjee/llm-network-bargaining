"""Display-name assignment, strict output schema, and forgiving response parsing."""

from dataclasses import FrozenInstanceError
import json
from typing import Any

import pytest

from llm_network_bargaining._prompt_examples import EX2
from llm_network_bargaining.actions import Action, validate
from llm_network_bargaining.names import NAME_POOL, assign_names
from llm_network_bargaining.networks import get_network, list_networks
from llm_network_bargaining.schema import action_to_reply, parse_reply, response_format
from llm_network_bargaining.seeds import derive_seed, make_rng

NAMES = {"A": "Orsa", "B": "Pell"}


def test_name_pool_and_seeded_assignment() -> None:
    """Assignments cover every node and follow the exact specified RNG sequence."""
    assert len(NAME_POOL) == len({name.casefold() for name in NAME_POOL}) == 24
    node_ids = {node.casefold() for net in list_networks() for node in net.nodes}
    assert not node_ids.intersection(name.casefold() for name in NAME_POOL)
    net = get_network("stem")
    rng = make_rng(derive_seed(42, "names"))
    indices = rng.choice(len(NAME_POOL), size=len(net.nodes), replace=False)
    expected = {node: NAME_POOL[int(indices[i])] for i, node in enumerate(net.nodes)}
    assert assign_names(net, 42) == expected == assign_names(net, 42)
    assert len({tuple(assign_names(net, seed).items()) for seed in range(10)}) > 1
    for network in list_networks():
        names = assign_names(network, 0)
        assert tuple(names) == network.nodes
        assert len(set(names.values())) == len(network.nodes)
        assert set(names.values()).issubset(NAME_POOL)
    with pytest.raises(ValueError, match="more nodes"):
        assign_names(net, 0, pool=("Orsa",))
    with pytest.raises(ValueError, match="Duplicate"):
        assign_names(get_network("pair"), 0, pool=("Orsa", "ORSA"))


def test_response_format_is_exact_and_independent() -> None:
    """The structured-output schema checks format without encoding game rules."""
    expected = {
        "type": "json_schema", "json_schema": {
            "name": "bargaining_action", "strict": True, "schema": {
                "type": "object", "properties": {
                    "action": {"type": "string", "enum": ["offer", "accept", "pass"]},
                    "to": {"type": ["string", "null"]},
                    "my_points": {"type": ["integer", "null"]},
                    "note": {"type": "string"},
                }, "required": ["action", "to", "my_points", "note"],
                "additionalProperties": False,
            },
        },
    }
    assert response_format() == expected
    changed = response_format()
    changed["json_schema"]["schema"]["properties"]["my_points"]["minimum"] = 0
    assert response_format() == expected


PARSED = [
    ('{"action":"offer","to":"Pell","my_points":14,"note":"x"}', Action("offer", "B", 14, "x")),
    ('  {"action":"ACCEPT","to":" pell ","my_points":null,"note":""}  ', Action("accept", "B", None, "")),
    ('{"action":"pass","to":null,"my_points":null,"note":"wait"}', Action("pass", None, None, "wait")),
    ('{"action":"offer","to":"B","my_points":14,"note":""}', Action("offer", "?B", 14, "")),
    ('{"action":"offer","to":"Zed","my_points":14,"note":""}', Action("offer", "?Zed", 14, "")),
    ('{"action":"offer","to":7,"my_points":14,"note":""}', Action("offer", "?7", 14, "")),
    ('{"action":"offer","to":"Pell","my_points":12.5,"note":""}', Action("offer", "B", 12.5, "")),
    ('{"action":5,"to":"Pell","my_points":1,"note":""}', Action(5, "B", 1, "")),
    ('```json\n{"action":"pass","to":null,"my_points":null,"note":""}\n```', Action("pass", None, None, "")),
    ('```\n{"action":"pass","to":null,"my_points":null,"note":""}\n```', Action("pass", None, None, "")),
]


@pytest.mark.parametrize("content,expected", PARSED)
def test_parser_cases(content: str, expected: Action) -> None:
    """Names are normalised, while invalid actions and point types remain visible."""
    parsed = parse_reply(content, NAMES)
    assert parsed.action == expected and parsed.error is None
    json.dumps(parsed.details)


@pytest.mark.parametrize("content,error", [
    ("Sure, I offer 14", "invalid_json"), ("[1,2]", "not_an_object"),
    ("null", "not_an_object"), ('{"action":"offer"}', "missing_field"),
    ("", "empty"), ("   ", "empty"), (None, "empty"),
])
def test_parse_errors(content: str | None, error: str) -> None:
    """Malformed replies return an explicit error and no game action."""
    result = parse_reply(content, NAMES)
    assert result.error == error and result.action is None
    if error == "missing_field":
        assert result.details["missing"] == ["to", "my_points", "note"]
    with pytest.raises(FrozenInstanceError):
        result.error = None  # type: ignore[misc]


def test_refusal_precedence_and_diagnostics() -> None:
    """Refusal wins over empty content; extra keys and normalisation are recorded."""
    result = parse_reply(None, NAMES, refusal="I can't help with that.")
    assert result.error == "refusal" and result.details["refusal"] == "I can't help with that."
    data = dict(action=" ACCEPT ", to=" pell ", my_points=None, note="", extra=1)
    result = parse_reply(json.dumps(data), NAMES)
    assert result.details["extra_keys"] == ["extra"]
    assert result.details["to_raw"] == " pell "
    assert result.action == Action("accept", "B", None, "")


def test_notes_are_measured_without_truncation() -> None:
    """A long note is kept intact; non-string notes become None."""
    note = " ".join(["word"] * 35)
    data = dict(action="pass", to=None, my_points=None, note=note)
    parsed = parse_reply(json.dumps(data), NAMES)
    assert parsed.action is not None and parsed.action.note == note
    assert parsed.details["note_words"] == 35 and parsed.details["note_over_limit"] is True
    data["note"] = 5
    parsed = parse_reply(json.dumps(data), NAMES)
    assert parsed.action is not None and parsed.action.note is None
    assert parsed.details["note_words"] == 0 and parsed.details["note_over_limit"] is False


@pytest.mark.parametrize("action", [Action("offer", "B", 14, "x"),
                                   Action("accept", "A", None, ""), Action("pass", note="wait")])
def test_json_inverse(action: Action) -> None:
    """The JSON inverse is exact for requests with string notes."""
    reply = action_to_reply(action, NAMES)
    assert list(json.loads(reply)) == ["action", "to", "my_points", "note"]
    assert parse_reply(reply, NAMES).action == action
    assert ": " not in reply


def test_none_note_and_no_action_encoding() -> None:
    """Absent notes become empty strings, and no action becomes an empty reply."""
    assert action_to_reply(None, NAMES) == ""
    assert json.loads(action_to_reply(Action("pass"), NAMES))["note"] == ""
    assert parse_reply(action_to_reply(None, NAMES), NAMES).error == "empty"


def test_parser_has_no_coverage_check_and_engine_checks_neighbours() -> None:
    """The parser can use partial mappings and resolve a named non-neighbour."""
    assert parse_reply('{"action":"pass","to":null,"my_points":null,"note":""}', {}).error is None
    obs = EX2.observation()
    reply = '{"action":"offer","to":"Pell","my_points":12,"note":""}'
    parsed = parse_reply(reply, EX2.names)
    assert parsed.action == Action("offer", "C", 12, "")
    assert validate(parsed.action, obs) == "not_a_neighbour"
    with pytest.raises(ValueError, match="Duplicate"):
        parse_reply(reply, {"A": "Orsa", "B": "ORSA"})


@pytest.mark.parametrize("points", [True, 12.0, "12", -1, 25])
def test_parser_leaves_illegal_points_for_the_engine(points: Any) -> None:
    """Schema-independent parsing preserves the value that violated game rules."""
    obs = EX2.observation()
    data = dict(action="offer", to="Orsa", my_points=points, note="")
    parsed = parse_reply(json.dumps(data), EX2.names)
    assert parsed.action is not None and type(parsed.action.my_points) is type(points)
    assert validate(parsed.action, obs) == "bad_points"
