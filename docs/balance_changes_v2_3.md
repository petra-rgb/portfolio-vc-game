# PORTFOLIO — v2.3 Balance Changes (from simulation)

Result of the design-optimisation pass with the five heuristic agents. Baseline (v2.2 + fixed cards) penalty 37; this design 17, of which 12 is the Contrarian thesis, which the current agents cannot test. Effective penalty ≈ 5. Mean score rises from 25 to 29 (mostly the +2 starting capital).

## Changes

| Item | v2.2 | v2.3 | Why |
|---|---|---|---|
| Starting capital | 15 | **17** | Passive play won 13% of games; two more capital lets everyone act from round 1. Passive drops to 8%. |
| Series A cost | 5 / 6 | **4 / 5** | Mid ladder was overpriced relative to its payout. |
| Seed cost | 6 / 7 | **5 / 6** | Same. |
| Pre-seed cost | 7 / 8 | **6 / 7** | Same. |
| Contrarian Bet cost | 9 / 10 | **11 / 12** | Contrarian margin was far too fat (EV − cost ≈ +4). |
| Series A payouts | ×1.0 | **×1.15** | Series A was the worst stage per capital; now sits between Growth and Seed. |
| Contrarian payouts | ×1.0 | **×0.8** | Top payout 30 → 24. Combined with the cost change, Contrarian EV − cost goes from +4 to −0.7 before Coaching and specialization — it is now a bet, not a bargain. |
| Loss-making Exit (Stealth/Emerging) | −1 rep | **−2 rep** | Reputation was too sticky; losses now hurt. |
| Loss-making Exit (Notable+) | −2 rep | **−3 rep** | Same. |
| Lightspeed | invest any slot once | **invest any slot once, paying 4 extra capital** | Lightspeed won 36–46% of games. Now 26%. |
| Operator thesis | Coach 4+ | **Coach 5+** | 75% completion → 19%. Agents Coach about once a game; humans will Coach more, so 5 is likely right. |
| Platform Play thesis | 5 sectors | **4 sectors** | 1% → 14%. Still hard; agents specialise, humans may find it easier. |

Unchanged on purpose (the optimiser suggested these but they were noise or degenerate): Coach cost stays 1 (free Coaching kills Figma/Cherry; cost 2 kills Operator entirely), Growth/Seed/Pre-seed payouts unchanged, sector bonus stays 4 per companion, profit reputation stays +2.

## New Exit Payout Table

| Adjusted traction | Growth | Series A | Seed | Pre-seed | Contrarian Bet |
|---|---|---|---|---|---|
| 1 | 1 | 1 | BUST | BUST | BUST |
| 2 | 2 | 2 | 3 | BUST | BUST |
| 3 | 3 | 5 | 5 | BUST | BUST |
| 4 | 4 | 6 | 6 | 8 | BUST |
| 5 | 5 | 7 | 8 | 10 | 12 |
| 6 | 6 | 8 | 9 | 12 | 14 |
| 7 | 7 | 9 | 11 | 14 | 17 |
| 8 | 8 | 12 | 12 | 16 | 19 |
| 9 | 9 | 13 | 14 | 18 | 22 |
| 10 | 10 | 14 | 15 | 20 | 24 |

Expected payout, uncoached: Growth 5.5 · Series A 7.7 · Seed 8.3 · Pre-seed 9.8 · Contrarian 10.8.
Average cost: 4.5 · 4.5 · 5.5 · 6.5 · 11.5.
Margin (EV − cost): +1.0 · +3.2 · +2.8 · +3.3 · −0.7. Contrarian now only pays with Coaching, specialization, or an IPO Window — which is the point of a contrarian bet.

## Startup card cost changes

Every Series A, Seed and Pre-seed card: printed cost −1. Every Contrarian Bet: printed cost +2. Growth unchanged.

## Results with this design (3000 games)

- Strategies: scout 34%, aggressive 33%, specialist 26%, balanced 24%, passive 8%.
- Firms: all between 20% (Index) and 30% (a16z).
- Theses: Early Bird 64%, Steady Hand 52%, Untouchable 43%, Climber 33%, Home Run 29%, Specialist 23%, Operator 19%, Platform Play 14%, Contrarian 1%.
- 35% of players reach Blue Chip; score SD 14.5.

## Still open

- **Contrarian thesis (1%)** and **Platform Play (14%)** are limited by agent behaviour, not rules. Re-test after the agent-optimisation step.
- **Early Bird 64%** is slightly easy. Option: "profitable Exit by end of Round 2".
- **Scout / aggressive at 33–34%** vs specialist / balanced at 24–26%: a 9-point spread, just outside target. The cheaper mid ladder favours volume buyers. Acceptable for now; revisit after agents.
