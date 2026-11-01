"""Render the fixed v1 experimental stimulus from permitted observation data."""

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path

from .names import _name_lookup
from .networks import Network
from .observation import KnowledgeSetting, Observation, OfferView, PastRound

PROMPT_VERSION = "v1"


def _pts(number: int) -> str:
    return f"{number} point" if number == 1 else f"{number} points"


def _names_list(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _sentences(parts: list[str]) -> str:
    return " ".join(part if i == 0 else part[0].upper() + part[1:]
                    for i, part in enumerate(parts))


def _referenced_nodes(obs: Observation) -> set[str]:
    nodes = {obs.agent, *obs.neighbours}
    if obs.knowledge == "full_map" and obs.network_edges is not None:
        for a, b in obs.network_edges:
            nodes.update((a, b))
    for past in (*obs.history, obs.current):
        for offer in (*past.offers_made, *past.offers_received):
            nodes.update((offer.maker, offer.recipient))
        for deal in past.neighbour_deals:
            nodes.add(deal.neighbour)
            if deal.partner is not None:
                nodes.add(deal.partner)
    for past in obs.history:
        if past.deal is not None:
            nodes.add(past.deal.partner)
    return nodes


def _lapsed_when(node: str, partners: Mapping[str, str | None],
                  names: Mapping[str, str], mentioned: set[str]) -> str:
    mentioned.add(node)
    partner = partners.get(node)
    if partner is None:
        return f"it lapsed when {names[node]} closed another deal"
    mentioned.add(partner)
    return f"it lapsed when {names[node]} dealt with {names[partner]}"


def _offer_sentence(offer: OfferView, names: Mapping[str, str], *, mine: bool,
                    partner: str | None, partners: Mapping[str, str | None],
                    mentioned: set[str]) -> str:
    maker, recipient = names[offer.maker], names[offer.recipient]
    if mine:
        beginning = f"you offered {recipient} {_pts(offer.recipient_points)} (you keep {offer.maker_points})"
        if offer.status == "recipient_dealt":
            outcome = _lapsed_when(offer.recipient, partners, names, mentioned)
        elif offer.status == "maker_dealt":
            assert partner is not None
            outcome = f"it lapsed when you accepted {names[partner]}'s offer"
        else:
            outcome = {
                "open": "still open, not accepted yet", "accepted": f"{recipient} accepted",
                "withdrawn": "you replaced it", "lapsed": f"{recipient} did not accept",
            }[offer.status]
    else:
        beginning = f"{maker} offered you {_pts(offer.recipient_points)} ({maker} keeps {offer.maker_points})"
        if offer.status == "open":
            return beginning + "."
        if offer.status == "maker_dealt":
            if offer.maker == partner:
                outcome = f"{maker} accepted your offer instead"
            else:
                outcome = _lapsed_when(offer.maker, partners, names, mentioned)
        elif offer.status == "recipient_dealt":
            assert partner is not None
            outcome = f"it lapsed when you dealt with {names[partner]}"
        else:
            outcome = {
                "accepted": "you accepted", "withdrawn": f"{maker} withdrew it",
                "lapsed": "you did not accept",
            }[offer.status]
    return beginning + "; " + outcome + "."


def _history_line(past: PastRound, neighbours: tuple[str, ...], names: Mapping[str, str]) -> str:
    partner = past.deal.partner if past.deal is not None else None
    partners = {deal.neighbour: deal.partner for deal in past.neighbour_deals}
    mentioned: set[str] = set()
    parts = []
    for offer in past.offers_made:
        parts.append(_offer_sentence(offer, names, mine=True, partner=partner,
                                    partners=partners, mentioned=mentioned))
    for offer in past.offers_received:
        parts.append(_offer_sentence(offer, names, mine=False, partner=partner,
                                    partners=partners, mentioned=mentioned))
    if not past.offers_made and not past.offers_received:
        parts.append("No offers made or received.")
    elif not past.offers_received and past.deal is None:
        parts.append("No offers received.")
    parts.append(_pts(past.points) + ".")
    for deal in sorted(past.neighbour_deals, key=lambda deal: names[deal.neighbour]):
        if deal.neighbour in mentioned:
            continue
        mentioned.add(deal.neighbour)
        if deal.partner is None:
            parts.append(f"{names[deal.neighbour]} closed a deal.")
        else:
            mentioned.add(deal.partner)
            parts.append(f"{names[deal.neighbour]} dealt with {names[deal.partner]}.")
    no_deal = sorted(names[node] for node in neighbours if node != partner and node not in mentioned)
    if no_deal:
        parts.append(_names_list(no_deal) + " had no deal.")
    return f"  Round {past.round}: {_sentences(parts)}"


def _history_block(obs: Observation, names: Mapping[str, str]) -> list[str]:
    if not obs.history:
        return ["Your history: none yet."]
    count = len(obs.history)
    rounds = f"{count} round" if count == 1 else f"{count} rounds"
    deals = sum(past.deal is not None for past in obs.history)
    header = f"Your history: {_pts(obs.total_points)} over {rounds}; deals in {deals} of {count}."
    return [header, *(_history_line(past, obs.neighbours, names) for past in obs.history)]


def _reason_text(reason: str | None, pie: int) -> str:
    return {
        "no_action": "no usable reply",
        "unknown_action": "the action was not offer, accept or pass",
        "offer_in_final_phase": "offers are not allowed in phase 3",
        "not_a_neighbour": "that agent is not your neighbour",
        "neighbour_done": "that neighbour had already closed a deal",
        "bad_points": f"my_points must be a whole number from 0 to {pie}",
        "no_open_offer": "that agent had no open offer to you",
    }[reason]


def _current_block(obs: Observation, names: Mapping[str, str]) -> list[str]:
    current = obs.current
    partners = {deal.neighbour: deal.partner for deal in current.neighbour_deals}
    phase_lines = []
    for phase in range(1, obs.phase + 1):
        parts = []
        for turn in current.my_turns:
            if turn.phase != phase or turn.auto:
                continue
            if not turn.valid:
                parts.append(f"your action was invalid ({_reason_text(turn.reason, obs.pie)}) and counted as a pass.")
            elif turn.applied == "pass":
                parts.append("you passed.")
            elif turn.applied == "offer":
                offer = next(offer for offer in current.offers_made if offer.phase == phase)
                parts.append(_offer_sentence(offer, names, mine=True, partner=None,
                                            partners=partners, mentioned=set()))
        for offer in current.offers_received:
            if offer.phase == phase:
                parts.append(_offer_sentence(offer, names, mine=False, partner=None,
                                            partners=partners, mentioned=set()))
        if parts:
            label = f"Phase {phase}, before your turn" if phase == obs.phase else f"Phase {phase}"
            phase_lines.append(f"  {label}: {_sentences(parts)}")
    done = []
    for deal in sorted(current.neighbour_deals, key=lambda deal: names[deal.neighbour]):
        entry = names[deal.neighbour]
        if deal.partner is not None:
            entry += f" (with {names[deal.partner]})"
        done.append(entry)
    if not phase_lines and not done:
        return ["This round so far: nothing has happened yet."]
    return ["This round so far:", *phase_lines,
            f"  Neighbours already done this round: {', '.join(done) if done else 'none' }."]


def rules_block(network: Network | Observation, node: str, names: Mapping[str, str], *,
                knowledge: KnowledgeSetting, n_rounds: int) -> list[str]:
    """Return the nine opening rules, using round 1/phase 1 for a network.

    The renderer passes an Observation instead, so the same text can show its
    current round and phase without consulting a network or any hidden data.
    """
    if knowledge not in ("full_map", "own_links"):
        raise ValueError("knowledge must be 'full_map' or 'own_links'.")
    if n_rounds < 1:
        raise ValueError("n_rounds must be positive.")
    if isinstance(network, Observation):
        if (node, knowledge, n_rounds) != (network.agent, network.knowledge, network.n_rounds):
            raise ValueError("Rule settings must match the observation.")
        neighbours = network.neighbours
        network_edges = network.network_edges if knowledge == "full_map" else None
        pie, round_number, phase = network.pie, network.round, network.phase
    else:
        if network.kind != "exchange":
            raise ValueError("Bargaining rules require an exchange network.")
        neighbours = network.neighbours(node)
        network_edges = network.edges if knowledge == "full_map" else None
        pie, round_number, phase = network.pie, 1, 1
    _name_lookup(names)
    visible = {node, *neighbours}
    if network_edges is not None:
        visible.update(endpoint for edge in network_edges for endpoint in edge)
    missing = visible - names.keys()
    if missing:
        raise ValueError(f"Missing display names for observed nodes: {', '.join(sorted(missing))}.")
    neighbour_text = ", ".join(sorted(names[node] for node in neighbours))
    if knowledge == "full_map":
        assert network_edges is not None
        edges = sorted(tuple(sorted((names[a], names[b]))) for a, b in network_edges)
        links = ", ".join(f"{a}–{b}" for a, b in edges)
        map_sentence = f"The whole network: {links}. Every agent is shown this same map."
    else:
        map_sentence = "Each agent knows only its own neighbours."
    return [
        f"You are agent {names[node]}. You earn points by making deals with your neighbours.",
        f"Each round you can close at most ONE deal. Every deal splits {pie} points between its two agents.",
        f"Your neighbours: {neighbour_text}. {map_sentence}",
        "Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.",
        "With no deal by the end of a round you earn 0.",
        f"Goal: earn as many points as possible over {n_rounds} rounds.",
        f"Round {round_number} of {n_rounds}, phase {phase} of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.",
        "A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.",
        "Agents act in a random order that changes every phase. You see offers made to you before your turn.",
    ]


def render_prompt(obs: Observation, names: Mapping[str, str], *, version: str = "v1") -> str:
    """Render v1 exactly, requiring names only for nodes this observation mentions."""
    if version != PROMPT_VERSION:
        raise ValueError(f"Unknown prompt version: {version!r}.")
    if obs.n_phases != 3:
        raise ValueError("Prompt v1 requires exactly three phases.")
    _name_lookup(names)
    missing = _referenced_nodes(obs) - names.keys()
    if missing:
        raise ValueError(f"Missing display names for observed nodes: {', '.join(sorted(missing))}.")
    lines = rules_block(obs, obs.agent, names, knowledge=obs.knowledge, n_rounds=obs.n_rounds)
    lines.extend([*_history_block(obs, names), *_current_block(obs, names)])
    offers = [f"{names[offer.maker]} offers you {offer.recipient_points} "
              f"({names[offer.maker]} keeps {offer.maker_points})" for offer in obs.open_offers_to_me]
    lines.extend([
        f"Offers open to you now: {'; '.join(offers) if offers else 'none'}.",
        "Reply with JSON only:",
        '{"action": "offer|accept|pass", "to": "<neighbour>", '
        f'"my_points": <0-{obs.pie}, ignored for accept>, "note": "<private, max 30 words>"' + '}',
        f"For an offer, my_points is the whole number of points you keep; the neighbour gets {obs.pie} minus it.",
        'You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.',
    ])
    return "\n".join(lines)


def build_messages(obs: Observation, names: Mapping[str, str], *,
                   version: str = "v1") -> list[dict[str, str]]:
    """Build the one user message constituting the experimental stimulus."""
    return [{"role": "user", "content": render_prompt(obs, names, version=version)}]


def main(argv: Sequence[str] | None = None) -> None:
    """Print scripted examples, or capture one prompt from a bot episode."""
    parser = argparse.ArgumentParser(description="Review bargaining prompts without model calls.")
    commands = parser.add_subparsers(dest="command", required=True)
    examples = commands.add_parser("examples")
    examples.add_argument("--out", type=Path)
    sample = commands.add_parser("sample")
    sample.add_argument("--network", required=True)
    sample.add_argument("--bot", choices=("pass", "equal_split", "aspiration", "random"), default="aspiration")
    sample.add_argument("--knowledge", choices=("full_map", "own_links"), default="full_map")
    sample.add_argument("--seed", type=int, default=1)
    sample.add_argument("--agent", required=True)
    sample.add_argument("--round", type=int, required=True)
    sample.add_argument("--phase", type=int, required=True)
    sample.add_argument("--rounds", type=int, default=12)
    args = parser.parse_args(argv)
    if args.command == "examples":
        from ._prompt_examples import SCENARIOS

        sections = [f"## {name}\n\n```text\n{render_prompt(scenario.observation(), scenario.names)}\n```"
                    for name, scenario in SCENARIOS.items()]
        text = "\n\n".join(sections) + "\n"
        if args.out is None:
            print(text, end="")
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        return
    _sample_prompt(args, parser)


def _sample_prompt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from .bots import make_bot
    from .engine import Episode
    from .names import assign_names
    from .networks import get_network
    from .seeds import derive_seed

    try:
        network = get_network(args.network)
    except KeyError as error:
        parser.error(str(error))
    if network.kind != "exchange":
        parser.error("The broker protocol arrives in Phase 8.")
    if args.agent not in network.nodes:
        parser.error("agent must be a node in the selected network")
    if args.rounds < 1 or not 1 <= args.round <= args.rounds or not 1 <= args.phase <= 3:
        parser.error("choose a round within the episode and a phase from 1 to 3")
    seed = derive_seed(args.seed, "sample")
    names = assign_names(network, seed)
    bots = {node: make_bot(args.bot, node=node, episode_seed=seed) for node in network.nodes}
    episode = Episode(network, knowledge=args.knowledge, n_rounds=args.rounds, episode_seed=seed)
    while (pending := episode.next_turn()) is not None:
        if (pending.agent, pending.round, pending.phase) == (args.agent, args.round, args.phase):
            print(render_prompt(pending.observation, names))
            return
        episode.submit(bots[pending.agent].act(pending.observation))
    parser.exit(1, f"Agent {args.agent} was not asked in round {args.round}, phase {args.phase} "
                   "(already done, or a forced pass).\n")


if __name__ == "__main__":
    main()
