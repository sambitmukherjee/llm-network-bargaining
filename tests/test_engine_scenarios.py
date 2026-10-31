"""The brief's hand-worked protocol scenarios, including event ordering."""

import pytest

from llm_network_bargaining.actions import Action
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.observation import KnowledgeSetting, MyDeal, NeighbourDeal
from phase2_helpers import check_result, scripted_episode


def test_s1_simple_deal() -> None:
    """S1: sequential turns can close a deal in the first phase."""
    net = get_network("pair")
    result, agents = scripted_episode(net, {"A": {(1, 1): Action("offer", "B", 14)},
                                             "B": {(1, 1): Action("accept", "A")}})
    assert result.points == {"A": (14,), "B": (10,)}
    assert result.offers[0].status == "accepted"
    assert result.deals[0].phase == 1
    assert [len(agents[node].observations) for node in net.nodes] == [1, 1]
    assert [event["type"] for event in result.events] == [
        "episode_start", "phase_start", "turn", "offer", "turn", "deal", "offer_status",
        "phase_start", "phase_start", "round_end", "episode_end"]
    check_result(result, net)


@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_s2_replacement_and_voiding(knowledge: KnowledgeSetting) -> None:
    """S2: replacement and a deal give four different final offer statuses."""
    net = get_network("line3")
    result, agents = scripted_episode(net, {
        "A": {(1, 1): Action("offer", "B", 10), (1, 2): Action("offer", "B", 9)},
        "B": {(1, 1): Action("offer", "C", 16), (1, 2): Action("accept", "A")},
        "C": {(1, 1): Action("offer", "B", 12)},
    }, rounds=2, knowledge=knowledge)
    assert [(offer.maker, offer.recipient, offer.maker_points, offer.status) for offer in result.offers] == [
        ("A", "B", 10, "withdrawn"), ("B", "C", 16, "maker_dealt"),
        ("C", "B", 12, "recipient_dealt"), ("A", "B", 9, "accepted")]
    assert {node: result.points[node][0] for node in net.nodes} == {"A": 9, "B": 15, "C": 0}
    assert [len(agents[node].observations) for node in net.nodes] == [4, 4, 3]
    forced = [turn for turn in result.turns if turn.round == 1 and turn.agent == "C" and turn.phase > 1]
    assert len(forced) == 2 and all(turn.auto for turn in forced)
    c = agents["C"].at(2, 1)
    assert c.history[0].offers_made[0].status == "recipient_dealt"
    assert c.history[0].offers_received[0].recipient_points == 8
    assert c.history[0].offers_received[0].status == "maker_dealt"
    assert c.history[0].deal is None and c.history[0].points == 0
    assert c.history[0].neighbour_deals == (NeighbourDeal("B", "A" if knowledge == "full_map" else None),)
    a, b = agents["A"].at(2, 1), agents["B"].at(2, 1)
    assert [offer.status for offer in a.history[0].offers_made] == ["withdrawn", "accepted"]
    assert a.history[0].deal == MyDeal("B", 2, 9, 15, True)
    assert a.history[0].neighbour_deals == ()
    assert [offer.maker_points for offer in b.history[0].offers_received] == [10, 12, 9]
    assert b.history[0].deal is not None and b.history[0].deal.i_offered is False
    assert (a.total_points, b.total_points, c.total_points) == (9, 15, 0)
    statuses = [event for event in result.events if event["type"] == "offer_status"]
    assert [(event["offer_id"], event["status"]) for event in statuses] == [
        (0, "withdrawn"), (1, "maker_dealt"), (2, "recipient_dealt"), (3, "accepted")]
    check_result(result, net)


@pytest.mark.parametrize("accept_final", [False, True])
def test_s3_final_phase_and_lapse(accept_final: bool) -> None:
    """S3/S3b: final-phase offers are invalid, while standing offers remain valid."""
    net = get_network("pair")
    script = {"A": {(1, 2): Action("offer", "B", 13), (1, 3): Action("offer", "B", 12)},
              "B": {(1, 1): Action("offer", "A", 20)}}
    if accept_final:
        script["B"][1, 3] = Action("accept", "A")
    result, agents = scripted_episode(net, script)
    invalid = next(turn for turn in result.turns if turn.agent == "A" and turn.phase == 3)
    assert not invalid.valid and invalid.reason == "offer_in_final_phase" and invalid.applied == "pass"
    assert len(agents["A"].observations) == len(agents["B"].observations) == 3
    if accept_final:
        assert result.points == {"A": (13,), "B": (11,)}
        assert result.deals[0].phase == 3
        assert [offer.status for offer in result.offers] == ["maker_dealt", "accepted"]
    else:
        assert result.points == {"A": (0,), "B": (0,)}
        assert [offer.status for offer in result.offers] == ["lapsed", "lapsed"]
        end = [event for event in result.events if event["type"] in ("offer_status", "round_end")]
        assert [event["type"] for event in end] == ["offer_status", "offer_status", "round_end"]
        assert [event["offer_id"] for event in end[:-1]] == [0, 1]
    check_result(result, net)


