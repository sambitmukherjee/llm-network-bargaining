## EX1

```text
You are agent Orsa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Pell, Talin, Vash. The whole network: Orsa–Pell, Orsa–Talin, Orsa–Vash, Pell–Vash. Every agent is shown this same map.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 1 of 12, phase 1 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: none yet.
This round so far: nothing has happened yet.
Offers open to you now: none.
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## EX2

```text
You are agent Talin. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Orsa. Each agent knows only its own neighbours.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 5 of 12, phase 2 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 33 points over 4 rounds; deals in 3 of 4.
  Round 1: you offered Orsa 12 points (you keep 12); Orsa accepted. 12 points.
  Round 2: Orsa offered you 12 points (Orsa keeps 12); you accepted. 12 points.
  Round 3: Orsa offered you 9 points (Orsa keeps 15); you accepted. 9 points.
  Round 4: you offered Orsa 14 points (you keep 10); it lapsed when Orsa closed another deal. No offers received. 0 points.
This round so far:
  Phase 1: you offered Orsa 14 points (you keep 10); still open, not accepted yet.
  Neighbours already done this round: none.
Offers open to you now: none.
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## EX3

```text
You are agent Pell. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Orsa, Vash. The whole network: Orsa–Pell, Orsa–Talin, Orsa–Vash, Pell–Vash. Every agent is shown this same map.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 9 of 12, phase 3 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 86 points over 8 rounds; deals in 7 of 8.
  Round 1: Vash offered you 12 points (Vash keeps 12); you accepted. 12 points. Orsa dealt with Talin.
  Round 2: you offered Orsa 11 points (you keep 13); Orsa accepted. 13 points. Vash had no deal.
  Round 3: you offered Orsa 10 points (you keep 14); it lapsed when Orsa dealt with Talin. Vash offered you 12 points (Vash keeps 12); you accepted. 12 points.
  Round 4: you offered Vash 10 points (you keep 14); Vash accepted. 14 points. Orsa dealt with Talin.
  Round 5: Orsa offered you 11 points (Orsa keeps 13); you accepted. 11 points. Vash had no deal.
  Round 6: you offered Vash 12 points (you keep 12); Vash accepted. 12 points. Orsa dealt with Talin.
  Round 7: Vash offered you 12 points (Vash keeps 12); you accepted. 12 points. Orsa dealt with Talin.
  Round 8: you offered Vash 12 points (you keep 12); it lapsed when Vash dealt with Orsa. No offers received. 0 points.
This round so far:
  Phase 1: you offered Orsa 11 points (you keep 13); it lapsed when Orsa dealt with Talin.
  Phase 2: you passed. Vash offered you 10 points (Vash keeps 14).
  Neighbours already done this round: Orsa (with Talin).
Offers open to you now: Vash offers you 10 (Vash keeps 14).
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## EX4

```text
You are agent Orsa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Pell, Talin, Vash. Each agent knows only its own neighbours.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 12 of 12, phase 1 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 171 points over 11 rounds; deals in 11 of 11.
  Round 1: you offered Talin 12 points (you keep 12); Talin accepted. 12 points. Pell dealt with Vash.
  Round 2: Pell offered you 12 points (Pell keeps 12); you accepted. 12 points. Talin and Vash had no deal.
  Round 3: you offered Pell 10 points (you keep 14); it lapsed when Pell dealt with Vash. Talin offered you 14 points (Talin keeps 10); you accepted. 14 points.
  Round 4: you offered Talin 9 points (you keep 15); Talin accepted. 15 points. Pell dealt with Vash.
  Round 5: Pell offered you 16 points (Pell keeps 8); you accepted. 16 points. Talin and Vash had no deal.
  Round 6: Talin offered you 18 points (Talin keeps 6); you accepted. 18 points. Pell dealt with Vash.
  Round 7: you offered Vash 6 points (you keep 18); Vash accepted. 18 points. Pell and Talin had no deal.
  Round 8: Talin offered you 18 points (Talin keeps 6); you accepted. 18 points. Pell dealt with Vash.
  Round 9: you offered Talin 8 points (you keep 16); Talin accepted. 16 points. Pell dealt with Vash.
  Round 10: Pell offered you 15 points (Pell keeps 9); you accepted. 15 points. Talin and Vash had no deal.
  Round 11: you offered Talin 7 points (you keep 17); Talin accepted. 17 points. Pell dealt with Vash.
This round so far:
  Phase 1, before your turn: Talin offered you 18 points (Talin keeps 6). Vash offered you 15 points (Vash keeps 9).
  Neighbours already done this round: none.
Offers open to you now: Talin offers you 18 (Talin keeps 6); Vash offers you 15 (Vash keeps 9).
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## G5

```text
You are agent Bexa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Calo, Deni, Fira. Each agent knows only its own neighbours.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 2 of 12, phase 1 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 15 points over 1 round; deals in 1 of 1.
  Round 1: you offered Calo 8 points (you keep 16); it lapsed when you accepted Deni's offer. Calo offered you 14 points (Calo keeps 10); it lapsed when you dealt with Deni. Deni offered you 15 points (Deni keeps 9); you accepted. Fira offered you 13 points (Fira keeps 11); it lapsed when you dealt with Deni. 15 points. Calo and Fira had no deal.
This round so far: nothing has happened yet.
Offers open to you now: none.
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## G6_OWN

```text
You are agent Lusa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Jaro, Mardo. Each agent knows only its own neighbours.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 4 of 12, phase 3 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 1 point over 3 rounds; deals in 1 of 3.
  Round 1: No offers made or received. 0 points. Jaro closed a deal. Mardo closed a deal.
  Round 2: you offered Jaro 11 points (you keep 13); it lapsed when you accepted Jaro's offer. Jaro offered you 1 point (Jaro keeps 23); you accepted. 1 point. Mardo had no deal.
  Round 3: you offered Mardo 8 points (you keep 16); Mardo did not accept. Mardo offered you 10 points (Mardo keeps 14); Mardo withdrew it. Jaro offered you 9 points (Jaro keeps 15); you did not accept. 0 points. Jaro and Mardo had no deal.
