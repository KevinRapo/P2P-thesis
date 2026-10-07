# SimBench profiles: the time series of loads and generators

> What a SimBench profile is, how the Studio turns it into power, and where each
> class of profiles comes from: households, businesses, farms, heat pumps, electric
> vehicles, PV, wind, biomass, hydro, storage and whole grids.
> SimBench in general: [overview](README.md) · Which networks use which profiles:
> [network catalogue](networks.md).

Section numbers like §3.5.2 refer to the SimBench documentation, version 1.1.0
(see the [overview](README.md) for the full reference). Counts, means and peaks in
the tables are measured from the data set the Studio reads (scenario 0 unless
stated).

## 1. What a profile is

A profile is a **normalised** time series: for every quarter hour of 2016 it gives
a factor of an element's rated power. The element (a load, static generator or
storage unit) names its profile in its `profile` column; many elements share one
profile.

$$
P_e(t) = p_{e} \cdot f_{\text{profile}(e)}(t), \qquad
Q_e(t) = q_{e} \cdot f^{q}_{\text{profile}(e)}(t)
$$

with $p_e$ the element's rated active power (`p_mw`) and $q_e$ its rated reactive
power (`q_mvar`).

| Property | Value |
|---|---|
| Year | 2016, a leap year: 366 days |
| Resolution | 15 minutes: 96 values per day, **35,136** per year |
| Scale | factor of rated power; 1.0 = rated power |
| Reactive power | loads have a P and a Q profile (`H0-A_pload`, `H0-A_qload`); generators and storage have P only |
| Tables | `load`, `renewables` (PV, wind, biomass, hydro, grids), `powerplants` (EHV plants, imports), `storage` |

Things to know when reading the numbers:

- **Peaks are not always 1.** Load profiles reach 1.0; PV profiles peak at most at
  0.63 of rated power, because panels rarely deliver their rating.
- **Q factors can be negative**: some measured loads feed reactive power back at
  times.
- **Rated power is not energy.** A household of 3 kW with H0-A draws on average
  0.19 × 3 kW ≈ 0.6 kW. The mean factors below show how far each class stays below
  its rating.
- **Time stamps.** Measurements from other years (feed-in 2011/2012, hydro 2017,
  households 2010) were moved onto the 2016 calendar, with daylight saving time
  taken into account; the leap day was filled with the mean of the neighbouring
  same weekdays (§3.5.4).

### In the Studio

The Inspect page shows profiles in two ways:

- **Factor** (the Profiles section of a network, and the Profiles tab with SimBench's
  whole catalogue): the normalised values above.
- **kW** ("Sum per profile" / "Per element"): factor × rated power of the elements
  that use the profile, as in the formula above.

