"""Recreate the original Appendix B.1.7 scripted late-game example offline.

Adapted from the copied paper/build_appendix_b_materials.py capture_late
function. Uses the unchanged tracked engine and prompt renderer; no model calls.
"""
from context import ROOT, OUT
from llm_network_bargaining.actions import Action, Decision
from llm_network_bargaining.engine import Episode
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.prompts import render_prompt

NAMES = {"A": "Talin", "B": "Orsa", "C": "Pell", "D": "Vash"}


def capture_late():
    game = Episode(get_network("line3"), knowledge="own_links", n_rounds=24,
                   episode_seed=0, turn_order=lambda r, p: ("A", "B", "C"))
    while (turn := game.next_turn()) is not None:
        r, p, node = turn.round, turn.phase, turn.agent
        if (r, p, node) == (24, 2, "A"):
            assert turn.observation.total_points == 120
            assert sum(past.deal is not None for past in turn.observation.history) == 15
            text = render_prompt(turn.observation, {k: NAMES[k] for k in "ABC"})
            assert "Pell" not in text
            return text
        action = Action("pass")
        if r == 24:
            if p == 1 and node == "A":
                action = Action("offer", "B", 8)
            elif p == 1 and node == "B":
                action = Action("offer", "A", 16)
        elif r % 3 == 1:
            if p == 1 and node == "A":
                action = Action("offer", "B", 8)
            elif p == 1 and node == "B":
                action = Action("accept", "A")
        elif r % 3 == 2:
            if p == 1 and node == "A":
                action = Action("offer", "B", 8)
            elif p == 1 and node == "B":
                action = Action("offer", "C", 16)
            elif p == 1 and node == "C":
                action = Action("accept", "B")
        else:
            if p == 1 and node == "B":
                action = Action("offer", "A", 16)
            elif p == 2 and node == "A":
                action = Action("accept", "B")
        game.submit(Decision(action))
    raise RuntimeError("Late prompt was not reached")


if __name__ == "__main__":
    text = capture_late() + "\n"
    assert text == (ROOT / "data/protocol/late_own_links.txt").read_text()
    target = OUT / "protocol/late_own_links.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    print("Late-game prompt reproduced exactly: 23 rounds, 15 deals, 120 points; hidden third name absent")