This round so far:
  Phase 1: you offered Jaro 10 points (you keep 14); you replaced it. Mardo offered you 12 points (Mardo keeps 12); it lapsed when Mardo closed another deal.
  Phase 2: you offered Mardo 11 points (you keep 13); it lapsed when Mardo closed another deal. Jaro offered you 9 points (Jaro keeps 15).
  Neighbours already done this round: Mardo.
Offers open to you now: Jaro offers you 9 (Jaro keeps 15).
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## G6_FULL

```text
You are agent Lusa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Jaro, Mardo. The whole network: Isko–Jaro, Jaro–Lusa, Lusa–Mardo, Mardo–Nesh. Every agent is shown this same map.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 4 of 12, phase 3 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 1 point over 3 rounds; deals in 1 of 3.
  Round 1: No offers made or received. 0 points. Jaro dealt with Isko. Mardo dealt with Nesh.
  Round 2: you offered Jaro 11 points (you keep 13); it lapsed when you accepted Jaro's offer. Jaro offered you 1 point (Jaro keeps 23); you accepted. 1 point. Mardo had no deal.
  Round 3: you offered Mardo 8 points (you keep 16); Mardo did not accept. Mardo offered you 10 points (Mardo keeps 14); Mardo withdrew it. Jaro offered you 9 points (Jaro keeps 15); you did not accept. 0 points. Jaro and Mardo had no deal.
This round so far:
  Phase 1: you offered Jaro 10 points (you keep 14); you replaced it. Mardo offered you 12 points (Mardo keeps 12); it lapsed when Mardo dealt with Nesh.
  Phase 2: you offered Mardo 11 points (you keep 13); it lapsed when Mardo dealt with Nesh. Jaro offered you 9 points (Jaro keeps 15).
  Neighbours already done this round: Mardo (with Nesh).
Offers open to you now: Jaro offers you 9 (Jaro keeps 15).
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## G7

```text
You are agent Rulo. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Sefi. The whole network: Rulo–Sefi. Every agent is shown this same map.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 1 of 12, phase 2 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: none yet.
This round so far:
  Phase 1: your action was invalid (that agent is not your neighbour) and counted as a pass. Sefi offered you 12 points (Sefi keeps 12).
  Neighbours already done this round: none.
Offers open to you now: Sefi offers you 12 (Sefi keeps 12).
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```

## G8

```text
You are agent Lusa. You earn points by making deals with your neighbours.
Each round you can close at most ONE deal. Every deal splits 24 points between its two agents.
Your neighbours: Jaro, Mardo. Each agent knows only its own neighbours.
Each round has 3 phases. In phases 1 and 2 you may offer a split to one neighbour, accept an offer made to you, or pass. In phase 3 you may only accept an offer or pass.
With no deal by the end of a round you earn 0.
Goal: earn as many points as possible over 12 rounds.
Round 6 of 12, phase 2 of 3. Offers stay open until the end of the round unless the maker or the recipient closes another deal.
A new offer from you replaces your previous one. In phase 3, anything not accepted lapses and earns 0.
Agents act in a random order that changes every phase. You see offers made to you before your turn.
Your history: 13 points over 5 rounds; deals in 2 of 5.
  Round 1: No offers made or received. 0 points. Jaro closed a deal. Mardo closed a deal.
  Round 2: you offered Jaro 11 points (you keep 13); it lapsed when you accepted Jaro's offer. Jaro offered you 1 point (Jaro keeps 23); you accepted. 1 point. Mardo had no deal.
  Round 3: you offered Mardo 8 points (you keep 16); Mardo did not accept. Mardo offered you 10 points (Mardo keeps 14); Mardo withdrew it. Jaro offered you 9 points (Jaro keeps 15); you did not accept. 0 points. Jaro and Mardo had no deal.
  Round 4: you offered Jaro 10 points (you keep 14); you replaced it. You offered Mardo 11 points (you keep 13); it lapsed when Mardo closed another deal. Mardo offered you 12 points (Mardo keeps 12); it lapsed when Mardo closed another deal. Jaro offered you 9 points (Jaro keeps 15); you did not accept. 0 points. Jaro had no deal.
  Round 5: you offered Jaro 12 points (you keep 12); Jaro accepted. Jaro offered you 10 points (Jaro keeps 14); Jaro accepted your offer instead. 12 points. Mardo had no deal.
This round so far:
  Phase 1: you passed. Mardo offered you 11 points (Mardo keeps 13); Mardo withdrew it.
  Neighbours already done this round: none.
Offers open to you now: none.
Reply with JSON only:
{"action": "offer|accept|pass", "to": "<neighbour>", "my_points": <0-24, ignored for accept>, "note": "<private, max 30 words>"}
For an offer, my_points is the whole number of points you keep; the neighbour gets 24 minus it.
You can offer only to neighbours not yet done this round. For an accept, "to" names the neighbour whose offer you accept. For a pass, "to" and "my_points" are ignored. Any invalid action counts as a pass.
```
