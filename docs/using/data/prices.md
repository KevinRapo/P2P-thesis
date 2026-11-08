# Prices: the German dynamic tariff and the feed-in

> Where the DSO's prices come from:
> - the **utility price** $p_\text{utility}$, what a participant pays per kWh bought
>   from the DSO;
> - the **feed-in tariff** $p_\text{FiT}$, what it earns per kWh sold to the DSO.
>
> The market experiments use German day-ahead prices of 2024, turned into a dynamic
> household tariff, so both prices change every hour. What a peer trade leaves of the
> gap between them is on [Tariffs and the peer charge](../../methodology/market/tariffs.md).

## The price files

The scenario's `dso.prices` names a file in [config/data/](../../../config/data/), or
gives two flat prices
([config reference](../config.md#price-file)). Before each step, the DSO
takes that step's two prices
([`Dso.set_hour`](../../../core/market/dso.py#L120-L123)). They are the same for every
participant.

| File | Utility price | Feed-in tariff | Used by |
|---|---|---|---|
| [`de_2024.json`](../../../config/data/de_2024.json) | Spot price + a fixed adder, every hour of every day | Spot price − 0.004 | **The market experiments** (`base_long_p13`, `ctde_sweep_p13`, …), set in the experiment |
| [`de_2024_flat.json`](../../../config/data/de_2024_flat.json) | The same | Flat 0.08 | A variant |
| [`synthetic_day.json`](../../../config/data/synthetic_day.json) | Time of use: 0.20 at night, 0.30 by day, 0.40 from 17:00 to 22:00, the same every day | Flat 0.08 | The saved scenarios and the market tests (MP-0b) |
| [`synthetic_day_15min.json`](../../../config/data/synthetic_day_15min.json) | The same per quarter-hour | Flat 0.08 | Quarter-hour scenarios |

All prices are in EUR per kWh. Every file is plotted in the Studio's
**Inspect → Prices** tab.

## How `de_2024` is built

[`build_de_2024.py`](../../../config/data/build_de_2024.py) builds both German files from
two sources:

1. the hourly **day-ahead prices** of the DE-LU bidding zone for 2024, from
   [Energy-Charts](https://api.energy-charts.info/), saved as
   [`de_day_ahead_2024.csv`](../../../config/data/de_day_ahead_2024.csv);
2. the average **household price** of 2024 from DESTATIS.

With $s = \max(\text{spot}, 0)$ per kWh, every hour:

$$
\begin{aligned}
p_\text{utility} &= s + a, \qquad a = \bar p_\text{household} - \bar s_{2024} \\
p_\text{FiT} &= \max(s - 0.004,\ 0)
\end{aligned}
$$

where:
- $\bar p_\text{household}$ = 0.3948 is the 2024 household price;
- $\bar s_{2024}$ = 0.0785 is the mean spot price of 2024;
- 0.004 is an assumed fee of a direct marketer on sold energy.

**The utility price.** A dynamic tariff passes the spot price through and adds
everything else a household pays:
- the supplier's margin;
- the network charges;
- taxes and levies.

The adder $a$ = 0.3163 makes the year's mean utility price equal the household
price. Real dynamic tariffs add these parts per kWh in the same way. Negative spot
prices are set to 0, so a household is never paid for buying.

**The feed-in tariff.** A PV owner selling at market price, through a direct
marketer, earns the spot price minus the marketer's fee, and nothing in hours of
negative prices. This is how larger German PV sells today. A small rooftop system
would usually get the fixed EEG rate instead; that is the flat 0.08 of
`de_2024_flat`.

### The household price

DESTATIS publishes the household price for the consumption band 2,500 to 5,000 kWh
a year (band DC) in three parts. Figures in ct/kWh:

| Component | H1 2024 | H2 2024 | Mean, in the build script |
|---|---|---|---|
| Energy and supply (*Energie und Vertrieb*) | 16.75 | 16.33 | 16.54 |
| Network charges (*Netzentgelte*) | 11.31 | 11.64 | 11.475 → 11.47 |
| Taxes, levies and surcharges (*Steuern, Abgaben und Umlagen*) | 11.45 | 11.47 | 11.46 → 11.47 |
| **Total** | **39.51** | **39.43** | **39.48** |

Sources: DESTATIS press releases [PD24_375](https://www.destatis.de/DE/Presse/Pressemitteilungen/2024/09/PD24_375_61243.html)
(H1) and [PD25_123](https://www.destatis.de/DE/Presse/Pressemitteilungen/2025/03/PD25_123_61243.html)
(H2), checked on 5 Nov 2026. The two equal components in the script (0.1147 each)
are the two half-year means, rounded. The taxes part on its own rounds to 11.46,
a difference of 0.0001 EUR/kWh in the total.

The same three parts decide what a peer trade can avoid
([peer charge](../../methodology/market/tariffs.md#what-a-peer-trade-avoids-in-reality)).

### Which day's prices a market day uses

The SimBench profiles are from 2016, the prices from 2024. Each simulated day of
2016 takes the prices of the 2024 day **2926 days later**, which falls on the same
weekday. For example, 2016-06-01 and 2024-06-05 are both Wednesdays. So weekday and
weekend patterns of load and price stay together, while the seasons shift by four
days.

The file keeps the simulated dates as keys under `days`, and the shift as
`date_shift`. The Inspect page uses the shift to show the real dates. A clock-change
day keeps 24 hours: the missing hour repeats the one before, and the doubled hour is
averaged. The top-level `utility` and `feed_in` are the mean day, for reading only.
The market trades at each date's own prices and refuses a date the file does not
have.

## What the prices look like

Computed from `de_2024.json`:

| Window | Days | Utility, mean (min–max) | Feed-in, mean (max) | Hours with feed-in 0 | Daily max − min of the utility price, mean |
|---|---|---|---|---|---|
| Whole year | 366 | 0.396 (0.316–1.253) | 0.076 (0.932) | 737 | 0.107 |
| Training, June | 30 | 0.390 (0.316–0.526) | 0.070 (0.206) | 93 | 0.120 |
| Test, 1–14 July | 14 | 0.379 (0.316–0.574) | 0.059 (0.253) | 65 | 0.139 |

The mean summer day has a **midday dip and an evening peak**. Over the test days,
the hourly means are:
- about 0.37 at night;
- 0.335 at 13:00 to 14:00, when PV pushes the spot price down;
- 0.463 at 20:00.

That is a spread of about 13 ct/kWh within a day. A battery can earn from it by
charging at noon and discharging in the evening.

**The gap is nearly constant.** Both tariffs follow the same spot price, so:

$$
p_\text{utility} - p_\text{FiT} = a + \min(s, 0.004) \approx 0.32 \text{ EUR/kWh}
$$

at every hour of the year (minimum 0.3163, mean 0.3200). A kWh traded between
neighbours is therefore worth the same at noon as at night. The hour changes only
the price level, and that is what pays for shifting energy in time. With
`de_2024_flat`, the gap follows the spot price instead.

## Where the prices enter the model

| Where | How | Page |
|---|---|---|
| Settlement | Energy traded with the DSO, and energy left untraded, is paid at the step's two prices | [Settlement](../../methodology/market/step.md#4-settlement) |
| Order prices | Peer prices must lie between the two tariffs, $p_\text{FiT} < p_\text{P2P} < p_\text{utility}$ ([P1] §3.3.2), less the peer charge; a file that leaves no room at some step is refused | [Tariffs](../../methodology/market/tariffs.md#the-two-tariffs) |
| The agents' price action | Mapped onto that band at each step, so the same action means a different price at a different hour | [Action](../../methodology/environment/action.md) |
| The observation | Both prices of the step about to be played are observed (`dso_buy_price`, `dso_sell_price`), scaled to a fixed range (`tariff_range`) | [Observation](../../methodology/environment/observation.md) |
| The references | The ceiling and non-P2P money use the same prices per step | [Results](../studio/results/index.md#baselines-and-references) |

## Rebuilding the files

From the repository root, in the `marlem` environment:

```
python config/data/build_de_2024.py
python config/data/build_de_2024.py download
```

The first command rebuilds both German files from the saved CSV. The second
downloads the CSV from Energy-Charts again first.

For another year or country, change the source URL, the household price and the
date shift in the script's constants.
