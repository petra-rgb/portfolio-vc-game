# PORTFOLIO: a venture capital board game

A tabletop game for 3–4 players (2 with the co-fund variant). Each player runs a VC fund: you bid for startups at auction,
coach them through operating dilemmas, keep your LPs happy, and exit at the right moment.
Returns follow a power law, so most bets fail and one or two make the game.

This repository has the rules and the Monte Carlo simulator I used to balance them.

## What's here

| Path | What |
|---|---|
| `rules/PORTFOLIO_Rulebook_v2_3.docx` | Current rulebook (v2.3) |
| `rules/player_mat_v3.pdf` | Printable player mat |
| `sim/portfolio_sim.py` | Monte Carlo balance simulator |
| `sim/design_v23.json` | Parameters for the v2.3 balance |
| `docs/balance_changes_v2_3.md` | What changed in v2.3 and why, with the simulation numbers |
| `docs/sim_results_v22.png` | Simulator output for v2.2 |

The card decks are not included.

## How a game works

- **Deal flow.** 60 startups in 6 sectors and 5 stages, from Growth to Contrarian bets. Later stages
  are cheaper and safer; earlier ones are expensive and pay out big or not at all.
- **Auctions.** Startups are bought at auction. Your reputation tier decides which deal-flow slots
  you can reach.
- **Coaching.** Spend capital to draw an advisory dilemma with three choices. A good call moves the
  startup's traction up.
- **Exits.** Traction is rolled in secret when you invest and revealed at exit. Profitable exits
  raise your reputation; losses and busts lower it.
- **Pressure.** Market events every round, LP demands every fourth round, and a secret thesis
  per player that pays a bonus at the end.

## Running the simulator

Standard library only (matplotlib is needed for `--plot`):

```bash
python sim/portfolio_sim.py --plot                      # 2000 games, 4 players, charts
python sim/portfolio_sim.py --design sim/design_v23.json --plot
python sim/portfolio_sim.py --no-cards                  # core rules only
python sim/portfolio_sim.py --games 5000 --seed 1 --players 3
```

The players are five heuristic agents (balanced, conservative, aggressive, specialist, scout). Use the results
to spot broken rules or dominant strategies, not to predict how real people play.

## Balancing

The simulator drove the v2.3 changes: starting capital went from 15 to 17 because passive play was
winning 13% of games, the mid-stage startups got cheaper, and an overpowered fund ability was
taxed. Details are in [`docs/balance_changes_v2_3.md`](docs/balance_changes_v2_3.md).

Startup and fund names in the simulator are labels taken from real companies. The game is not
affiliated with any of them.