def test_s4_done_neighbour() -> None:
    """S4: a rejected offer to a done neighbour does not end the maker's round."""
    net = get_network("line4")
    result, agents = scripted_episode(net, {
        "A": {(1, 1): Action("offer", "B", 12)}, "B": {(1, 1): Action("accept", "A")},
        "C": {(1, 1): Action("offer", "B", 12)},
    })
    invalid = next(turn for turn in result.turns if turn.agent == "C" and turn.phase == 1)
    assert invalid.reason == "neighbour_done" and invalid.applied == "pass"
    assert agents["C"].at(1, 2).legal.can_offer_to == ("D",)
    assert result.points == {"A": (12,), "B": (12,), "C": (0,), "D": (0,)}
    check_result(result, net)


def test_s5_crossing_offers() -> None:
    """S5: the accepting agent's own offer is voided as maker_dealt."""
    net = get_network("pair")
    result, _ = scripted_episode(net, {
        "A": {(1, 1): Action("offer", "B", 14), (1, 2): Action("accept", "B")},
        "B": {(1, 1): Action("offer", "A", 14)},
    })
    assert result.points == {"A": (10,), "B": (14,)}
    assert [offer.status for offer in result.offers] == ["maker_dealt", "accepted"]
    statuses = [event["offer_id"] for event in result.events if event["type"] == "offer_status"]
    assert statuses == [0, 1]
    check_result(result, net)


INVALID_REQUESTS = [
    (None, "no_action"), (Action("dance"), "unknown_action"),
    (Action("offer", "Z", 12), "not_a_neighbour"),
    (Action("offer", "A", 12), "not_a_neighbour"),
    (Action("offer", None, 12), "not_a_neighbour"),
    *((Action("offer", "B", points), "bad_points") for points in (25, -1, 12.5, 12.0, True, "12", None)),
    (Action("accept", "B"), "no_open_offer"), (Action("accept"), "no_open_offer"),
]


@pytest.mark.parametrize("action,reason", INVALID_REQUESTS)
def test_s6_invalid_requests(action: Action | None, reason: str) -> None:
    """S6: every specified malformed request becomes a recorded invalid pass."""
    result, _ = scripted_episode(get_network("pair"), {"A": {(1, 1): action}})
    turn = result.turns[0]
    assert turn.reason == reason and not turn.valid and turn.applied == "pass"
    assert result.offers == () and result.totals == {"A": 0, "B": 0}


def test_pass_and_accept_ignore_unused_arguments() -> None:
    """Junk pass arguments and an accept's points do not change valid play."""
    result, _ = scripted_episode(get_network("pair"), {
        "A": {(1, 1): Action("pass", to="ZZZ", my_points={1, 2}),
              (1, 2): Action("accept", "B", 99)},
        "B": {(1, 1): Action("offer", "A", 14)},
    })
    assert all(turn.valid for turn in result.turns)
    assert result.points == {"A": (10,), "B": (14,)}


@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_s7_current_neighbour_deals(knowledge: KnowledgeSetting) -> None:
    """S7: both ends of a neighbour-neighbour deal are visible without its split."""
    _, agents = scripted_episode(get_network("stem"), {
        "C": {(1, 1): Action("offer", "D", 12)}, "D": {(1, 1): Action("accept", "C")},
    }, knowledge=knowledge, order=("C", "D", "A", "B"))
    b = agents["B"].at(1, 1)
    assert b.current.neighbour_deals == (NeighbourDeal("C", "D"), NeighbourDeal("D", "C"))
    assert b.legal.can_offer_to == ("A",)
    assert agents["A"].at(1, 1).current.neighbour_deals == ()


@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_s8_hidden_partners(knowledge: KnowledgeSetting) -> None:
    """S8: local knowledge hides non-neighbour partners in current and past deals."""
    result, agents = scripted_episode(get_network("line5"), {
        "C": {(1, 1): Action("offer", "D", 12)}, "D": {(1, 1): Action("accept", "C")},
    }, rounds=2, knowledge=knowledge, order=("C", "D", "B", "A", "E"))
    b = agents["B"].at(1, 1)
    assert b.current.neighbour_deals == (NeighbourDeal("C", "D" if knowledge == "full_map" else None),)
    assert all(turn.auto for turn in result.turns if turn.agent == "E" and turn.round == 1)
    assert agents["E"].at(2, 1).history[0].neighbour_deals == (
        NeighbourDeal("D", "C" if knowledge == "full_map" else None),)
