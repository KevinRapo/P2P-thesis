# Tariffs and the peer charge

> What a kWh costs from the DSO, what it earns when sold to it, and what is left
> for a peer trade to share. The peer charge decides that last part: it is the one
> setting that fixes how much the local market can be worth at all, so it is
> explained here in full. Its value is open (MP-4h, [below](#the-decision-mp-4h)).

## The two tariffs

Every participant can always trade with the DSO: buy at the utility price
$p_\text{utility}$ and sell at the feed-in tariff $p_\text{FiT}$ ([P1] §3.4.4). Both
come from the scenario's `dso.prices` ([Configuration](../config/reference.md#dso)),
flat or one price per step, and the DSO moves to each step's prices before the step
([`Dso.set_hour`](../../core/market/dso.py#L120-L123)). Untraded energy is settled at
these tariffs too (MP-1e, [Settlement](market-step.md#4-settlement)).

A peer trade is worth making only at a price between the two: the seller earns more
than $p_\text{FiT}$, the buyer pays less than $p_\text{utility}$. [P1] §3.3.2 requires
$p_\text{FiT} < p_\text{P2P} < p_\text{utility}$, and
[`DsoSetup.problems`](../../core/config/scenario.py#L319-L357) refuses tariffs that
leave no room at some step.

### The reference prices: `de_2024`

The market experiments use [`de_2024.json`](../../config/data/de_2024.json), built by
[`build_de_2024.py`](../../config/data/build_de_2024.py) as a dynamic household
tariff from the German day-ahead prices of 2024 (Energy-Charts, DE-LU). With
$s = \max(\text{spot}, 0)$ per kWh, every hour:

$$
\begin{aligned}
p_\text{utility} &= s + a, \qquad a = \bar p_\text{household} - \bar s_{2024} \\
p_\text{FiT} &= \max(s - 0.004,\ 0)
\end{aligned}
$$

where $\bar p_\text{household}$ is the average German household price of 2024 and
$\bar s_{2024}$ the mean spot price of 2024 (0.0785). The adder $a$ = 0.3163 makes the
year's mean utility price equal the household price; 0.004 is an assumed direct
marketer's fee on sold energy.

The household price is DESTATIS's, for the band 2,500 to 5,000 kWh a year (band DC),
in ct/kWh:

| Component | H1 2024 | H2 2024 | Mean, in the build script |
|---|---|---|---|
| Energy and supply (*Energie und Vertrieb*) | 16.75 | 16.33 | 16.54 |
| Network charges (*Netzentgelte*) | 11.31 | 11.64 | 11.475 → 11.47 |
| Taxes, levies and surcharges (*Steuern, Abgaben und Umlagen*) | 11.45 | 11.47 | 11.46 → 11.47 |
| **Total** | **39.51** | **39.43** | **39.48** |

Sources: DESTATIS press releases [PD24_375](https://www.destatis.de/DE/Presse/Pressemitteilungen/2024/09/PD24_375_61243.html)
(H1) and [PD25_123](https://www.destatis.de/DE/Presse/Pressemitteilungen/2025/03/PD25_123_61243.html)
(H2), checked on 5 Nov 2026. The two equal components in the script (0.1147 each)
are the two half-year means rounded, not a copying slip; the taxes part rounds to
11.46 on its own, a difference of 0.0001 EUR/kWh in the total.

**What follows from the construction.** Both tariffs move with the spot price, so
their gap is almost constant:

$$
p_\text{utility} - p_\text{FiT} = a + \min(s, 0.004) \approx 0.32 \text{ EUR/kWh}
$$

at every hour of the year (minimum 0.3163, mean 0.3200). A kWh traded between
neighbours is worth the same at noon as at night; what changes over the day is only
the price level, which is what a battery can earn from by shifting energy in time.
In [`de_2024_flat.json`](../../config/data/de_2024_flat.json) the feed-in tariff is a
flat 0.08 instead (about the 2024 EEG rate for small rooftop PV), and the gap follows
the spot price.

## What a peer trade avoids, in reality

The household price is three parts, and buying from a neighbour replaces only some
of them. The energy comes from the neighbour instead of the supplier, but it still
flows through the public low-voltage network, and taxes and levies are charged on
consumed electricity whatever its source. Whether a regime charges those parts on a
peer kWh is a regulatory choice:

- **[P1] and the original code:** no charge. A peer trade pays only the eq. 8 grid
  fees ([Fees](market-step.md#6-fees)), which are the paper's own construction and
  small in our scenario (about 3 EUR over 14 test days on `lv_rural3_p13`).
- **Germany, §42c EnWG** (energy sharing, in force since 1 June 2026): shared
  electricity pays the normal network charges, levies and taxes, without a
  reduction ([Gleiss Lutz](https://www.gleisslutz.com/en/know-how/energy-sharing-joint-use-renewable-electricity-under-new-section-42c-energy-industry-act),
  [innobu](https://www.innobu.com/en/articles/energy-sharing-section-42c-2026.html),
  [aceflex](https://www.aceflex.de/?p=191111)). One source reports an
  electricity-tax exemption (2.05 ct/kWh) for plants up to 2 MW in a local area
  ([Interreg Europe](https://www.interregeurope.eu/news-events/news/energy-sharing-now-easier-to-implement-in-germany-too));
  the others do not mention it.
- **Austria, renewable energy communities** (§16c ElWOG, being replaced by the
  ElWG): a local community pays about 57 % less network usage charge at low
  voltage (a regional one 28 % less), and the renewable levies and the electricity
  levy are waived ([UIV](https://stadtarchiv.ulm.de/-/media/ulm/zda/downloads/missionsmartcity/zia/uiv-eg-prsentation_250523.pdf),
  [Energie NÖ](https://www.energie-noe.at/download/5141),
  [Taylor Wessing](https://www.taylorwessing.com/de/insights-and-events/insights/2025/09/energy-communities-in-austria-and-the-new--electricity-industry-act));
  secondary sources, the legal text still to be checked before citing.

No EU regime found waives everything: a charge of 0 is the paper's idealised market.

## The peer charge in the code

`DsoSetup.peer_charge_kwh` ([scenario.py](../../core/config/scenario.py#L272-L305))
is a charge per kWh on every peer-to-peer trade, in all three clearing stages. It is
not in [P1]; 0, the default, is the paper's market.

| What | Where |
|---|---|
| Added to each peer trade's fee parts as `peer_charge` = charge × quantity | [`Dso.fees_of`](../../core/market/dso.py#L216) |
| Paid whole by the buyer; the rest of the fee is split by `fee_buyer_share` | [`Dso._charged`](../../core/market/dso.py#L238-L257) |
| Not charged on a trade with the DSO: its utility price already holds these parts, and feed-in pays none | same |
| Lowers the highest peer price to the **peer ceiling** $p_\text{utility} - c$, so a buyer never pays more than the DSO asks; order prices stop there | [`Dso.peer_ceiling`](../../core/market/dso.py#L138-L144), [order prices](market-step.md#2-orders) |
| Moves the reference price before any trade to the midpoint of $p_\text{FiT}$ and the ceiling | [`Dso.market_price`](../../core/market/dso.py#L146-L150) |
| Tariffs must leave $p_\text{FiT} < p_\text{utility} - c$ at every step | [`DsoSetup.problems`](../../core/config/scenario.py#L319-L357) |
| Off with `fees_charged = false` (no ceiling, nothing paid; still recorded) | [`Dso.peer_ceiling`](../../core/market/dso.py#L138-L144) |
| Recorded per trade and per day as `peer_charge`; the buyer's gain is counted net of it | [Metrics](../studio/results/metrics.md) |

The peer price band is therefore $p_\text{FiT} < p_\text{P2P} < p_\text{utility} - c$,
and its width $p_\text{utility} - p_\text{FiT} - c$ is all a peer trade can share
between buyer and seller.

## What each setting leaves

With `de_2024` (gap about 0.32 EUR/kWh):

| Regime | $c$ (EUR/kWh) | Left to share per kWh | Basis |
|---|---|---|---|
| [P1], now | 0 | about 0.32 | no charge |
| Austria-like | about 0.13 to 0.15 | about 0.17 to 0.19 | 43 % of the network charges, VAT and the concession fee kept, electricity tax and levies waived: an estimate on German components, to be worked out from the levy-level split |
| Germany §42c | 0.2294 | about 0.09 | network charges + taxes and levies, the two DESTATIS parts above |

Under §42c the peer trade competes only with the supplier's energy-and-supply part:
the buyer saves what a supplier adds over the spot price, the seller gains what the
spot price pays over the feed-in. That is the realistic case for Germany, and it
leaves the market less than a third of its value under the paper's assumption.

## What depends on it

- **The VTI ceiling** ([ceiling.py](../../core/runner/ceiling.py)) assumes peer
  transfers are free: its LP nets the community's energy without the charge. VTI is
  correct only at $c = 0$; any arm with a charge needs the LP to charge peer
  transfers first (RP-7g).
- **`reachable_share`** in the validation tables assumes free netting the same way
  and reads low at $c > 0$ ([Validation](../studio/results/validation.md)).
- **The rule-based bidders** price inside the band
  ([`rule_based_bid.py`](../../core/market/agent/rule_based_bid.py#L80)), and the RL
  price action is mapped onto it ([Action](environment/action.md)): both follow the
  ceiling without a change.
- **The learning signal.** The charge scales down what a peer trade is worth, so
  every reward from trading shrinks with it; a battery's shift in time does not pay
  it when it charges from its owner's own surplus.

## The decision (MP-4h)

Open ([plan](../plan/open.md)). The options:

1. **0 as the main setting**, described as the paper's idealised market; results
   are an upper bound on what P2P can be worth, §42c a sensitivity arm.
2. **§42c (0.2294) as the main setting**, consistent with the German prices already
   in use; the market keeps under a third of its value.
3. **0 as the main setting plus two referenced arms** (Austria-like and §42c),
   reported as how much of the value survives regulation.

Before any arm with a charge: the ceiling LP charges peer transfers (above); for the
Austria-like arm, its value from the levy-level split of the household price.
