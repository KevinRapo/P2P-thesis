# Glossary

> The terms these pages use, in one line each, with the page that explains them.

## The market

| Term | Meaning |
|---|---|
| **LEM** | Local energy market: households with loads, PV and batteries that trade energy with each other in one low-voltage network ([market step](../methodology/market/step.md)) |
| **Participant** | A market member that owns some of the network's loads, generators and batteries, and places one order per step |
| **Background** | The network's elements that belong to no participant. They load the grid in the power flow but do not trade |
| **P2P** | Peer to peer: a trade between two participants |
| **DSO** | Distribution system operator: it buys and sells whatever the peers do not match, and charges the grid fees |
| **Utility price** | What the DSO charges per kWh bought from it ([tariffs](../methodology/market/tariffs.md)) |
| **Feed-in tariff (FiT)** | What the DSO pays per kWh sold to it |
| **Peer charge** | The grid charges a buyer still pays on a peer trade: the part of the utility price a peer trade does not avoid (MP-4h, [tariffs](../methodology/market/tariffs.md#the-decision-mp-4h)) |
| **Order** | A side (buy or sell), a quantity, a price and a preferred partner |
| **Clearing** | Matching the orders: preferred partners, then the double auction, then the DSO ([§3](../methodology/market/step.md#3-clearing)) |
| **Pricing mechanism** | How a matched pair's price is set from the bid and the ask ([config](../using/running/config.md)) |
| **Reputation** | A score per participant, updated every step. It weighs partner choice and breaks ties in the double auction |
| **Fees** | The DSO's charges on a trade: congestion, thermal, voltage, transmission and imbalance parts, less a bonus for trades within one feeder ([§6](../methodology/market/step.md#6-fees)) |

## The grid

| Term | Meaning |
|---|---|
| **SimBench** | German benchmark grids with line data and a year of 15-minute profiles ([SimBench](../using/data/simbench.md)) |
| **Profile** | A time series of factors of an element's rated power; SimBench's loads and generators each follow one ([profiles](../using/data/profiles.md)) |
| **Study case** | One of SimBench's fixed planning situations (hL, hPV, lPV…): every element at a set share of its rated power, replacing its profile |
| **Grid method** | How the market sees the grid: `powerflow` (an AC power flow) or `graph` (the paper's graph model) ([grid methods](../methodology/market/grid-methods.md)) |
| **Line loading** | A line's current as a share of its rating, in %. The congestion and thermal fees read it |

## Learning

| Term | Meaning |
|---|---|
| **PPO** | Proximal policy optimisation, the one learning algorithm in this version (RLlib's) ([learning layer](../methodology/learning/index.md)) |
| **Mixed action** | The paper's action: side and partner chosen from lists (categorical), quantity and price as numbers (continuous) ([action](../methodology/environment/action.md)) |
| **β** | The partner part of the action: which peer, or the DSO, an agent prefers |
| **Observation** | What an agent sees each step: the paper's 42 signals plus the peers' reputations ([observation](../methodology/environment/observation.md)) |
| **Reward** | What an agent is trained to maximise; by default its bill for the step ([reward](../methodology/environment/reward.md)) |
| **Paradigm** | How the agents are trained together. **CTCE**: one policy acts for everyone. **CTDE**: each agent acts on its own observation; the critics see everyone (as MAPPO). **DTDE**: each agent learns alone |
| **Probe** | A tiny environment with a known correct answer, used to check the learner ([probes](../methodology/validation/probes.md)) |

## Experiments and results

| Term | Meaning |
|---|---|
| **Scenario** | A network, a day, the participants and the market settings, as one JSON file in `config/scenarios/` ([config](../using/running/config.md)) |
| **Experiment** | Paradigms × seeds × variants on one scenario, with budget and settings, as one JSON file in `config/experiments/` ([experiments](../using/running/runs.md)) |
| **Run** | One combination of an experiment: one paradigm, seed and variant, trained and evaluated ([how a run is judged](../methodology/evaluation/index.md#when-results-are-made)) |
| **Budget** | The number of environment steps a run trains for |
| **Target** | Where an experiment runs: `local` (this PC) or `taltech` (the SLURM cluster) |
| **Test profile** | An experiment's smallest version (`--profile test`), to check it starts |
| **Baselines** | What a trained policy is compared with: net position, the market's rule, played on the test days; non-P2P and the ceiling, calculated |
| **Ceiling** | The most money the community could make on the test days, with perfect foresight ([evaluation](../methodology/evaluation/index.md#the-ceiling)) |
| **Non-P2P** | Every participant on its own with the DSO, its battery used as well as it could be. The reference "no market" |
| **VTI** | Value tapping index: the share of the gap from non-P2P to the ceiling that the policy reaches. 0 = no better than on their own, 1 = the ceiling ([metrics](../methodology/evaluation/metrics.md)) |

## The documentation's own labels

| Label | Meaning |
|---|---|
| **[P1], [P2]** | The two MARLEM papers: the framework paper (Applied Energy, 2026) and the learning-results preprint ([register](../original/issues/register.md#about-this-register)) |
| **M-, E-, L-, D-** | An issue in the original MARLEM: market; environment and cooperation; learning; experiments and data ([issue register](../original/issues/register.md)) |
| **MP-, RP-** | A question about this version's market (`MP-`) or its learning and results (`RP-`), decided or still open ([open items](../temp/open.md)) |
