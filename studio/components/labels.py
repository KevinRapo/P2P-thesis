"""The names the Studio shows for scenario choices, shared by the pages that set
them and the pages that summarise them."""

from core.grid.losses import LOSS_ALLOCATIONS

MECHANISMS = {
    "average": "Average",
    "buyer": "Buyer's price",
    "seller": "Seller's price",
    "bid_ask_spread": "Bid-ask spread",
    "nash_bargaining": "Nash bargaining",
    "proportional_surplus": "Proportional surplus",
}
BACKGROUNDS = {
    "profiles": "SimBench profiles",
    "off": "Off: only the participants",
}
STEP_LENGTHS = {1.0: "1 hour (24 steps)", 0.25: "15 minutes (96 steps)"}
GRID_METHODS = {
    "powerflow": "AC power flow",
    "graph": "Graph model of the paper",
}
GRAPH_CAPACITIES = {
    "paper": "A total spread over the lines",
    "ratings": "Each line's rating",
}
VOLTAGE_DROPS = {
    "distance": "From the distance",
    "measured": "Measured in the power flow",
}
# Eq. 18 per trade, then every rule of core/grid/losses.py, named by its label: a new
# rule appears here without a change to the Studio.
LOSSES = {"trades": "Per trade, from the distance (eq. 18)"} | {
    name: rule.label for name, rule in LOSS_ALLOCATIONS.items()
}