Resolutions: **15 min** is the raw data; **hourly** is the mean of the four
quarter hours of each hour (the market's default step, 24 per day); **daily** is
the mean of all 96 values of a day.

## 2. The classes at a glance

Grouped as in SimBench's own overview (Meinecke et al., 2020, Figures 1 and 8); the
Studio classifies every profile by its name (`studio/adapters/profile_classes.py`).

| Group | Class | Names | Profiles | P / Q | Mean factor | Section |
|---|---|---|---|---|---|---|
| Load, accumulated | Households | `H0-A` … `H0-L` | 6 | P, Q | 0.19 | [§3](#households-h0) |
| | Commercial | `G0-A` … `G6-A` | 15 | P, Q | 0.35 | [§3](#commercial-g0g6) |
| | Agricultural | `L0-A`, `L1-A`, `L2-A`, `L2-M` | 4 | P, Q | 0.31 | [§3](#agricultural-l0l2) |
| | Other standard profiles | `BL-H`, `WB-H` | 2 | P, Q | 0.52 | [§3](#other-bl-h-wb-h) |
| Load, individual | Heat pumps | `Air_…`, `Soil_…` | 8 | P, Q | 0.10 | [§4](#heat-pumps) |
| | Electric vehicles | `HLS_…`, `APLS_…` | 15 | P, Q | 0.01 | [§4](#electric-vehicles) |
| Generation | PV | `PV1` … `PV8` | 8 | P | 0.07 | [§5](#pv-wind-biomass-hydro) |
| | Wind | `WP1` … `WP12` | 12 | P | 0.36 | [§5](#pv-wind-biomass-hydro) |
| | Biomass | `BM1` … `BM5` | 5 | P | 0.33 | [§5](#pv-wind-biomass-hydro) |
| | Hydro | `Hydro1` … `Hydro3` | 3 | P | 0.29 | [§5](#pv-wind-biomass-hydro) |
| | Conventional plants | `pp_1` … | 318 | P | 0.22 | [§5](#power-plants-and-imports) |
| Storage | Storage | `Storage_PV…_…` | 0 (scenario 0), 60 (scenarios 1, 2) | P | 0.10 | [§6](#6-storage) |
| Aggregated grids | SimBench grids, load | `lv_…`, `mv_…`, `hv_…` | 16 | P, Q | 0.18 | [§7](#7-aggregated-grids) |
| | SimBench grids, generation | `lv_…`, `mv_…`, `hv_…` | 14 | P | 0.15 | [§7](#7-aggregated-grids) |
| | Omitted HV grids | `HS0` … `HS27`, `HSexp0/1` | 30 | P, Q | 0.53 | [§7](#7-aggregated-grids) |
| | Import | `imp0`, `imp1` | 2 | P | 0.39 | [§5](#power-plants-and-imports) |

The whole catalogue has **458 profiles in scenario 0** and **518 in scenarios 1
and 2**: the difference is the 60 storage profiles.

## 3. Accumulated consumers: households, businesses, farms

Accumulated consumers are many similar customers that are planned with a
**standard load profile** (SLP), the German utilities' typical-day curves: H0
households, G0–G6 businesses, L0–L2 farms, B0 band load (§3.5.1). SimBench replaces
each SLP by a **real measured time series** that matches it, so the profiles keep
the randomness of real customers.

How the series were chosen:

1. **Data.** Businesses and farms: 2,539 anonymised 15-minute measurements of 2016
   (customers with a power meter, mostly under 100,000 kWh a year), after removing
   faulty files (~10 %) and series with cos φ < 0.8 (~14 %). Households: the IZES
   data set (HTW Berlin, 2010), resampled to 15 minutes by taking every 15th value
   instead of averaging, so the short-term peaks stay.
2. **Average week.** Each series is averaged to one week (each weekday over the
   year, seasons ignored) and normalised to the week's mean.
3. **Matching.** The distance to every SLP is the cumulative Euclidean distance
   (load and time) between the points of the two curves. A series is assigned to
   the SLP it is closest to, if it is not as close to another one.
4. **Size classes.** By mean consumption per 15 minutes: 0–4 kWh for LV, 10–20 kWh
   for MV (318 series, 12.5 %), above 100 kWh for HV (17 series, 0.7 %).

The **suffix** after the dash is the consumption level and size class: `-A`, `-B`,
`-C` … are different low-consumption series of the same class (LV), `-M` medium
(MV), `-H` high (HV).

### Households (H0)

`H0-A`, `H0-B`, `H0-C`: the three household series closest to H0 (§4.1.5,
Figure 4.15). `H0-G` and `H0-L`: households that match the business profile G6 and
the farm profile L1 better than H0. They were kept on purpose, so the set covers
the spread of real households: many real households use much more at weekends than
H0 assumes. `H0-H`: an HV-size industrial customer whose shape resembles H0 (high
base load, even rise over the week).

### Commercial (G0–G6)

G for *Gewerbe*. SLP meaning: G0 business in general, G1 weekdays 8–18 h, G2
mainly evening, G3 continuous, G4 shops and hairdressers, G5 bakeries, G6 weekend
business. Series: `G0-A`, `G0-M`, `G1-A`, `G1-B`, `G1-C`, `G2-A`, `G3-A`, `G3-M`,
`G3-H`, `G4-A`, `G4-B`, `G4-M`, `G4-H`, `G5-A`, `G6-A`.

G0 is itself a mix of the other G profiles, so no real customer is "G0"; a
measured series is supplied anyway because grid operators often use G0 for all
businesses. Most measured business series matched G1 (over 20 % of the data).

### Agricultural (L0–L2)

L for *Landwirtschaft*: L0 farms in general, L1 farms with dairy, L2 other farms.
Series: `L0-A`, `L1-A`, `L2-A`, `L2-M`. Farm profiles have an even demand over the
week with high morning and evening peaks, which is also why many measured
households matched them.

### Other (BL-H, WB-H)

Two HV-size series with an almost constant demand ("band load"). They matched B0
and L2 only loosely and are listed as "other".

## 4. Individual consumers: heat pumps and electric vehicles

One device each, simulated bottom-up rather than measured (§3.5.2). Both use a
fixed lagging power factor cos φ = 0.93, since the models give no reactive power.

### Heat pumps

The electrical demand of a heat pump that heats a three-person single-family house
in Hanover or Lübeck (heat demand of 2016 with 2011 weather, so it correlates with
the PV and wind series).

| Name | Heat source and operation |
|---|---|
| `Air_Parallel_1/2` | Air source. Below −2 °C the pump and a backup heater run together |
| `Air_Alternative_1/2` | Air source. Below −2 °C the pump stops and the heater covers everything |
| `Air_Semi-Parallel_1/2` | Air source. Both run between −2 °C and −5 °C; below −5 °C only the heater |
| `Soil_Alternative_1/2` | Ground source (probe), soil at a constant 7 °C. The documentation describes only parallel operation for ground-source pumps; the data names it "Alternative" |

`_1` and `_2` are the two cities. How the series behave:

- **Lockout periods.** The utility blocks heat pumps every day 07:45–09:30,
  11:30–12:30 and 16:45–19:00: the profile is 0 then, and catches up afterwards.
- **Storage.** A hot-water tank (8.7 kWh) and a space-heating tank (11–14 kWh) are
  charged when either falls below 50 % and filled to 100 %; hot water first.
- **Efficiency.** COP = 0.36 · Carnot COP, flow temperature 55 °C.
- **Size.** Pumps of 3.8–4.9 kW with heaters of 0.5–10.7 kW; in the grids, heat pumps
  of 2–30 kW use these profiles (larger ones at MV).

### Electric vehicles

Charging power at one charging point, from a bottom-up simulation of drivers
(§3.5.2, §4.1.5): car model, battery (20–100 kWh) and consumption (15 or
25 kWh/100 km) drawn from the German fleet, measured charging curves of ten EV
models, and trips from the survey *Mobilität in Deutschland* (number of trips,
arrival times, purpose, distance, speed). A car charges with 80 % probability if
it parks over three hours (20 % otherwise), always below 20 % state of charge.

| Name | Charging point | Power |
|---|---|---|
| `HLS_A_3.7`, `HLS_B_3.7`, `HLS_C_3.7` | at home (*Heimladestation*) | 3.7 kW |
| `HLS_A_11.0`, `HLS_B_11.0` | at home | 11 kW |
| `HLS_A_22.0` | at home | 22 kW |
| `APLS_A_3.7`, `APLS_B_3.7` | at work (*Arbeitsplatzladestation*) | 3.7 kW |
| `APLS_A_11.0`, `APLS_B_11.0` | at work | 11 kW |
| `APLS_A_22.0` | at work | 22 kW |
| `APLS_A_50.0` | at work | 50 kW |
| `APLS_0.1014`, `APLS_0.5202`, `APLS_0.033` | aggregated workplace charging for MV grids (name: nominal power in MW) | e.g. 101.4 kW, the sum of the LV workplace series; ×5 for large companies |

The single-point series are normalised to a maximum of 1. The aggregated ones are
not, because all chargers never run at once. With a **mean factor of 0.01**, an
EV charger draws its full power only for short times: these are the most "peaky"
profiles in SimBench.

## 5. Generation

### PV, wind, biomass, hydro

PV, wind and biomass series were simulated with SIMONA, an agent-based grid
simulation of the TU Dortmund, from weather data of the German Weather Service for
2011 and 2012 (§3.5.4). Plant sites follow the HV grids, so a wind farm in an HV
grid gets the weather of its region. Hydro series are real, anonymised plant data
of 2017. All are normalised to the plant's rating and have **no reactive power**:
reactive power depends on how a plant is controlled, which SimBench leaves to the
user (the study cases assume cos φ = 1).

| Name | Site | PV orientation |
|---|---|---|
| `PV1` | Hanover (site 3) | east |
| `PV2` | Lübeck (site 1) | east |
| `PV3` | Hanover (site 1) | south |
| `PV4` | Hanover (site 2) | south |
| `PV5` | Lübeck (site 2) | south |
| `PV6` | Lübeck (site 3) | south |
| `PV7` | Hanover (site 2) | west |
| `PV8` | Lübeck (site 2) | west |
| `WP1`, `WP2` | Baltic Sea, North Sea (offshore) | |
| `WP3`, `WP9`, `WP6` | Baltic coast, North Sea coast, East Germany | |
| `WP4`, `WP7`, `WP10` | east, north and south of HV grid 1 | |
| `WP5`, `WP8`, `WP11` | east, north and south of HV grid 2 | |
| `WP12` | (not listed in the documentation's table) | |
| `BM1` … `BM5` | biomass plants: almost constant output (mean factor 0.33) | |
| `Hydro1` … `Hydro3` | run-of-river plants | |

For a local market at LV, **PV is the generation that matters**: it is the only
generation SimBench connects at LV. Its mean factor of 0.07 means a 10 kW system
yields on average 0.7 kW, concentrated around noon and in summer.

### Power plants and imports

Only in the EHV grids: `pp_1` … `pp_318`, one profile per conventional power plant
(many are constant), and `imp0`, `imp1`, generators at the border that stand for
power from neighbouring countries.

## 6. Storage

SimBench models two kinds of batteries (§3.5.5, §4.1.5):

- **PV batteries** that maximise self-consumption: the PV series is coupled to a
  household or business series; surplus PV charges the battery, a deficit
  discharges it. PV size = household energy × 0.00071 /h; the battery is large
  enough to store any surplus; charge and discharge efficiency 0.95; self-discharge
  4 % per month.
- **Grid-beneficial batteries** next to wind and PV plants that store the top 3 %
  of the plant's energy (a fixed power limit above which the feed-in is stored).

The profile is the battery's power at its bus **as if only the PV system and the
battery were connected**; the household's own load is a separate element. Only the
batteries actually installed in a grid have a profile, named after the series they
combine: `Storage_PV3_H0-A` is a battery with PV3 next to an H0-A household.

**Scenario 0 ships no storage profiles**: batteries only appear in the future
scenarios, which have 60 of them.

## 7. Aggregated grids

Where a network connects a whole grid of the level below as one element, that
element follows the summed time series of the grid it stands for (§3.5.3,
§4.1.5):

- **`lv_…`, `mv_…`, `hv_…` (bottom-up).** A year-long power flow of each SimBench
  grid, recorded at its slack: `lv_rural1` is the total load (or generation) of LV
  rural 1, used by an MV network's loads. Load versions have P and Q; generation
  versions P only. `mv_add1`, `mv_add2` are further MV grids.
- **`HS0` … `HS27`, `HSexp0`, `HSexp1` (top-down).** The EHV grid covers all of
  Germany, but only some HV grids are modelled. The rest come from Germany's total
  demand (ENTSO-E), split into households (by population, H0), farms (2 % of
  demand, by farmland, L0), businesses (by employees and area, G0) and industry and
  transport (the remainder), assigned to EHV/HV nodes by Voronoi areas and reduced
  to 28 representative series by k-means. `exp` marks the two series for nodes
  outside Germany. cos φ = 0.93.

For a local market these matter only as the background of MV and higher networks:
an MV load called `lv_semiurb4` is a whole neighbourhood, not a prosumer.

## 8. Where the data differs from the documentation

Found while writing this page, by comparing the documentation (v1.1.0) with the
profiles the `simbench` package ships. The data is what the Studio uses.

| Topic | Documentation says | Data has |
|---|---|---|
| Ground-source heat pumps | only parallel operation (§3.5.2) | profiles named `Soil_Alternative_1/2` |
| Wind profiles | table of sites lists `WP1` … `WP11` (Table 4.7) | 12 profiles, `WP1` … `WP12` |
| Feed-in scale | "normalised to one" (§4.1.5) | factors of rated power: PV peaks at 0.63, not 1 |
| Aggregated grid profiles | "normalised to one" (§4.1.5) | peaks of 0.95 (load) and 0.92 (generation) |
| Storage profiles | active and reactive power series (§4.1.5) | active power only |
| Storage profiles per scenario | — | none in scenario 0; 60 in scenarios 1 and 2 |

The documentation's wording "normalised to one" most likely means "relative to the
rated power", which the data follows; the other rows are open.
