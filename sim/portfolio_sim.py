"""
PORTFOLIO - Monte Carlo balance simulator (rulebook v2.2 + fixed card decks)

Run FROM A TERMINAL (not the >>> prompt):
    python portfolio_sim.py --plot                 # 2000 games, 4 players, charts
    python portfolio_sim.py --advisory-skill 1.0   # experienced table (always finds the sound answer)
    python portfolio_sim.py --no-cards             # core rules only, no event/LP/firm/thesis/ability cards
    python portfolio_sim.py --rules v21            # old rules for comparison
    python portfolio_sim.py --games 5000 --seed 1 --players 3
    python portfolio_sim.py --design design_v23.json --plot   # run the v2.3 balance numbers

No dependencies beyond the standard library (matplotlib only for --plot).

Modelled: 60 startups with all 15 abilities, five stage stacks with reshuffle, tiers,
reputation +2/-1/-2/bust, auctions with opener's final raise, private traction, Scout with
first refusal, persisting Scouted cards, Coaching via the fixed Advisory deck, sector bonus,
power-law scoring, 24 Market Events, 18 LP Demands, 10 VC Firms, 10 Secret Theses.
Not modelled: Syndication (so Side Letter, Secondary Sale Fee, Dealmaker, SpaceX resolve
as "no trade"). Agents are heuristics: read the results as "is anything broken".
"""
import argparse
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Static data
# ----------------------------------------------------------------------------
STAGES = ["Growth", "Series A", "Seed", "Pre-seed", "Contrarian"]
SECTORS = ["Climate", "Fintech", "Deep Tech", "Consumer", "Biotech", "Space"]
TIERS = ["Stealth", "Emerging", "Notable", "Prominent", "Blue Chip"]
AVG_COST = {"Growth": 4.5, "Series A": 5.5, "Seed": 6.5, "Pre-seed": 7.5, "Contrarian": 9.5}
PAYOUT = {
    "Growth":     [None, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "Series A":   [None, 1, 2, 4, 5, 6, 7, 8, 10, 11, 12],
    "Seed":       [None, 0, 3, 5, 6, 8, 9, 11, 12, 14, 15],
    "Pre-seed":   [None, 0, 0, 0, 8, 10, 12, 14, 16, 18, 20],
    "Contrarian": [None, 0, 0, 0, 0, 15, 18, 21, 24, 27, 30],
}
BASE_PAYOUT = {k: list(v) for k, v in PAYOUT.items()}
EV = {s: sum(PAYOUT[s][1:]) / 10 for s in STAGES}
SD = {s: statistics.pstdev(PAYOUT[s][1:]) for s in STAGES}
ROUNDS, ACTIONS, START_CAPITAL, PORTFOLIO_SIZE = 8, 2, 15, 6


@dataclass
class Design:
    """Every tunable number in the game. optimize.py searches over these."""
    payout_scale: dict = field(default_factory=lambda: {s: 1.0 for s in STAGES})   # multiplier on payout table
    cost_shift: dict = field(default_factory=lambda: {s: 0 for s in STAGES})       # added to printed cost
    rep_profit: int = 2
    rep_loss_low: int = 1
    rep_loss_high: int = 2
    rep_bust_extra: int = 1
    coach_cost: int = 1
    start_capital: int = 15
    spec_per: int = 4              # sector bonus per companion beyond the first
    operator_coaches: int = 4      # Operator thesis threshold
    contrarian_exits: int = 2      # Contrarian thesis threshold
    platform_sectors: int = 5      # Platform Play threshold
    lightspeed_surcharge: int = 0  # extra capital Lightspeed pays to reach above tier

    def as_dict(self):
        d = dict(self.__dict__)
        d["payout_scale"] = dict(self.payout_scale)
        d["cost_shift"] = dict(self.cost_shift)
        return d


DESIGN = Design()

DESIGN_KEYS = ["rep_profit", "rep_loss_low", "rep_loss_high", "rep_bust_extra", "coach_cost", "start_capital",
               "spec_per", "operator_coaches", "contrarian_exits", "platform_sectors", "lightspeed_surcharge"]


def design_from_params(params):
    """Build a Design from a flat dict like the ones saved by optimize.py (design_v23.json)."""
    d = Design()
    for s in STAGES:
        d.payout_scale[s] = params.get(f"payout_{s}", 1.0)
        d.cost_shift[s] = int(params.get(f"cost_{s}", 0))
    for k in DESIGN_KEYS:
        if k in params:
            setattr(d, k, int(params[k]))
    return d


def params_from_design(d):
    p = {}
    for s in STAGES:
        p[f"payout_{s}"] = d.payout_scale[s]
        p[f"cost_{s}"] = d.cost_shift[s]
    for k in DESIGN_KEYS:
        p[k] = getattr(d, k)
    return p


def load_design(path):
    import json
    return design_from_params(json.load(open(path)))


def apply_design(d):
    """Install a Design into the module globals used by the simulator."""
    global DESIGN, START_CAPITAL
    DESIGN = d
    for s in STAGES:
        PAYOUT[s] = [None] + [0 if v == 0 else max(1, round(v * d.payout_scale[s])) for v in BASE_PAYOUT[s][1:]]
        EV[s] = sum(PAYOUT[s][1:]) / 10
        SD[s] = statistics.pstdev(PAYOUT[s][1:])
        AVG_COST[s] = {"Growth": 4.5, "Series A": 5.5, "Seed": 6.5, "Pre-seed": 7.5, "Contrarian": 9.5}[s] + d.cost_shift[s]
    START_CAPITAL = d.start_capital

# name, sector, stage, cost, ability key
STARTUPS = [
    ("Rivian", "Climate", "Growth", 4, "rivian"), ("Orsted", "Climate", "Growth", 5, None),
    ("Tesla", "Climate", "Series A", 5, "tesla"), ("Lightyear", "Climate", "Series A", 6, None),
    ("Watershed", "Climate", "Seed", 6, None), ("Northvolt", "Climate", "Seed", 7, None),
    ("Redwood Materials", "Climate", "Pre-seed", 7, None), ("Impossible Foods", "Climate", "Pre-seed", 8, None),
    ("Climeworks", "Climate", "Contrarian", 9, None), ("ChargePoint", "Climate", "Contrarian", 10, None),
    ("Stripe", "Fintech", "Growth", 4, "stripe"), ("Klarna", "Fintech", "Growth", 5, "klarna"),
    ("Adyen", "Fintech", "Series A", 5, "adyen"), ("Revolut", "Fintech", "Series A", 6, None),
    ("Mollie", "Fintech", "Seed", 6, None), ("Wise", "Fintech", "Seed", 7, None),
    ("bunq", "Fintech", "Pre-seed", 7, None), ("Chime", "Fintech", "Pre-seed", 8, None),
    ("Coinbase", "Fintech", "Contrarian", 9, None), ("Plaid", "Fintech", "Contrarian", 10, None),
    ("Datadog", "Deep Tech", "Growth", 4, None), ("OpenAI", "Deep Tech", "Growth", 5, "openai"),
    ("Legora", "Deep Tech", "Series A", 5, "legora"), ("Lovable", "Deep Tech", "Series A", 6, None),
    ("Snowflake", "Deep Tech", "Seed", 6, None), ("Figma", "Deep Tech", "Seed", 7, "figma"),
    ("Notion", "Deep Tech", "Pre-seed", 7, "notion"), ("Base44", "Deep Tech", "Pre-seed", 8, None),
    ("Anduril", "Deep Tech", "Contrarian", 9, None), ("Palantir", "Deep Tech", "Contrarian", 10, "palantir"),
    ("Picnic", "Consumer", "Growth", 4, None), ("Airbnb", "Consumer", "Growth", 5, "airbnb"),
    ("DoorDash", "Consumer", "Series A", 5, None), ("Parloa", "Consumer", "Series A", 6, None),
    ("Fairphone", "Consumer", "Seed", 6, None), ("Spotify", "Consumer", "Seed", 7, None),
    ("Duolingo", "Consumer", "Pre-seed", 7, "duolingo"), ("Peloton", "Consumer", "Pre-seed", 8, None),
    ("Catawiki", "Consumer", "Contrarian", 9, None), ("WeTransfer", "Consumer", "Contrarian", 10, None),
    ("ViCentra", "Biotech", "Growth", 4, "vicentra"), ("SkinVision", "Biotech", "Growth", 5, None),
    ("Vitestro", "Biotech", "Series A", 5, None), ("Onera Health", "Biotech", "Series A", 6, None),
    ("Sirius Medical", "Biotech", "Seed", 6, None), ("Siilo", "Biotech", "Seed", 7, None),
    ("Mosa Meat", "Biotech", "Pre-seed", 7, "mosa"), ("NovioSense", "Biotech", "Pre-seed", 8, None),
    ("Meatable", "Biotech", "Contrarian", 9, None), ("ShanX Medtech", "Biotech", "Contrarian", 10, None),
    ("Elysian", "Space", "Growth", 4, None), ("Additive Industries", "Space", "Growth", 5, None),
    ("Isispace", "Space", "Series A", 5, None), ("Aiir", "Space", "Series A", 6, None),
    ("Space4Good", "Space", "Seed", 6, None), ("Spherical Systems", "Space", "Seed", 7, None),
    ("Conscious Aerospace", "Space", "Pre-seed", 7, None), ("Ignarion", "Space", "Pre-seed", 8, None),
    ("AeroDelft", "Space", "Contrarian", 9, None), ("SpaceX", "Space", "Contrarian", 10, "spacex"),
]

# Fixed Advisory deck: (A, B, C) modifiers; the sound answer is the max of each triple
ADVISORY = [(-2, 2, 0), (2, -2, 0), (-1, 0, 2), (0, 1, -1), (2, -2, -1), (-2, -1, 2), (1, -1, 1),
            (0, -1, 2), (2, -2, 0), (-2, -2, 2), (-1, 1, -1), (-2, -1, 2), (2, -1, 0), (-2, 2, -1), (1, 0, -1)]

LP_DEMANDS = ["Distribution Call", "Annual Review", "Fee Waiver", "Follow-on Ask", "Liquidity Event",
              "Confidence Vote", "Capital Call", "Side Letter", "Audit Request", "Key Person Clause",
              "Clawback", "Vintage Review", "GP Commitment", "Secondary Sale Fee", "Reporting Deadline",
              "LP Advisory Vote", "Extension Request", "Recapitalization"]
EVENTS = ["Correction", "Momentum", "Pivot", "Acqui-hire", "Regulatory Shift", "Talent War", "Down Round",
          "IPO Window", "Bull Run", "Bear Market", "Founder Drama", "Bidding War", "Media Cycle", "Layoffs",
          "Sovereign Fund", "Whistleblower", "Conference Season", "Currency Shock", "Green Wave",
          "Talent Poaching", "Patent Dispute", "Follow-the-Leader", "Dry Powder", "Black Swan"]
FIRMS = ["Sequoia", "a16z", "Lightspeed", "Accel", "Index", "General Catalyst", "Cherry", "Earlybird",
         "Speedinvest", "Creandum"]
THESES = ["Specialist", "Platform Play", "Steady Hand", "Home Run", "Contrarian", "Operator", "Dealmaker",
          "Climber", "Early Bird", "Untouchable"]
THESIS_BONUS = {"Specialist": 8, "Platform Play": 8, "Steady Hand": 6, "Home Run": 8, "Contrarian": 8,
                "Operator": 8, "Dealmaker": 8, "Climber": 8, "Early Bird": 6, "Untouchable": 6}


def tier_of(rep):
    return 0 if rep <= 2 else 1 if rep <= 4 else 2 if rep <= 6 else 3 if rep <= 8 else 4


def tier_top(t):
    return [2, 4, 6, 8, 10][t]


def clamp(t):
    return max(1, min(10, t))


@dataclass
class Rules:
    stage_stacks: bool = True
    opener_privilege: bool = True
    scout_first_refusal: bool = True
    keep_scouted: bool = True
    rep_profit: int = None       # None = take from DESIGN
    rep_loss_low: int = None
    rep_loss_high: int = None
    rep_bust_extra: int = None
    private_traction: bool = True
    deck_ends_game: bool = False
    cards: bool = True           # events, LP demands, firms, theses, abilities
    advisory_skill: float = 0.7  # chance a player picks the sound Advisory answer


def rules_v21():
    return Rules(stage_stacks=False, opener_privilege=False, scout_first_refusal=False, keep_scouted=False,
                 rep_profit=3, rep_loss_low=1, rep_loss_high=1, rep_bust_extra=0, private_traction=False,
                 deck_ends_game=True, cards=False)


# ----------------------------------------------------------------------------
# Objects
# ----------------------------------------------------------------------------
@dataclass
class Card:
    cid: int
    name: str
    sector: str
    stage: str
    cost: int
    ability: str = None
    duolingo_used: bool = False


@dataclass
class Holding:
    card: Card
    price: int
    traction: int
    coach: int = 0
    coached: bool = False
    halved: bool = False     # Down Round
    sector: str = None       # may be changed by Pivot

    def __post_init__(self):
        self.sector = self.card.sector

    def adjusted(self, extra=0):
        return clamp(self.traction + self.coach + extra)


@dataclass
class Strategy:
    name: str
    risk: float = 0.0          # multiplier on stage SD added to valuation (risk appetite)
    margin: float = 1.0        # required EV premium over price when bidding
    specialist: float = 1.0    # weight on same-sector companions
    scout_bias: float = 0.0    # extra willingness to Scout vs Invest
    coach_threshold: float = 1.5  # min expected gain (after cost) to Coach
    thesis_weight: float = 1.0    # how hard to pursue the Secret Thesis (0 = ignore)
    rep_value: float = 1.5        # value placed on the reputation from a profitable exit
    exit_eager: float = 2.0       # bonus for exiting profitably early (capital reuse)
    hold_loss: float = 3.0        # reluctance to exit at a loss mid-game


STRATEGIES = [
    Strategy("balanced"),
    Strategy("conservative", risk=-0.15, margin=0.5, specialist=0.5, scout_bias=-1.0),
    Strategy("aggressive", risk=0.5, margin=0.0, specialist=0.5),
    Strategy("specialist", risk=0.0, margin=0.8, specialist=2.5),
    Strategy("scout", risk=0.1, specialist=1.0, scout_bias=2.0),
]


@dataclass
class Player:
    idx: int
    strat: Strategy
    firm: str = None
    thesis: str = None
    capital: int = 15
    rep: int = 0
    portfolio: list = field(default_factory=list)
    # card-state
    firm_used: bool = False
    speed_sector: str = None
    consec_losses: int = 0
    scout_extra: int = 0
    skip_invest: bool = False
    skip_scout: bool = False
    access_cap: int = 99
    access_cap_round: int = -1
    last_exit_loss: bool = False
    # thesis tracking
    exits_by_sector: dict = field(default_factory=lambda: defaultdict(int))
    max_sectors_held: int = 0
    rep_ever_lost: bool = False
    max_exit: int = 0
    contrarian_profits: int = 0
    first_profit_round: int = 99
    ever_outbid: bool = False
    # stats
    exits: int = 0
    busts: int = 0
    profit_exits: int = 0
    invests: int = 0
    scouts: int = 0
    scout_buys: int = 0
    coaches: int = 0
    auctions_lost: int = 0
    premium_paid: list = field(default_factory=list)
    tier_reached_round: dict = field(default_factory=dict)
    max_rep: int = 0
    rep_by_round: list = field(default_factory=list)
    thesis_done: bool = False

    def tier(self):
        return tier_of(self.rep)

    def companions(self, sector, exclude=None):
        n = 0
        for h in self.portfolio:
            if h is exclude or h.sector != sector:
                continue
            n += 2 if h.card.ability == "airbnb" else 1
        return n


# ----------------------------------------------------------------------------
# Game
# ----------------------------------------------------------------------------
class Game:
    def __init__(self, strategies, rules, rng):
        self.r, self.rng = rules, rng
        self.players = [Player(i, s, capital=START_CAPITAL) for i, s in enumerate(strategies)]
        self.d = DESIGN
        self.n = len(self.players)
        self.round = 1
        self.first = 0
        self.stack_empties = 0
        self.ended_early = False
        self.build_deck()
        if rules.cards:
            for p, f, t in zip(self.players, rng.sample(FIRMS, self.n), rng.sample(THESES, self.n)):
                p.firm, p.thesis = f, t
                if f == "Speedinvest":
                    p.speed_sector = rng.choice(SECTORS)
            self.lp_deck = LP_DEMANDS[:]
            self.event_deck = EVENTS[:]
            rng.shuffle(self.lp_deck)
            rng.shuffle(self.event_deck)
        self.reset_mods()

    def reset_mods(self):
        self.mods = dict(exit_mult=1, sector_mult={}, sector_add={}, invest_add=0, fintech_add=0,
                         sector_trac={}, free_coach_sector=None, bidding_war=False, media_cycle=False,
                         blocked=set())

    # ---------------- deck ----------------
    def build_deck(self):
        cards = [Card(i, nm, sec, st, max(1, c + DESIGN.cost_shift[st]), ab) for i, (nm, sec, st, c, ab) in enumerate(STARTUPS)]
        self.rng.shuffle(cards)
        self.discards = {st: [] for st in STAGES}
        self.slots = [None] * 5
        self.scouted = [[] for _ in range(5)]
        if self.r.stage_stacks:
            self.stacks = {st: [c for c in cards if c.stage == st] for st in STAGES}
            for st in STAGES:
                self.rng.shuffle(self.stacks[st])
            for t in range(5):
                self.slots[t] = self.stacks[STAGES[t]].pop()
        else:
            self.deck = cards
            for t in range(5):
                self.slots[t] = self.deck.pop()

    def draw_for_tier(self, t):
        if self.r.stage_stacks:
            st = STAGES[t]
            if not self.stacks[st]:
                if self.discards[st]:
                    self.stacks[st], self.discards[st] = self.discards[st], []
                    self.rng.shuffle(self.stacks[st])
                else:
                    self.stack_empties += 1
                    return None
            return self.stacks[st].pop()
        return self.deck.pop() if self.deck else None

    def refill(self):
        if not self.r.keep_scouted:
            for t in range(5):
                for c in self.scouted[t]:
                    self.discards[c.stage].append(c)
                self.scouted[t] = []
        for t in range(5):
            if self.slots[t] is None:
                c = self.draw_for_tier(t)
                if c is None and self.r.deck_ends_game:
                    self.ended_early = True
                self.slots[t] = c

    def access_tier(self, p):
        t = p.tier()
        if self.round == p.access_cap_round:
            t = min(t, p.access_cap)
        return t

    def available(self, p, any_tier=False):
        out = []
        top = 4 if any_tier else self.access_tier(p)
        for t in range(5):
            for c, where in [(self.slots[t], "slot")] + [(c, "scouted") for c in self.scouted[t]]:
                if c is None:
                    continue
                if t <= top or (self.r.cards and c.ability == "adyen"):
                    out.append((c, t, where))
        return out

    def remove_card(self, card, t, where):
        if where == "slot":
            self.slots[t] = None
        else:
            self.scouted[t].remove(card)

    # ---------------- economics ----------------
    def price_for(self, p, card):
        cost = card.cost
        if self.r.cards:
            if card.ability == "duolingo" and not card.duolingo_used:
                cost -= 1
            if p.firm == "Speedinvest" and card.sector == p.speed_sector:
                cost -= 1
        return max(1, cost)

    def surcharge(self, p, card):
        if not self.r.cards:
            return 0
        return self.mods["invest_add"] + (self.mods["fintech_add"] if card.sector == "Fintech" else 0)

    def spec_bonus(self, p, n):
        if n <= 1:
            return 0
        per = self.d.spec_per + (1 if (self.r.cards and p.firm == "Accel") else 0)
        return per * (n - 1)

    def exit_proceeds(self, p, h):
        """(proceeds, bust) under current round mods; used by rules AND agents."""
        extra = self.mods["sector_trac"].get(h.sector, 0) if self.r.cards else 0
        pay = PAYOUT[h.card.stage][h.adjusted(extra)]
        if h.halved:
            pay //= 2
        bust = pay == 0
        if self.r.cards and not bust:
            if h.sector in self.mods["sector_mult"] and h.card.ability != "tesla":
                pay = int(pay * self.mods["sector_mult"][h.sector])
            pay += self.mods["sector_add"].get(h.sector, 0)
            pay *= self.mods["exit_mult"]
        bonus = 0 if bust else self.spec_bonus(p, p.companions(h.sector, exclude=h))
        proceeds = pay + bonus
        if self.r.cards:
            if h.card.ability == "stripe" and not bust:
                proceeds += 2
            if h.card.ability == "mosa" and bust:
                proceeds += 3
        return proceeds, bust

    def valuation(self, p, card):
        s = p.strat
        v = EV[card.stage] + s.risk * SD[card.stage]
        v += s.specialist * 0.6 * self.spec_bonus(p, p.companions(card.sector))
        rounds_left = ROUNDS - self.round
        v += s.rep_value * rounds_left / (ROUNDS - 1)
        if self.r.cards:
            tw = s.thesis_weight
            if p.thesis == "Contrarian" and card.stage == "Contrarian":
                v += 3 * tw
            if p.thesis == "Specialist":
                v += 1.5 * tw * min(2, p.companions(card.sector))
            if p.thesis == "Platform Play" and p.companions(card.sector) == 0:
                v += 1.5 * tw * (1 + len({h.sector for h in p.portfolio}) / 3)
            if p.thesis == "Climber":
                v += 0.5 * tw
            if p.thesis == "Home Run" and card.stage in ("Pre-seed", "Contrarian"):
                v += 1.0 * tw
            if card.ability in ("stripe", "klarna", "figma", "notion"):
                v += 1
            if card.ability == "legora" and any(h.sector == "Deep Tech" for h in p.portfolio):
                v += 1
        if rounds_left <= 1:
            v *= 0.55
        return v

    def acquire(self, p, card, price):
        p.portfolio.append(Holding(card, price, self.rng.randint(1, 10)))
        p.capital -= price
        p.premium_paid.append(price - card.cost)
        if self.r.cards:
            if card.ability == "duolingo":
                card.duolingo_used = True
            if card.ability == "legora" and any(h.sector == "Deep Tech" and h.card is not card for h in p.portfolio):
                p.capital += 1
        p.max_sectors_held = max(p.max_sectors_held, len({h.sector for h in p.portfolio}))

    # ---------------- auction ----------------
    def auction(self, opener, card, t, where):
        r = self.r
        opener.invests += 1
        sur = self.surcharge(opener, card)
        if sur and r.cards and opener.firm == "Index" and not opener.firm_used:
            opener.firm_used, sur = True, 0
        floor = self.price_for(opener, card)
        if opener.capital < floor + sur:
            return
        bidders = [p for p in self.players if p is not opener and self.access_tier(p) >= t
                   and len(p.portfolio) < PORTFOLIO_SIZE]
        maxbid = {p.idx: min(p.capital - self.surcharge(p, card), int(self.valuation(p, card) - p.strat.margin))
                  for p in bidders}
        maxbid[opener.idx] = max(floor, min(opener.capital - sur, int(self.valuation(opener, card) - opener.strat.margin)))
        current, holder = floor, opener
        order = sorted([p for p in bidders if maxbid[p.idx] >= current + 1], key=lambda p: (p.idx - opener.idx) % self.n)
        changed = True
        while changed:
            changed = False
            for p in order:
                if p is not holder and maxbid[p.idx] >= current + 1:
                    current, holder, changed = current + 1, p, True
            if holder is not opener and not r.opener_privilege and maxbid[opener.idx] >= current + 1:
                current, holder, changed = current + 1, opener, True
        if holder is not opener and r.opener_privilege:
            if r.cards and opener.firm == "a16z" and maxbid[opener.idx] >= current:
                holder = opener
            elif maxbid[opener.idx] >= current + 1:
                current, holder = current + 1, opener
        if r.cards and self.mods["bidding_war"]:
            self.mods["bidding_war"] = False
            if holder is opener and current == floor:
                return  # uncontested: the Invest fails, card stays
        if holder is not opener:
            opener.auctions_lost += 1
            opener.ever_outbid = True
        self.remove_card(card, t, where)
        self.acquire(holder, card, current)
        holder.capital -= sur if holder is opener else self.surcharge(holder, card)

    # ---------------- exit ----------------
    def do_exit(self, p, h):
        r = self.r
        if not r.private_traction:
            h.traction = self.rng.randint(1, 10)
        if r.cards and h.card.ability == "klarna" and r.private_traction:
            alt = self.rng.randint(1, 10)
            if PAYOUT[h.card.stage][clamp(alt + h.coach)] > PAYOUT[h.card.stage][h.adjusted()]:
                h.traction = alt
        proceeds, bust = self.exit_proceeds(p, h)
        if r.cards and p.firm == "Sequoia" and not p.firm_used and proceeds > h.price:
            proceeds += 3
            p.firm_used = True
        p.capital += proceeds
        p.exits += 1
        p.max_exit = max(p.max_exit, proceeds)
        p.exits_by_sector[h.sector] += 1
        if bust:
            p.busts += 1
        if proceeds > h.price:
            p.rep += (r.rep_profit if r.rep_profit is not None else self.d.rep_profit) + (1 if r.cards and h.card.ability == "openai" else 0)
            p.profit_exits += 1
            p.consec_losses = 0
            p.last_exit_loss = False
            p.first_profit_round = min(p.first_profit_round, self.round)
            if h.card.stage == "Contrarian":
                p.contrarian_profits += 1
        elif proceeds < h.price:
            ll = r.rep_loss_low if r.rep_loss_low is not None else self.d.rep_loss_low
            lh = r.rep_loss_high if r.rep_loss_high is not None else self.d.rep_loss_high
            loss = ll if p.tier() <= 1 else lh
            if bust:
                loss += r.rep_bust_extra if r.rep_bust_extra is not None else self.d.rep_bust_extra
            p.consec_losses += 1
            p.last_exit_loss = True
            if r.cards:
                if h.card.ability == "rivian" or (p.firm == "Creandum" and h.card.stage == "Contrarian"):
                    loss = 0
                if p.firm == "Earlybird" and p.consec_losses < 2:
                    loss = 0
            if loss > 0:
                p.rep_ever_lost = True
            p.rep -= loss
        p.rep = max(0, min(10, p.rep))
        p.max_rep = max(p.max_rep, p.rep)
        p.tier_reached_round.setdefault(p.tier(), self.round)
        p.portfolio.remove(h)
        self.discards[h.card.stage].append(h.card)

    def plain_value(self, h):
        pay = PAYOUT[h.card.stage][h.adjusted()]
        return pay // 2 if h.halved else pay

    def end_value(self, holdings, known):
        vals = sorted([self.plain_value(h) if known else EV[h.card.stage] for h in holdings], reverse=True)
        return sum(v if i == 0 else (v * 2) // 3 if i == 1 else v // 3 for i, v in enumerate(vals))

    # ---------------- agent ----------------
    def take_turn(self, p):
        a = ACTIONS
        while a > 0:
            a -= self.one_action(p, a)

    def best_exit(self, p, last_round):
        known = self.r.private_traction
        rounds_left = ROUNDS - self.round
        best, best_delta = None, -99
        for h in p.portfolio:
            if h.card.cid in self.mods["blocked"]:
                continue
            rest = [x for x in p.portfolio if x is not h]
            if known:
                proceeds, bust = self.exit_proceeds(p, h)
                hold_val = self.end_value(p.portfolio, True) - self.end_value(rest, True)
                delta = proceeds - hold_val
                s = p.strat
                if proceeds > h.price and rounds_left >= 2:
                    delta += s.exit_eager
                if proceeds < h.price and not last_round:
                    delta -= s.hold_loss
                if self.r.cards:
                    tw = s.thesis_weight
                    if p.thesis == "Home Run" and proceeds >= 15 and p.max_exit < 15:
                        delta += 4 * tw
                    if p.thesis == "Contrarian" and h.card.stage == "Contrarian" and proceeds > h.price and p.contrarian_profits < self.d.contrarian_exits:
                        delta += 4 * tw
                    if p.thesis == "Specialist" and proceeds > h.price:
                        delta += 1.0 * tw
                    if p.thesis == "Steady Hand" and proceeds < h.price:
                        delta -= 4 * tw
                    if p.thesis == "Early Bird" and proceeds > h.price and self.round <= 3 and p.first_profit_round > 3:
                        delta += 3 * tw
                    if p.thesis == "Platform Play" and p.max_sectors_held < self.d.platform_sectors:
                        delta -= 1.5 * tw
            else:
                proceeds = EV[h.card.stage] + self.spec_bonus(p, p.companions(h.sector, exclude=h))
                hold_val = self.end_value(p.portfolio, False) - self.end_value(rest, False)
                delta = proceeds - hold_val + (2.5 if rounds_left >= 2 else 0)
            if delta > best_delta:
                best, best_delta = h, delta
        return best, best_delta

    def coach_cost(self, p, h):
        if not self.r.cards:
            return self.d.coach_cost
        if h.card.ability == "figma" or (p.firm == "Cherry" and p.coaches == 0) or self.mods["free_coach_sector"] == h.sector:
            return 0
        return self.d.coach_cost

    def coach(self, p, h):
        p.capital -= self.coach_cost(p, h)
        p.coaches += 1
        skill = self.r.advisory_skill
        draws = [self.rng.choice(ADVISORY)]
        if self.r.cards and p.firm == "General Catalyst" and not p.firm_used:
            draws.append(self.rng.choice(ADVISORY))
            p.firm_used = True
        m = max(max(o) if self.rng.random() < skill else self.rng.choice(o) for o in draws)
        if self.r.cards:
            if h.card.ability == "vicentra" and not h.coached:
                m += 1
            if h.card.ability == "notion":
                m = max(0, m)
        h.coach += m
        h.coached = True

    def one_action(self, p, actions_left):
        r, s = self.r, p.strat
        last_round = self.round == ROUNDS

        h, delta = self.best_exit(p, last_round)
        if h is not None and delta > (0.5 if last_round else 2.0):
            self.do_exit(p, h)
            return 1
        if last_round:
            return 1

        # coach
        if r.private_traction:
            skill = r.advisory_skill
            best_c, best_gain = None, 0
            for hh in p.portfolio:
                cost = self.coach_cost(p, hh)
                if p.capital < cost:
                    continue
                base = self.plain_value(hh)
                exp = 0
                for opts in ADVISORY:
                    exp += skill * PAYOUT[hh.card.stage][clamp(hh.traction + hh.coach + max(opts))]
                    exp += (1 - skill) * sum(PAYOUT[hh.card.stage][clamp(hh.traction + hh.coach + o)] for o in opts) / 3
                gain = exp / len(ADVISORY) - base - cost
                if r.cards and p.thesis == "Operator" and p.coaches < self.d.operator_coaches:
                    gain += 1.5 * s.thesis_weight
                if gain > best_gain:
                    best_c, best_gain = hh, gain
            if best_c is not None and best_gain >= s.coach_threshold:
                self.coach(p, best_c)
                return 1

        if len(p.portfolio) >= PORTFOLIO_SIZE:
            return 1

        # invest vs scout
        best_card, best_net, use_ls = None, None, False
        cands = self.available(p, any_tier=(r.cards and p.firm == "Lightspeed" and not p.firm_used))
        for card, t, where in cands:
            price = self.price_for(p, card) + self.surcharge(p, card)
            if price > p.capital:
                continue
            rivals = sum(1 for q in self.players if q is not p and self.access_tier(q) >= t and q.capital >= card.cost + 1)
            net = self.valuation(p, card) - (price + 0.5 * rivals)
            if t > self.access_tier(p) and card.ability != "adyen":
                net -= self.d.lightspeed_surcharge
            if best_net is None or net > best_net:
                best_card, best_net = (card, t, where), net
                use_ls = t > self.access_tier(p) and card.ability != "adyen"
        if p.skip_invest:
            best_card = None

        t = min(4, self.access_tier(p) + (1 if r.cards and self.mods["media_cycle"] else 0))
        scout_net = None
        if actions_left >= 2 and r.scout_first_refusal and not p.skip_scout:
            st = STAGES[t]
            exp_cost = AVG_COST[st] if r.stage_stacks else 6.5
            if p.capital >= exp_cost + 1 + p.scout_extra:
                scout_net = (EV[st] + s.risk * SD[st] - exp_cost - p.scout_extra + s.scout_bias - 1.0
                             + 1.5 * (ROUNDS - self.round) / (ROUNDS - 1))
        if scout_net is not None and scout_net > 0 and (best_net is None or scout_net > best_net):
            return self.do_scout(p, t)
        if best_card is not None and best_net > 0:
            card, t2, where = best_card
            if use_ls:
                p.firm_used = True
                p.capital -= self.d.lightspeed_surcharge
            self.auction(p, card, t2, where)
            return 1
        p.skip_invest = False
        return 1

    def do_scout(self, p, t):
        p.scouts += 1
        if p.skip_scout:
            p.skip_scout = False
            return 1
        p.capital -= p.scout_extra
        p.scout_extra = 0
        card = self.draw_for_tier(t)
        if card is None:
            return 1
        price = self.price_for(p, card)
        if self.r.scout_first_refusal and price <= p.capital and self.valuation(p, card) - price > 0:
            self.acquire(p, card, price)
            p.scout_buys += 1
            return 2
        self.scouted[t].append(card)
        return 1

    # ---------------- cards ----------------
    def richest_opponent(self, p):
        return max((q for q in self.players if q is not p), key=lambda q: q.capital + self.end_value(q.portfolio, False))

    def drop_tier(self, p):
        if p.tier() > 0:
            p.rep = tier_top(p.tier() - 1)
            p.rep_ever_lost = True

    def own_top_sector(self, p):
        return max(SECTORS, key=lambda s_: sum(1 for h in p.portfolio if h.sector == s_))

    def resolve_event(self):
        ev = self.event_deck.pop()
        c = self.players[self.first]
        opp = self.richest_opponent(c)
        m = self.mods
        if ev == "Correction":
            m["sector_mult"][max(SECTORS, key=lambda s_: sum(1 for q in self.players if q is not c
                                                             for h in q.portfolio if h.sector == s_))] = 0.5
        elif ev == "Momentum":
            if c.portfolio:
                m["sector_add"][self.own_top_sector(c)] = 2
        elif ev == "Pivot":
            if len(c.portfolio) >= 2:
                sec = self.own_top_sector(c)
                odd = [h for h in c.portfolio if h.sector != sec]
                if odd:
                    odd[0].sector = sec
        elif ev == "Acqui-hire":
            for t in range(4, -1, -1):
                if self.slots[t] is not None and t > self.access_tier(c):
                    self.discards[self.slots[t].stage].append(self.slots[t])
                    self.slots[t] = None
                    break
            c.capital += 1
        elif ev == "Regulatory Shift":
            m["fintech_add"] = 2
        elif ev == "Talent War":
            m["invest_add"] = 1
        elif ev == "Down Round":
            if opp.portfolio:
                max(opp.portfolio, key=lambda h_: EV[h_.card.stage]).halved = True
        elif ev == "IPO Window":
            m["exit_mult"] = 2
        elif ev == "Bull Run":
            for q in self.players:
                q.capital += 1
        elif ev == "Bear Market":
            for q in self.players:
                q.capital = max(0, q.capital - 1)
        elif ev == "Bidding War":
            m["bidding_war"] = True
        elif ev == "Media Cycle":
            m["media_cycle"] = True
        elif ev == "Layoffs":
            if c.portfolio:
                m["free_coach_sector"] = self.own_top_sector(c)
        elif ev == "Sovereign Fund":
            max(self.players, key=lambda q: q.rep).capital += 2
        elif ev == "Whistleblower":
            for q in self.players:
                low = [h for h in q.portfolio if h.adjusted() <= 3 and h.card.ability != "palantir"]
                if low:
                    self.do_exit(q, min(low, key=lambda h_: h_.adjusted()))
        elif ev == "Conference Season":
            for q in self.players:
                card = self.draw_for_tier(self.access_tier(q))
                if card:
                    self.scouted[self.access_tier(q)].append(card)
        elif ev == "Currency Shock":
            m["sector_trac"]["Fintech"] = -1
        elif ev == "Green Wave":
            m["sector_trac"]["Climate"] = 1
        elif ev == "Talent Poaching":
            if opp.capital > 0:
                opp.capital -= 1
                c.capital += 1
        elif ev == "Patent Dispute":
            for q in self.players:
                if q is c:
                    continue
                dt = [h for h in q.portfolio if h.sector == "Deep Tech"]
                if dt:
                    m["blocked"].add(max(dt, key=self.plain_value).card.cid)
                    break
        elif ev == "Dry Powder":
            for q in self.players:
                if q.portfolio:
                    h = min(q.portfolio, key=lambda h_: h_.adjusted())
                    if self.plain_value(h) == 0:
                        q.portfolio.remove(h)
                        self.discards[h.card.stage].append(h.card)
                        q.capital += 1
        elif ev == "Black Swan":
            for q in self.players:
                for h in q.portfolio:
                    if h.card.stage == "Contrarian":
                        h.traction = max(1, h.traction - 2)
        # Founder Drama, Follow-the-Leader: information only

    def resolve_lp(self):
        lp = self.lp_deck.pop()
        for p in self.players:
            self.apply_lp(p, lp)

    def pay(self, p, x):
        p.capital = max(0, p.capital - x)

    def apply_lp(self, p, lp):
        if lp == "Distribution Call":
            if p.capital >= 3 or p.tier() == 0:
                self.pay(p, 3)
            else:
                self.drop_tier(p)
        elif lp == "Annual Review":
            avg = statistics.mean(sum(h.price for h in q.portfolio) for q in self.players)
            if sum(h.price for h in p.portfolio) < avg:
                self.drop_tier(p)
        elif lp == "Fee Waiver":
            p.scout_extra = 1
        elif lp == "Follow-on Ask":
            n = sum(1 for h in p.portfolio if h.card.stage == "Contrarian")
            if n and p.capital >= 2 * n:
                p.capital -= 2 * n
            elif n:
                p.access_cap, p.access_cap_round = 1, self.round + 1
        elif lp == "Liquidity Event":
            cands = [h for h in p.portfolio if h.card.ability != "palantir"]
            if cands:  # table picks the holding most likely to be a loss on public info
                self.do_exit(p, max(cands, key=lambda h_: h_.price - EV[h_.card.stage]))
        elif lp == "Confidence Vote":
            if p.tier() == 0:
                p.capital += 1
            else:
                self.pay(p, 2)
        elif lp == "Capital Call":
            if p.capital >= 2:
                p.capital -= 2
            else:
                p.skip_invest = True
        elif lp == "Side Letter":
            self.pay(p, 3)
        elif lp == "Key Person Clause":
            self.pay(p, p.tier())
        elif lp == "Clawback":
            if p.last_exit_loss:
                self.pay(p, 2)
        elif lp == "Vintage Review":
            if p.invests >= 3:
                self.pay(p, 3)
        elif lp == "GP Commitment":
            self.pay(p, len(p.portfolio))
        elif lp == "Secondary Sale Fee":
            p.capital += 1
        elif lp == "Reporting Deadline":
            if p.strat.scout_bias > 0 and p.capital >= 2:
                p.capital -= 2
            else:
                p.skip_scout = True
        elif lp == "LP Advisory Vote":
            if p.tier() > 0 and self.round < ROUNDS:
                self.drop_tier(p)
            else:
                self.pay(p, 3)
        elif lp == "Extension Request":
            if p.capital >= 2:
                p.capital -= 2
            elif self.lp_deck:
                self.apply_lp(p, self.lp_deck.pop())
        elif lp == "Recapitalization":
            if p.portfolio:
                h = min(p.portfolio, key=lambda h_: h_.adjusted())
                if self.plain_value(h) <= 3:
                    p.portfolio.remove(h)
                    self.discards[h.card.stage].append(h.card)
                    p.capital += 3
        # Audit Request: information only

    # ---------------- run ----------------
    def run(self):
        for rd in range(1, ROUNDS + 1):
            self.round = rd
            self.reset_mods()
            if self.r.cards:
                self.resolve_event()
            for i in range(self.n):
                self.take_turn(self.players[(self.first + i) % self.n])
            if self.r.cards and rd % 4 == 0:
                self.resolve_lp()
            for p in self.players:
                if p.rep == 0:
                    p.rep = 1
                p.rep_by_round.append(p.rep)
                p.max_sectors_held = max(p.max_sectors_held, len({h.sector for h in p.portfolio}))
            self.refill()
            if self.ended_early:
                break
            self.first = (self.first + 1) % self.n
        return self.score()

    def thesis_ok(self, p):
        t = p.thesis
        return {"Specialist": max(p.exits_by_sector.values(), default=0) >= 3,
                "Platform Play": p.max_sectors_held >= self.d.platform_sectors,
                "Steady Hand": not p.rep_ever_lost,
                "Home Run": p.max_exit >= 15,
                "Contrarian": p.contrarian_profits >= self.d.contrarian_exits,
                "Operator": p.coaches >= self.d.operator_coaches,
                "Dealmaker": False,
                "Climber": p.max_rep >= 9,
                "Early Bird": p.first_profit_round <= 3,
                "Untouchable": not p.ever_outbid}.get(t, False)

    def score(self):
        scores = {}
        for p in self.players:
            if not self.r.private_traction:
                for h in p.portfolio:
                    h.traction = self.rng.randint(1, 10)
            p.busts += sum(1 for h in p.portfolio if self.plain_value(h) == 0)
            sc = p.capital + self.end_value(p.portfolio, True)
            if self.r.cards and self.thesis_ok(p):
                sc += THESIS_BONUS[p.thesis]
                p.thesis_done = True
            scores[p.idx] = sc
        return scores


# ----------------------------------------------------------------------------
# Batch + report
# ----------------------------------------------------------------------------
def mean(xs):
    return statistics.mean(xs) if xs else float("nan")


def run_batch(n_games, n_players, rules, seed):
    rng = random.Random(seed)
    stats = defaultdict(lambda: defaultdict(list))
    wins, plays = defaultdict(float), defaultdict(int)
    tier_round = defaultdict(lambda: defaultdict(list))
    firm = defaultdict(lambda: [0.0, 0, []])
    thesis = defaultdict(lambda: [0.0, 0, 0])
    early_ends = stack_empties = 0
    for _ in range(n_games):
        g = Game(rng.sample(STRATEGIES, n_players), rules, rng)
        scores = g.run()
        early_ends += g.ended_early
        stack_empties += g.stack_empties
        best = max(scores.values())
        winners = [i for i, v in scores.items() if v == best]
        for p in g.players:
            nm = p.strat.name
            plays[nm] += 1
            w = (1 / len(winners)) if p.idx in winners else 0
            wins[nm] += w
            st = stats[nm]
            for k, v in dict(score=scores[p.idx], rep=p.rep, exits=p.exits, busts=p.busts, profit_exits=p.profit_exits,
                             auctions_lost=p.auctions_lost, scouts=p.scouts, scout_buys=p.scout_buys, coaches=p.coaches,
                             held_at_end=len(p.portfolio)).items():
                st[k].append(v)
            st["premium"].extend(p.premium_paid)
            st["rep_by_round"].append(p.rep_by_round)
            for t, r_ in p.tier_reached_round.items():
                tier_round[nm][t].append(r_)
            if rules.cards:
                firm[p.firm][0] += w
                firm[p.firm][1] += 1
                firm[p.firm][2].append(scores[p.idx])
                thesis[p.thesis][0] += w
                thesis[p.thesis][1] += 1
                thesis[p.thesis][2] += p.thesis_done
    return dict(stats=stats, wins=wins, plays=plays, tier_round=tier_round, firm=firm, thesis=thesis,
                early_ends=early_ends, stack_empties=stack_empties, n_games=n_games, n_players=n_players)


def report(res, rules, name):
    stats, wins, plays, tier_round = res["stats"], res["wins"], res["plays"], res["tier_round"]
    fair = 100 / res["n_players"]
    print(f"\n=== PORTFOLIO simulation — rules {name}, {res['n_games']} games, {res['n_players']} players, "
          f"advisory skill {rules.advisory_skill:.0%} ===\n")
    print(f"Games ended early: {res['early_ends']}   Stack-empty events: {res['stack_empties']}\n")
    hdr = f"{'strategy':<13}{'win%':>7}{'score':>8}{'rep':>6}{'exits':>7}{'profit':>8}{'busts':>7}{'lostAuc':>9}{'scouts':>8}{'sc.buy':>8}{'coach':>7}{'prem':>6}{'held':>6}"
    print(hdr)
    print("-" * len(hdr))
    for nm in sorted(stats, key=lambda k: -wins[k] / plays[k]):
        st = stats[nm]
        print(f"{nm:<13}{100 * wins[nm] / plays[nm]:>6.1f}%{mean(st['score']):>8.1f}{mean(st['rep']):>6.1f}"
              f"{mean(st['exits']):>7.2f}{mean(st['profit_exits']):>8.2f}{mean(st['busts']):>7.2f}"
              f"{mean(st['auctions_lost']):>9.2f}{mean(st['scouts']):>8.2f}{mean(st['scout_buys']):>8.2f}"
              f"{mean(st['coaches']):>7.2f}{mean(st['premium']):>6.2f}{mean(st['held_at_end']):>6.2f}")
    print("\nAverage round a tier is first reached (share of players who reach it):")
    print(f"{'strategy':<13}" + "".join(f"{t:>11}" for t in TIERS[1:]))
    for nm in stats:
        row = f"{nm:<13}"
        for t in range(1, 5):
            xs = tier_round[nm][t]
            row += f"{mean(xs):>6.1f}({len(xs) / plays[nm]:>3.0%})" if xs else f"{'—':>11}"
        print(row)
    if rules.cards:
        print(f"\nVC Firms (fair share = {fair:.0f}%):")
        print(f"{'firm':<18}{'win%':>7}{'avg score':>11}")
        for f, (w, pl, sc) in sorted(res["firm"].items(), key=lambda kv: -kv[1][0] / kv[1][1]):
            print(f"{f:<18}{100 * w / pl:>6.1f}%{mean(sc):>11.1f}")
        print(f"\nSecret Theses (fair share = {fair:.0f}%):")
        print(f"{'thesis':<15}{'win%':>7}{'completed':>11}")
        for t, (w, pl, done) in sorted(res["thesis"].items(), key=lambda kv: -kv[1][2] / kv[1][1]):
            print(f"{t:<15}{100 * w / pl:>6.1f}%{100 * done / pl:>10.0f}%")
    all_scores = [v for st in stats.values() for v in st["score"]]
    print(f"\nScore across all players: mean {mean(all_scores):.1f}, sd {statistics.pstdev(all_scores):.1f}, "
          f"min {min(all_scores)}, max {max(all_scores)}")
    summary(res, rules)


def summary(res, rules):
    stats, wins, plays, tier_round = res["stats"], res["wins"], res["plays"], res["tier_round"]
    print("\n--- What this means ---")
    active = [k for k in stats if k != "conservative"]
    wr = [100 * wins[k] / plays[k] for k in active]
    spread = max(wr) - min(wr)
    print(f"* Win-rate spread between the four active strategies: {spread:.0f} points "
          f"({'balanced' if spread < 10 else 'one strategy dominates' if spread > 20 else 'slightly skewed'}).")
    all_scores = sorted(v for st in stats.values() for v in st["score"])
    print(f"* Typical final score {statistics.median(all_scores):.0f}; top-10% game {all_scores[int(0.9 * len(all_scores))]}+. "
          f"A passive player ends near {START_CAPITAL}.")
    bc = mean([len(tier_round[k][4]) / plays[k] for k in stats])
    print(f"* {100 * bc:.0f}% of players reach Blue Chip — "
          f"{'sensible pace' if 0.15 < bc < 0.6 else 'too fast' if bc >= 0.6 else 'too slow'}.")
    print(f"* Average player: {mean([v for st in stats.values() for v in st['exits']]):.1f} Exits, "
          f"{mean([v for st in stats.values() for v in st['busts']]):.1f} Busts, "
          f"{mean([v for st in stats.values() for v in st['coaches']]):.1f} Coaches.")
    print(f"* Average premium over printed cost: {mean([v for st in stats.values() for v in st['premium']]):.1f} capital.")
    if rules.cards:
        fr = {f: 100 * w / pl for f, (w, pl, _) in res["firm"].items()}
        th = {t: 100 * d / pl for t, (_, pl, d) in res["thesis"].items()}
        print(f"* Firm win-rate range: {min(fr, key=fr.get)} {min(fr.values()):.0f}% to {max(fr, key=fr.get)} {max(fr.values()):.0f}%. "
              f"Anything outside roughly 18-32% is worth a look.")
        print(f"* Thesis completion range: {min(th, key=th.get)} {min(th.values()):.0f}% to {max(th, key=th.get)} {max(th.values()):.0f}%. "
              f"Aim for roughly 25-60% each.")


def plot(res, rules, name, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed - run:  pip install matplotlib  - for charts)")
        return
    stats, wins, plays = res["stats"], res["wins"], res["plays"]
    names = sorted(stats, key=lambda k: -wins[k] / plays[k])
    fair = 100 / res["n_players"]
    nrows = 3 if rules.cards else 2
    fig, ax = plt.subplots(nrows, 2, figsize=(14, 4.5 * nrows))
    fig.suptitle(f"PORTFOLIO simulation — rules {name}, {res['n_games']} games")
    a = ax[0][0]
    a.bar(names, [100 * wins[n] / plays[n] for n in names], color="#355A7A")
    a.axhline(fair, ls="--", color="grey", lw=1)
    a.set_title(f"Win rate by strategy (dashed = {fair:.0f}%, fair share)")
    a = ax[0][1]
    for n in names:
        a.hist(stats[n]["score"], bins=range(0, 90, 4), alpha=0.45, label=n)
    a.axvline(START_CAPITAL, ls="--", color="grey", lw=1)
    a.set_title("Final score distribution (dashed = starting capital)")
    a.legend()
    a = ax[1][0]
    for n in names:
        rows_ = stats[n]["rep_by_round"]
        a.plot(range(1, ROUNDS + 1), [mean([r[i] for r in rows_ if len(r) > i]) for i in range(ROUNDS)], marker="o", label=n)
    for y, t in ((2.5, "Emerging"), (4.5, "Notable"), (6.5, "Prominent"), (8.5, "Blue Chip")):
        a.axhline(y, ls=":", color="grey", lw=0.8)
        a.text(8.1, y + 0.1, t, fontsize=8, color="grey")
    a.set_title("Average reputation by round")
    a.set_ylim(0, 10)
    a.legend()
    a = ax[1][1]
    xs = [AVG_COST[s] for s in STAGES]
    a.scatter(xs, [EV[s] for s in STAGES], s=80, color="#D6B85C", zorder=3)
    for s, x_ in zip(STAGES, xs):
        a.annotate(f"{s}\nEV {EV[s]:.1f}, SD {SD[s]:.1f}", (x_, EV[s]), textcoords="offset points", xytext=(6, -14), fontsize=8)
    a.plot([3, 11], [3, 11], ls="--", color="grey", lw=1)
    a.set_title("Stage: average cost vs expected payout (dashed = break-even)")
    if rules.cards:
        a = ax[2][0]
        fs = sorted(res["firm"], key=lambda f: -res["firm"][f][0] / res["firm"][f][1])
        a.barh(fs, [100 * res["firm"][f][0] / res["firm"][f][1] for f in fs], color="#355A7A")
        a.axvline(fair, ls="--", color="grey", lw=1)
        a.set_title("Win rate by VC Firm (%)")
        a.invert_yaxis()
        a = ax[2][1]
        ts = sorted(res["thesis"], key=lambda t: -res["thesis"][t][2] / res["thesis"][t][1])
        a.barh(ts, [100 * res["thesis"][t][2] / res["thesis"][t][1] for t in ts], color="#D6B85C")
        a.set_title("Secret Thesis completion rate (%)")
        a.invert_yaxis()
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"\nCharts saved to {path}")


def main():
    ap = argparse.ArgumentParser(description="Portfolio board game balance simulator")
    ap.add_argument("--games", type=int, default=2000)
    ap.add_argument("--players", type=int, default=4, choices=[3, 4])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rules", choices=["v22", "v21"], default="v22")
    ap.add_argument("--no-cards", action="store_true", help="core rules only: no events, LP demands, firms, theses, abilities")
    ap.add_argument("--advisory-skill", type=float, default=0.7, help="chance a player picks the sound Advisory answer (0-1)")
    ap.add_argument("--no-opener", action="store_true")
    ap.add_argument("--random-slots", action="store_true")
    ap.add_argument("--plot", action="store_true", help="save charts to portfolio_sim_<rules>.png (needs matplotlib)")
    ap.add_argument("--design", help="JSON design file, e.g. design_v23.json (default: v2.2 numbers)")
    args = ap.parse_args()

    if args.design:
        apply_design(load_design(args.design))

    rules = rules_v21() if args.rules == "v21" else Rules()
    name = args.rules + ("_" + args.design.rsplit("/", 1)[-1].replace(".json", "") if args.design else "")
    rules.advisory_skill = args.advisory_skill
    if args.no_cards and rules.cards:
        rules.cards = False
        name += "_nocards"
    if args.no_opener:
        rules.opener_privilege = False
        name += "_noopener"
    if args.random_slots:
        rules.stage_stacks = False
        name += "_randomslots"
    res = run_batch(args.games, args.players, rules, args.seed)
    report(res, rules, name)
    if args.plot:
        plot(res, rules, name, f"portfolio_sim_{name}.png")


if __name__ == "__main__":
    main()
