# MARLEM validation and fix plan

## Purpose and audit scope

This is the concrete remediation plan for the current MARLEM repository. It is intended to support a thesis account of what was inherited, what is unreliable, how each issue affects the system, and how the corrected implementation will be validated.

The audit covers the working tree on 2026-08-08 at `HEAD 04b6be1`, including `src/`, `tests/`, `notebooks/`, `examples/`, configuration/packaging files, and user-facing documentation. It combines static inspection with targeted execution checks. It is comprehensive for the code currently present, but it is not a claim that no further defect can be found after the model is specified more precisely.

Audit-time executable evidence (2026-08-08, before the fixes below):

- `pytest -q` collects 35 tests but reports **15 passed, 3 failed, and 17 errors**.
- The test files contain no `assert` statement or `pytest.raises` check.
- A deterministic environment probe with `max_steps=24` executes **23 transitions**, leaves `current_step=23`, and returns post-clearing order quantities of zero.
- With the supplied reset path and one seed, identically configured agents receive identical generation profiles, demand profiles, reputations, and initial balances.
- Agent `profit` remains zero after settlement.

Current acceptance evidence (2026-08-25): `pytest -q` passes 90 focused P0-P3 regression tests, and case notebooks 1–7 execute from fresh kernels under their documented safe defaults with runtime output checked for actual success/failure counts. The empirical study requirements in P2-01/P2-06 are documented external blockers rather than unimplemented code work.

## Severity and evidence conventions

- **P0 — correctness blocker:** invalidates state transitions, settlement, rewards, learning, or the ability to verify the system. Fix before using any experiment result.
- **P1 — model-validity blocker:** the code runs, but the implemented quantity does not support the physical, economic, or coordination claim attached to it.
- **P2 — experimental-validity blocker:** prevents reproducible training, fair evaluation, generalisation claims, or exact reconstruction of a run.
- **P3 — maintenance/documentation defect:** does not by itself invalidate an experiment, but increases error risk or misrepresents repository capabilities.

Evidence labels used below:

- **Confirmed defect:** the implementation contradicts its own interface or a required invariant.
- **Model-definition gap:** more than one convention is possible, but the convention is absent or the current label overstates the model.
- **Reproducibility gap:** the run cannot be independently reconstructed or compared fairly.

## Issue tracker convention

Each issue has an independent tracker. Use one of these status values: `Open`, `In progress`, `Blocked`, `Fixed ? pending validation`, `Done`, or `Not applicable`. An issue is only `Done` when its implementation and verification are complete and its effect on the thesis has been recorded. Replace `TBD` with links or identifiers for the relevant commit, test, experiment artifact, or thesis section.

## P0 — correctness blockers

### P0-01. Bought and sold energy have reversed signs in the DER balance

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed - pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The one-balance settlement convention is documented in `model-contract.md`; focused battery trade-balance and source/delivered/loss conservation regressions pass in the acceptance gate.

**Evidence and location:** `DERAgent.update_battery_from_trades` defines `net_trade_energy = energy_sold - energy_bought` and adds it to generation minus demand ([src/agent/der.py:L293-L305](../src/agent/der.py#L293-L305)). The environment passes positive bought and sold totals into that method ([src/environment/lem.py:L391-L411](../src/environment/lem.py#L391-L411)). Consequently, buying creates a larger deficit and selling creates a larger surplus.

**Paper correspondence:** The [MARLEM paper](marlem.pdf), Section 3.4.1, Equation (9), defines the agent balance as `generation - demand + bought - sold`; Section 3.5.3, Equation (16), uses the same sign convention for grid balance. The implementation therefore directly reverses the paper's bought/sold terms. An accessible copy is available in the [official arXiv HTML](https://arxiv.org/html/2602.16063).

**Affected system:** battery SOC, demand satisfaction, storage arbitrage, agent balance, reward inputs, battery case studies, and every energy-conservation result.

**Minimal fix:** adopt one balance equation and use it everywhere:

```text
net_energy = generation + delivered_purchases - demand - source_sales
```

Do not update demand, storage, and accounting in separate ad hoc equations. Compute one per-agent settlement record and apply it once.

**Validation:** golden tests for no trade, pure buy, pure sell, self-balanced generation/demand, and a buy/sell round trip. Assert per-step and per-episode energy conservation.

### P0-02. Action feasibility is derived from the requested action, not the physical state

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Focused physical surplus, deficit, and infeasible-direction tests verify signed quantities are capped by current generation/demand state and permit zero/no-order actions.

**Evidence and location:** buy feasibility calculates `quantity - current_generation`; sell feasibility calculates `quantity - current_demand` ([src/agent/der.py:L192-L228](../src/agent/der.py#L192-L228)). These equations omit the actual `generation - demand` net position. The final clamp forces at least `market_config.min_quantity`, even when zero is the only feasible action ([src/agent/der.py:L230-L234](../src/agent/der.py#L230-L234)). The environment applies another quantity clamp afterward ([src/environment/lem.py:L350-L357](../src/environment/lem.py#L350-L357)).

**Paper correspondence:** The [MARLEM paper](marlem.pdf), Sections 3.2.3 and 3.4.2, states that requested quantities are constrained by the physical state and defines maximum sellable and buyable quantities from generation-demand surplus/deficit and battery availability in Equations (11a)-(11d). This is a direct specification-to-code mismatch.

**Affected system:** order quantities, battery dispatch, unmet demand, curtailment, DSO fallback volume, market clearing, and policy rewards.

**Minimal fix:** separate `requested_quantity`, `physically_available_quantity`, and `settled_quantity`. Determine a household's net deficit/surplus from generation, demand, and feasible battery movement; cap the request to that amount; allow zero and submit no order when it is below the market minimum.

**Validation:** hand-calculated cases with and without a battery. For example, generation 10 and demand 5 permits at most 5 units sold, while generation 0 and demand 5 permits at most 5 units bought.

### P0-03. Direction and partner decisions do not match the policy's declared action space

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The model contract defines `[price, signed_quantity]`; focused action-feasibility and declared-agent-order tests verify the policy action is interpreted consistently without learned partner selection.

**Evidence and location:** price, quantity, direction, and partner are all declared as one continuous `Box` ([src/environment/action.py:L34-L44](../src/environment/action.py#L34-L44)). Battery adjustment treats any non-zero direction as true ([src/agent/der.py:L183-L196](../src/agent/der.py#L183-L196)), whereas the environment later uses a 0.5 threshold ([src/environment/lem.py:L335-L359](../src/environment/lem.py#L335-L359)). Partner selection truncates a continuous float to an integer ([src/environment/lem.py:L358-L359](../src/environment/lem.py#L358-L359)). Before any external clipping, the “no preference” mapping is reached only at the exact upper endpoint, so its probability depends on clipping behavior rather than categorical semantics; self-selection is also allowed ([src/environment/action.py:L68-L88](../src/environment/action.py#L68-L88)). CTDE then models every component with diagonal Gaussians ([src/environment/ctde.py:L366-L383](../src/environment/ctde.py#L366-L383)).

**Paper correspondence:** The [MARLEM paper](marlem.pdf), Section 3.2.3, Equation (1), calls the action a continuous vector while simultaneously defining direction `alpha` as binary and partner `beta` as a discrete index. The paper therefore documents the intended components but also contains the mixed continuous/discrete formulation that causes this issue; it is not a complete corrective specification.

**Affected system:** executed actions, policy log-probabilities, exploration, entropy, PPO/APPO/SAC comparisons, partner preference, CTDE, CTCE, and inference.

**Minimal fix:** keep an algorithm-friendly continuous action without pretending discrete values are Gaussian. The simplest baseline is `[price, signed_quantity]`: sign means buy/sell and magnitude means quantity. Remove learned partner selection initially and use deterministic price-time matching. Add partner choice later only if it is a research variable and the chosen algorithms support a categorical component.

**Validation:** assert that the action used for feasibility, matching, logging, and reward is exactly the action whose probability the policy computes. Test zero, both signs, bounds, and no-order behavior.

### P0-04. Matching mutates submitted orders before reward calculation and destroys the audit trail

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The immutable-order regression verifies matching fills trades without changing submitted quantities; trade/order provenance is retained in matching results.

**Evidence and location:** the matcher subtracts fills directly from the input `Order.quantity` ([src/market/matching.py:L346-L354](../src/market/matching.py#L346-L354), [src/market/matching.py:L525-L554](../src/market/matching.py#L525-L554)), and DSO fallback assigns the remaining quantity to zero ([src/market/dso.py:L213-L253](../src/market/dso.py#L213-L253)). The same `Order` objects are then passed to reward code ([src/environment/lem.py:L413-L430](../src/environment/lem.py#L413-L430)) and stored in `info` ([src/environment/lem.py:L468-L476](../src/environment/lem.py#L468-L476)). Reward components divide by `order.quantity`, returning zero when the now-mutated quantity is zero ([src/environment/reward.py:L248-L249](../src/environment/reward.py#L248-L249), [src/environment/reward.py:L360-L363](../src/environment/reward.py#L360-L363), [src/environment/reward.py:L406-L409](../src/environment/reward.py#L406-L409)). The execution probe confirmed all stored order quantities were zero after the first step.

**Paper correspondence:** Algorithm 1 and Section 3.9 of the [MARLEM paper](marlem.pdf) treat submitted orders, executed trades, and subsequent state/KPI/reward updates as distinct phases. In particular, the executed-trade set is the clearing output consumed by later updates. Mutating the only submitted-order record destroys information required by the paper's stated workflow, although the paper does not prescribe a concrete immutable data model.

**Affected system:** trading reward, resource-allocation reward, execution ratios, reputation, order analytics, debugging, and reproducible settlement records.

**Minimal fix:** make submitted orders immutable, or copy them before matching. Track `submitted_quantity`, `remaining_quantity`, and fills separately. Pass the immutable submitted order plus fills to reward and analytics.

**Validation:** submit a known order, partially fill it, and assert that the original quantity is unchanged, remaining quantity is correct, fills sum correctly, and the execution ratio equals `filled/submitted`.

### P0-05. Two advertised pricing mechanisms receive the wrong arguments

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Golden pricing regression checks buyer, seller, midpoint, bid-ask factor, and proportional-surplus prices through the named buy/sell interface.

**Evidence and location:** the matcher always calls `calculate_price(buy_order, sell_order, market_price)` ([src/market/matching.py:L309-L312](../src/market/matching.py#L309-L312)). `SellerPricing` accepts its first positional argument as `sell_order`, so it returns the buyer's bid instead of the seller's ask ([src/market/mechanism.py:L69-L84](../src/market/mechanism.py#L69-L84)). `BidAskSpreadPricing` accepts the third positional argument as `factor`, so the current market price becomes the interpolation factor and is clipped to `[0,1]` ([src/market/mechanism.py:L87-L111](../src/market/mechanism.py#L87-L111)). Average pricing and symmetric Nash bargaining are also identical under the current definitions ([src/market/mechanism.py:L31-L48](../src/market/mechanism.py#L31-L48), [src/market/mechanism.py:L114-L148](../src/market/mechanism.py#L114-L148)).

**Paper correspondence:** Section 3.3.3 of the [MARLEM paper](marlem.pdf) defines seller pricing as the seller's bid, buyer pricing as the buyer's offer, and gives the average and Nash formulas in Equations (5) and (6). The seller-argument behavior directly contradicts that description. Equations (5) and (6) are algebraically identical in the paper itself, so the duplicate average/Nash mechanisms are a specification-level issue rather than solely an implementation regression.

**Affected system:** market-mechanism case study, clearing price, welfare/reward, DSO comparison, and any claim that six distinct mechanisms were compared.

**Minimal fix:** give every mechanism one typed interface, for example `calculate_price(buy_order, sell_order, reference_price=None, factor=None)`, and call it with keywords. Either remove mathematically duplicate mechanisms from comparisons or explicitly label them as equivalent controls.

**Validation:** for a bid of 120 and ask of 80, assert buyer pricing=120, seller pricing=80, midpoint=100, bid–ask factor 0.25=90, and proportional pricing matches a hand calculation.

### P0-06. Battery boundary and efficiency equations are inconsistent

**Classification:** Confirmed defect plus model-definition gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Focused battery regressions verify exact bound clipping, charge/discharge efficiency, and source/delivered/loss energy accounting; units are recorded in the model contract.

**Evidence and location:** exact transitions to maximum/minimum SOC and all oversized requests are rejected by `>=` and `<=` checks ([src/agent/battery.py:L95-L126](../src/agent/battery.py#L95-L126)). Charging first limits input by storage headroom and only then applies efficiency ([src/agent/battery.py:L131-L148](../src/agent/battery.py#L131-L148)). Discharging multiplies the request by efficiency and subtracts only the delivered amount from stored energy ([src/agent/battery.py:L158-L176](../src/agent/battery.py#L158-L176)), which is inconsistent if the request is external delivered energy. No timestep or charge/discharge power limit is represented. Documentation alternates between kWh and Wh ([src/agent/battery.py:L23-L38](../src/agent/battery.py#L23-L38), [src/agent/battery.py:L131-L176](../src/agent/battery.py#L131-L176)).

**Paper correspondence:** Section 3.4.3, Equation (12), of the [MARLEM paper](marlem.pdf) specifies `stored increase = E_in * charge_efficiency` and `stored decrease = E_out / discharge_efficiency`, clipped at the SOC limits. The same section also claims enforcement of maximum charge/discharge rates. The code's discharge equation and boundary rejection conflict directly with Equation (12), while the missing rate/timestep definition remains an ambiguity in the paper itself.

**Affected system:** SOC trajectories, losses, arbitrage, storage capacity, terminal energy, and comparisons across temporal resolution.

**Minimal fix:** define SOC as internal kWh, define charge requests at the grid side and discharge results at the grid side, clip rather than reject oversized requests, allow exact bounds, and add a per-step power limit multiplied by `delta_t`. Preserve a configurable or fixed initial SOC rather than randomising it implicitly.

**Validation:** equation-level tests for zero, exact bounds, oversized requests, both efficiencies, and round-trip loss. Assert `input = stored_change + charge_loss` and `removed_from_storage = delivered + discharge_loss`.

### P0-07. Episode termination executes `N-1` transitions and never reaches the intended terminal reward

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Horizon regressions verify that a configured horizon executes exactly that many transitions, including the one-step terminal case.

**Evidence and location:** rewards test the terminal flag before incrementing the step ([src/environment/lem.py:L424-L435](../src/environment/lem.py#L424-L435)); termination then fires when the incremented step is `>= max_steps - 1` ([src/environment/lem.py:L443-L453](../src/environment/lem.py#L443-L453)). A 24-step probe executed 23 transitions. The last executed pre-increment index is 22, so `is_terminal` is false and the terminal unmet-demand penalty at [src/environment/reward.py:L204-L214](../src/environment/reward.py#L204-L214) is skipped. Simply changing the comparator would make the observation update index `N` ([src/environment/lem.py:L478-L483](../src/environment/lem.py#L478-L483); [src/environment/observation.py:L334-L342](../src/environment/observation.py#L334-L342)).

**Paper correspondence:** Algorithm 1 and Section 3.9, phase 8, of the [MARLEM paper](marlem.pdf) define trading periods `t in {1, ..., tau}` and termination after reaching the maximum number `tau`. A configured 24-period experiment is therefore intended to execute 24 market transitions, not 23.

**Affected system:** episode return, final profile value, terminal SOC/demand penalties, replay length, training batches, and every 24-hour result.

**Minimal fix:** define `max_steps` as the number of transitions. Execute indices `0..N-1`, compute the terminal reward on index `N-1`, and return a valid terminal observation without indexing profile element `N`.

**Validation:** exact transition-count tests for horizons 1, 2, 4, and 24; assert every profile element is consumed once and the terminal penalty is applied once.

### P0-08. Reset reseeding makes agents identical and overwrites configured profiles

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Reset regressions verify configured profiles remain intact and distinct agent state is not collapsed by reseeding; exact replay is covered in the P2 profile tests.

**Evidence and location:** the environment and component resets repeatedly call global `np.random.seed` ([src/environment/lem.py:L271-L293](../src/environment/lem.py#L271-L293), [src/agent/der.py:L74-L109](../src/agent/der.py#L74-L109), [src/agent/battery.py:L54-L64](../src/agent/battery.py#L54-L64), [src/profile/base.py:L17-L29](../src/profile/base.py#L17-L29), [src/market/reputation.py:L60-L68](../src/market/reputation.py#L60-L68)). Every DER profile is regenerated on reset, even if explicit profiles were supplied ([src/environment/lem.py:L281-L293](../src/environment/lem.py#L281-L293)). `agent.reset` reseeds at the end of one agent's reset, causing the next identically configured agent to start from the same random stream. It also initializes `agent.balance` as an unrelated random value rather than a physical or settled balance ([src/agent/der.py:L99-L109](../src/agent/der.py#L99-L109)). The probe confirmed identical profiles, reputations, and balances across all three agents.

**Paper correspondence:** Sections 3.1 and 3.4.4 of the [MARLEM paper](marlem.pdf) describe agents as having unique generation/demand profiles and distinguish external-file profiles from procedurally generated stochastic profiles. Replacing supplied profiles and making nominally distinct agents identical contradicts that intended heterogeneity, although the paper does not define a seed-stream protocol.

**Affected system:** agent heterogeneity, measured-data replay, stochastic independence, statistical significance, training exploration, and scenario identity.

**Minimal fix:** create a master `numpy.random.Generator` per environment and derive stable child generators from `(episode_seed, component, agent_id)`. Add an explicit `profile_mode` with `replay` and `generate`; never replace supplied replay profiles.

**Validation:** same seed reproduces the complete episode, different agent IDs are not identical unless configured so, different seeds change stochastic fields, and replay mode preserves exact input arrays.

### P0-09. CTDE trains one actor and executes different, untrained actors

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** CTDE initialization raises a clear error until a verified local-actor training path exists. The focused regression and acceptance gate pass; DTDE and CTCE remain the available baselines.

**Evidence and location:** training uses the centralized `pi_encoder` and `pi` ([src/environment/ctde.py:L46-L49](../src/environment/ctde.py#L46-L49), [src/environment/ctde.py:L107-L128](../src/environment/ctde.py#L107-L128)), while rollout, exploration, and inference use independent `pi_heads` ([src/environment/ctde.py:L51-L56](../src/environment/ctde.py#L51-L56), [src/environment/ctde.py:L73-L104](../src/environment/ctde.py#L73-L104)). Target copies of local heads are created ([src/environment/ctde.py:L216-L233](../src/environment/ctde.py#L216-L233)), but that does not put the local heads in the actor loss.

**Paper correspondence:** Section 3.7.1 of the [MARLEM paper](marlem.pdf) defines CTDE as centrally training the agent policies with global information and then executing those trained policies independently from local observations. Executing separate actor heads that did not receive the actor loss directly violates this definition.

**Affected system:** every CTDE checkpoint, CTDE actions, comparison with DTDE/CTCE, and the thesis claim of centralized training with decentralized execution.

**Minimal fix:** disable CTDE experiments until one valid design is implemented. The smallest valid implementation is local actors trained from local observations with a centralized critic; do not maintain a separate centralized actor unless it is explicitly distilled into the local actors.

**Validation:** after one real learner update, assert that every executed actor's parameters and outputs changed, while the critic consumed centralized information. Add a tiny cooperative game with a known learnable solution.

### P0-10. Grouped observations/actions can be assigned to the wrong agents

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Grouped-space regression verifies tuple order follows the declared immutable agent order.

**Evidence and location:** the base environment exposes active agents as a `set` ([src/environment/lem.py:L69-L74](../src/environment/lem.py#L69-L74)). The grouped environment uses `env.agents_id` order for grouping ([src/environment/train.py:L635-L648](../src/environment/train.py#L635-L648)) and packs dictionary values in insertion order ([src/environment/train.py:L668-L684](../src/environment/train.py#L668-L684)). Its helper independently sorts dictionary keys when constructing tuple spaces ([src/environment/train.py:L688-L707](../src/environment/train.py#L688-L707)). If agent IDs are not already lexicographically ordered, tuple elements and their declared spaces refer to different agents. CTDE heads also enumerate the configured agent order ([src/environment/ctde.py:L51-L56](../src/environment/ctde.py#L51-L56)).

**Paper correspondence:** The Dec-POMDP formulation and Algorithm 1 in the [MARLEM paper](marlem.pdf) associate each observation and action with a specific agent `i`. Misaligning tuple positions with agent identities violates that per-agent mapping, but the paper does not prescribe a concrete ordering mechanism; the immutable `agent_order` requirement is an implementation contract derived from the model.

**Affected system:** CTDE/CTCE observations, actions, policy heads, checkpoint restore, and nontrivial agent identifiers such as `agent_2` and `agent_10`.

**Minimal fix:** create one immutable `agent_order` list and use it for group definitions, tuple spaces, packing, unpacking, modules, and inference. Never infer order from a set or re-sort it later.

**Validation:** use deliberately non-lexicographic IDs with distinct space bounds and observation sentinels; assert round-trip identity for every agent.

### P0-11. There is no conserved cash ledger, and household profit is never updated

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Cash-ledger regression verifies buyer debit, seller credit, fee collection, and zero-sum ledger conservation for a settled trade.

**Evidence and location:** `DERAgent.profit` is initialized and reset ([src/agent/der.py:L59-L62](../src/agent/der.py#L59-L62), [src/agent/der.py:L107-L109](../src/agent/der.py#L107-L109)) but has no update path; observations expose the unchanged value ([src/environment/observation.py:L334-L343](../src/environment/observation.py#L334-L343)). `Trade` stores one price, one source quantity, loss, and fees but no buyer payment or seller receipt ([src/market/order.py:L24-L34](../src/market/order.py#L24-L34)). DSO profit includes tariff trades but not accumulated grid fees ([src/market/dso.py:L255-L263](../src/market/dso.py#L255-L263), [src/market/dso.py:L342-L345](../src/market/dso.py#L342-L345)). The fee calculation leaves `transmission_fee` at zero and can apply a negative same-zone bonus, but no ledger assigns the resulting amount to payer and recipient ([src/market/dso.py:L285-L345](../src/market/dso.py#L285-L345)). The execution probe confirmed all DER profits remained zero after trading.

**Paper correspondence:** Section 3.4.1, Equation (10), of the [MARLEM paper](marlem.pdf) explicitly defines cumulative agent profit as sale receipts minus purchase payments, and Algorithm 1 says executed trades update buyer and seller profit. A permanently unchanged `DERAgent.profit` contradicts both statements. The paper does not fully specify fee payer/recipient accounting, so a conserved settlement ledger is still needed beyond Equation (10).

**Affected system:** economic reward, household profit, consumer/producer surplus, DSO profit, welfare, fee allocation, and individual-rationality claims.

**Minimal fix:** add a settlement ledger derived from immutable fills: buyer debit, seller credit, DSO import/export payment, explicit fee payer/recipient, and per-agent cash balance. Use the ledger—not a price-distance heuristic—as profit.

**Validation:** assert cash conservation for P2P and DSO trades, including fees; reconcile every agent and DSO balance to the sum of ledger entries.

### P0-12. The repository has no functioning correctness test gate

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The focused `test_p[0-3]_*.py` acceptance gate is documented in `docs/tests.md`, passes with the current deterministic regression suite, and is run by `.github/workflows/validation.yml` through Conda dependencies from environment.yml.

**Evidence and location:** current pytest collection fails because functions are treated as tests while requiring undefined fixtures such as `path` and `algo` ([tests/test_checkpoint.py:L16-L54](../tests/test_checkpoint.py#L16-L54), [tests/test_inference.py:L16-L94](../tests/test_inference.py#L16-L94), [tests/test_trainer.py:L18-L24](../tests/test_trainer.py#L18-L24), [tests/test_visualization.py:L29-L631](../tests/test_visualization.py#L29-L631)). Other tests are print-driven demonstrations with broad exception handling, for example [tests/test_battery.py:L13-L62](../tests/test_battery.py#L13-L62), [tests/test_environment.py:L17-L90](../tests/test_environment.py#L17-L90), and [tests/test_reward.py:L22-L224](../tests/test_reward.py#L22-L224). Calls have drifted from production signatures in [tests/test_profile.py:L16-L67](../tests/test_profile.py#L16-L67), [tests/test_reward.py:L22-L204](../tests/test_reward.py#L22-L204), and [tests/test_implicit_cooperation.py:L19-L178](../tests/test_implicit_cooperation.py#L19-L178). No CI workflow exists.

**Affected system:** every proposed fix, regression detection, dependency upgrades, releases, and evidential confidence in thesis results.

**Minimal fix:** first create a small assertion-based invariant suite; rename manual showcases so pytest does not collect them; provide or parametrize required fixtures; then add CI for the locked Python environment. Do not begin with broad snapshot tests.

**Validation:** `pytest -q` must return zero failures/errors, and deliberate mutations of energy signs, horizon, or pricing must make a relevant test fail.

## P1 — model-validity blockers

### P1-01. Source energy, delivered energy, and losses are not conserved in settlement

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Trade records retain source quantity, delivered quantity, and loss separately; focused conservation and DSO-residual regressions pass in the acceptance gate.

**Evidence and location:** a trade records `proposed_quantity` as `Trade.quantity` and loss separately ([src/market/matching.py:L314-L332](../src/market/matching.py#L314-L332)). The seller order is reduced by source quantity but the buyer order only by source minus loss ([src/market/matching.py:L346-L348](../src/market/matching.py#L346-L348)), allowing the loss remainder to be purchased again from the DSO. The environment nevertheless credits the buyer with the full source quantity ([src/environment/lem.py:L397-L411](../src/environment/lem.py#L397-L411)). Loss is computed as distance times source quantity without a cap ([src/grid/network.py:L340-L374](../src/grid/network.py#L340-L374)).

**Paper correspondence:** Section 3.5.2, Equation (14), of the [MARLEM paper](marlem.pdf) defines transmission loss as `distance * traded quantity * loss factor` and states that the loss derates the transported quantity. Crediting the buyer with the full pre-loss source quantity contradicts that statement. The paper does not precisely distinguish source-side from delivered-side `q_ij`, so the explicit two-quantity ledger proposed here also resolves a paper ambiguity.

**Affected system:** energy conservation, buyer delivery, demand satisfaction, DSO volume, market volume, transmission-loss metrics, battery SOC, and payments.

**Minimal fix:** make fills store both `source_quantity` and `delivered_quantity`, with `loss = source - delivered`. Reduce the seller obligation by source and buyer demand by delivered. Settle any remaining buyer demand once, not the physical loss itself.

**Validation:** assert `source = delivered + loss` for each trade and reconcile all source, demand, battery, curtailment, unserved energy, and loss terms per step.

### P1-02. Ordinary price matches bypass the network flow model and do not test projected constraints

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Capacity-flow regressions verify ordinary network settlement rejects overloaded paths and all matching paths use the same abstract graph constraint.

**Evidence and location:** ordinary matching checks only whether the current scalar balance is already beyond `max_quantity * num_agents` ([src/market/matching.py:L158](../src/market/matching.py#L158), [src/market/matching.py:L295-L307](../src/market/matching.py#L295-L307)). It neither evaluates the proposed trade nor uses `grid_network.capacity`. The ordinary branch never calls `update_flow_from_trade`; that call exists only in the preferred-partner path ([src/market/matching.py:L569-L575](../src/market/matching.py#L569-L575)).

**Paper correspondence:** Sections 3.5.2 and 3.5.3 of the [MARLEM paper](marlem.pdf) state that physical constraints apply to all energy transactions, every executed trade updates flow along its shortest path, and capacity-violating trades may be penalized or disallowed. Bypassing projection and flow updates in the ordinary matching path directly conflicts with that design.

**Affected system:** congestion, path utilization, grid fees, matching feasibility, topology comparisons, and all grid analytics.

**Minimal fix:** implement one `can_settle(fill)` check used by every matching path. It should project the fill onto the abstract network, reject or clip it before settlement, and then commit the same projected flow. Use the network's configured capacities only.

**Validation:** the same order pair must have the same network effect whether reached through price matching or preference matching. Add near-capacity and disconnected-path cases.

### P1-03. Grid flows are random, cumulative across time, unsigned, and silently clipped

**Classification:** Confirmed defect plus model-definition gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Focused grid-flow regressions verify per-step reset, signed opposite-flow netting, and overload rejection without clipping.

**Evidence and location:** reset initializes each edge to a random 0–30% utilization without injections ([src/grid/network.py:L54-L85](../src/grid/network.py#L54-L85)). `update_flow_from_trade` only adds positive flow along an undirected path and silently caps it at capacity ([src/grid/network.py:L279-L329](../src/grid/network.py#L279-L329)); there is no per-timestep flow reset, directional netting, rejection, or curtailment record. A missing path is swallowed, while `get_path_congestion` reports a missing path as zero congestion ([src/grid/network.py:L328-L329](../src/grid/network.py#L328-L329), [src/grid/network.py:L376-L403](../src/grid/network.py#L376-L403)). `Location.distance_to` catches every error and substitutes Euclidean distance ([src/grid/base.py:L34-L57](../src/grid/base.py#L34-L57)).

**Paper correspondence:** Section 3.5.3 of the [MARLEM paper](marlem.pdf) says grid state evolves from executed trades by updating the edges on each buyer-seller path and that violations can be disallowed. Equation (15) defines congestion from line flow relative to capacity. The paper does not specify timestep resets, signed flow, baseline injections, or curtailment, so it supports the missing-path and silent-clipping concerns but is not a complete physical-flow specification.

**Affected system:** congestion, capacity utilization, losses, fees, topology, grid stability, and physical-feasibility claims.

**Minimal fix:** explicitly scope the current grid as an abstract capacity graph. Start each timestep from declared baseline flows (zero by default), track signed/net path flow, reject disconnected or overloaded fills, and record curtailment. Do not claim voltage or AC power-flow validity.

**Validation:** opposite flows net correctly, flows do not leak into the next timestep, overloads are observable, and disconnected nodes cannot trade.

### P1-04. The IEEE34 representation is disconnected and its impedances are unused

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The current model contract scopes the grid to an abstract capacity graph; the IEEE34 connectivity regression verifies the representation is connected and does not claim AC impedance validity.

**Evidence and location:** the IEEE34 position map includes nodes 888 and 890, but the edge list contains only `888-890`; it omits the feeder connection `832-888` ([src/grid/config.py:L12-L39](../src/grid/config.py#L12-L39)). The impedance dictionary does contain `832-888` ([src/grid/config.py:L41-L75](../src/grid/config.py#L41-L75)), exposing the inconsistency. Grid construction adds only edge lengths as `weight` and never attaches or uses the impedance table ([src/grid/network.py:L127-L140](../src/grid/network.py#L127-L140)).

**Paper correspondence:** Section 3.5.1 of the [MARLEM paper](marlem.pdf) advertises canonical IEEE 13-node and IEEE 34-node feeders for standardized experiments and defines electrical distance through connected shortest paths. Section 3.5.2 further claims that lower-impedance edges influence capacity. A disconnected feeder and unused impedance table contradict those stated properties.

**Affected system:** IEEE34 connectivity, transformer branch, path distances, agent placement, losses, congestion, and notebook claims of a realistic IEEE feeder.

**Minimal fix:** add the missing edge and a topology connectivity test. If the thesis stays with the abstract graph, remove/ignore impedance claims explicitly; only integrate a validated power-flow library if electrical voltage/impedance analysis is a research requirement.

**Validation:** assert one connected component, expected nodes/edges, reachable paths, and an explicit statement/test of which edge attributes affect calculations.

### P1-05. DSO fallback bypasses grid feasibility and makes unmatched-order metrics degenerate

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** DSO residual regressions verify bounded fallback volume remains visible and DSO trades are rejected when the same network capacity constraint is exceeded.

**Evidence and location:** DSO fallback buys or sells every remaining quantity with zero distance, zero loss, and zero fee ([src/market/dso.py:L213-L253](../src/market/dso.py#L213-L253)). It does not call `validate_grid_constraints`; that validator applies `abs(self.balance + proposed_quantity)` without order direction and examines current rather than projected path congestion ([src/market/dso.py:L347-L390](../src/market/dso.py#L347-L390)). The matcher then forcibly sets `unmatched_orders=[]` ([src/market/matching.py:L356-L382](../src/market/matching.py#L356-L382)).

**Paper correspondence:** Section 3.3.1 of the [MARLEM paper](marlem.pdf) assigns the DSO responsibility for grid stability and grid-usage fees, while Sections 3.5.2-3.5.3 apply losses, paths, and capacity constraints to energy transactions. Unconditionally clearing DSO trades with zero path effects and erasing infeasible residuals does not implement that role. The paper's separate claim that the DSO guarantees complete clearing does not explain how physical infeasibility should be represented.

**Affected system:** DSO volume/profit, feasibility, unserved demand, curtailment, reliability, fallback effectiveness, grid import, and reward.

**Minimal fix:** route DSO fills through the same settlement/constraint function as P2P fills. Preserve any quantity that cannot be served as `unserved_demand` or `curtailed_generation`; do not erase it.

**Validation:** constrain DSO capacity/path availability and assert that infeasible residuals remain visible and all DSO fills satisfy the same ledger and network invariants.

### P1-06. Reward calculation contains bypasses, stale state, duplicated weights, and unnormalised terms

**Classification:** Confirmed defect plus model-definition gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Reward is now a bounded, ledger-derived objective: normalized settlement cash change, unserved demand, delivered-energy loss, and congestion penalty. Focused golden tests cover monotonicity and unit-display invariance.

**Evidence and location:** `_w_local` is assigned 0.7 and later overwritten as 0.3 ([src/environment/reward.py:L79-L93](../src/environment/reward.py#L79-L93)). Agents with no trade return early and skip grid/cooperation/terminal penalties ([src/environment/reward.py:L130-L136](../src/environment/reward.py#L130-L136)). Dimensionful or unbounded KPIs are inverted with `1-x` and averaged as if normalized ([src/environment/reward.py:L168-L192](../src/environment/reward.py#L168-L192)). Terminal penalties are scaled by the magnitude of unrelated base reward ([src/environment/reward.py:L204-L229](../src/environment/reward.py#L204-L229)). Grid contribution uses `agent.balance` before the environment updates it ([src/environment/reward.py:L270-L297](../src/environment/reward.py#L270-L297); [src/environment/lem.py:L424-L441](../src/environment/lem.py#L424-L441)). Within-step price dispersion is labelled stability ([src/environment/reward.py:L435-L446](../src/environment/reward.py#L435-L446)).

**Paper correspondence:** Section 3.2.4, Equation (2), of the [MARLEM paper](marlem.pdf) defines reward as a base term modified by cooperation and individual-contribution factors, followed by DSO and unmet-demand penalties. Section 3.9, phase 5, says rewards are computed after economic and physical outcomes and KPIs are available. Early returns, stale balances, and unnormalised inputs prevent the implementation from representing that stated equation.

**Affected system:** all learned behavior, hyperparameter tuning, checkpoint selection, cooperation claims, and reward comparability across units or community sizes.

**Minimal fix:** after correcting settlement, replace the reward with a small, auditable objective: normalized household cost/profit, unserved-energy penalty, and optional constraint penalty. Keep thesis KPIs out of the training reward initially and report them independently.

**Validation:** monotonic golden tests: more profit improves reward; more unserved energy, loss, or constraint violation worsens it; changing display units does not change policy incentives.

### P1-07. Core coordination KPIs do not implement the quantities named

**Classification:** Confirmed model-validity defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Unsupported KPI labels were removed. The metric contract now defines turnover, trade energy, quote spread, settlement volatility, physical imbalance, congestion, balance score, and local-trade share from recorded inputs; decentralized observations no longer consume global KPI vectors.

**Evidence and location:** “social welfare” is transaction turnover ([src/coordination/implicit_cooperation.py:L90-L94](../src/coordination/implicit_cooperation.py#L90-L94)); bid and ask price lists are reversed ([src/coordination/implicit_cooperation.py:L99-L100](../src/coordination/implicit_cooperation.py#L99-L100)); “supply-demand imbalance” sums positive trade quantities rather than signed physical mismatch ([src/coordination/implicit_cooperation.py:L117-L128](../src/coordination/implicit_cooperation.py#L117-L128)); “coordination convergence” is three-step trading-volume stability ([src/coordination/implicit_cooperation.py:L139-L154](../src/coordination/implicit_cooperation.py#L139-L154)); “DER self-consumption” is local-trade share ([src/coordination/implicit_cooperation.py:L175-L188](../src/coordination/implicit_cooperation.py#L175-L188)); and flexibility combines mutually exclusive buyable and sellable quantities before calculating utilization ([src/coordination/implicit_cooperation.py:L190-L226](../src/coordination/implicit_cooperation.py#L190-L226)). The reported `clearing_price` is a volume-weighted mean of heterogeneous bilateral and DSO settlements rather than one uniform market-clearing price ([src/market/matching.py:L368-L385](../src/market/matching.py#L368-L385)).

**Paper correspondence:** Section 3.6.2, Equations (17)-(23), of the [MARLEM paper](marlem.pdf) is the source of several implemented KPI names and formulas. It also contains conceptual inconsistencies: Equation (17) labels transaction turnover as consumer-plus-producer surplus, and Equation (21) labels P2P volume share as DER self-consumption. The paper should therefore be cited as the origin of these definitions, not as independent evidence that they are valid economic or energy metrics. Equations (19), (20), and (22)-(23) still provide direct intended formulas against which the implementation can be checked.

**Affected system:** observations, cooperation reward, plots, thesis tables, welfare, balance, self-consumption, and flexibility conclusions.

**Minimal fix:** write a metric dictionary before implementation: name, equation, units, required raw inputs, range, aggregation, and interpretation. Rename turnover and local-trade share immediately; implement physical imbalance and self-consumption only from the corrected energy ledger.

**Validation:** hand-calculated no-trade, balanced, import, export, P2P, and DSO cases shared by KPI, observation, reward, and analytics tests.

### P1-08. Analytics report economic, grid, and coordination concepts without the required inputs

**Classification:** Confirmed model-validity defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Market analytics now expose only settlement aggregates with direct ledger/history provenance, and the affected visualizations use literal labels. Unsupported welfare, surplus, allocation, price-discovery, liquidity, and fairness scores were removed.

**Evidence and location:** market analytics define welfare as turnover, split a zero/constructed surplus evenly, equate uniform transaction sizes with allocative efficiency, and equate low price variance with price discovery ([src/analytics/market_analytics.py:L228-L332](../src/analytics/market_analytics.py#L228-L332)). Grid stability includes price volatility; “grid utilization” is P2P share; load factor uses clearing volume; capacity utilization uses only the final cumulative edge state ([src/analytics/grid_metrics.py:L129-L228](../src/analytics/grid_metrics.py#L129-L228)). Grid time-series fields are declared but are not populated by the returned metric object ([src/analytics/grid_metrics.py:L39-L50](../src/analytics/grid_metrics.py#L39-L50), [src/analytics/grid_metrics.py:L72-L110](../src/analytics/grid_metrics.py#L72-L110)). DSO “self-sufficiency” is P2P share and fallback effectiveness counts trades against a deliberately empty unmatched list ([src/analytics/dso_metrics.py:L99-L111](../src/analytics/dso_metrics.py#L99-L111), [src/analytics/dso_metrics.py:L148-L226](../src/analytics/dso_metrics.py#L148-L226)). Coordination analytics infer strategy alignment, information efficiency, battery coordination, peak reduction, and energy-waste reduction from rewards, P2P ratio, price, or grid balance without strategy, information, battery, baseline-load, or curtailed-energy inputs ([src/analytics/coordination_metrics.py:L200-L297](../src/analytics/coordination_metrics.py#L200-L297), [src/analytics/coordination_metrics.py:L381-L459](../src/analytics/coordination_metrics.py#L381-L459), [src/analytics/coordination_metrics.py:L497-L588](../src/analytics/coordination_metrics.py#L497-L588)).

**Paper correspondence:** Sections 3.6.2 and 3.8 of the [MARLEM paper](marlem.pdf) claim that the analytics quantify economic efficiency, grid stability, resource coordination, and coordination effectiveness, and present Equations (17)-(23) as their definitions. These sections establish the meanings being claimed but do not supply several raw variables required to measure those meanings. Some semantic defects therefore originate in the paper, while others are additional unsupported inferences introduced by the analytics code.

**Affected system:** dashboards, case studies, thesis outcome variables, claims of emergence, causality, fairness, grid stability, and efficiency.

**Minimal fix:** retain only metrics directly supported by raw data. Rename proxies literally (for example, `p2p_volume_share` and `transaction_price_cv`). Implement profit, surplus, self-consumption, unserved energy, curtailment, and battery utilization only after their ledgers exist. Remove causal terms such as “impact” unless a controlled comparison estimates them.

**Validation:** every reported metric must have a definition, units/range, a golden test, and a direct provenance path to recorded variables.

### P1-09. Observations mix a false initial state, exact future information, and global/private information

**Classification:** Confirmed defect plus model-definition gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Reset uses current local state, unavailable future totals are zeroed, and the decentralized policy observation no longer exposes peer reputation vectors.

**Evidence and location:** reset observations hard-code generation, demand, remaining energy, profit, and KPIs to zero ([src/environment/observation.py:L195-L251](../src/environment/observation.py#L195-L251)) even though profiles and random balances already exist. Later observations expose exact sums of all future demand and generation and the never-updated profit ([src/environment/observation.py:L334-L343](../src/environment/observation.py#L334-L343); [src/agent/der.py:L338-L363](../src/agent/der.py#L338-L363)). Every agent receives global market/DSO/grid/KPI signals ([src/environment/observation.py:L279-L326](../src/environment/observation.py#L279-L326)) and, when preferences are enabled, every agent's reputation including its own ([src/environment/observation.py:L353-L357](../src/environment/observation.py#L353-L357)).

**Paper correspondence:** Sections 3.2.1 and 3.2.2 of the [MARLEM paper](marlem.pdf) define the problem as a Dec-POMDP, state that the full global state is never visible to one agent, distinguish public market signals from private agent-specific signals, and require the next observation to reflect the updated state. False reset values, exact unavailable future truth, or peer-private data contradict this information model.

**Affected system:** first action, causality, partial observability, decentralization, privacy, forecasting difficulty, and generalisation.

**Minimal fix:** make reset return the real step-0 state. Define separate observation specifications for causal decentralized policies and an oracle/centralized baseline. Replace exact future sums with forecasts only if a forecast is actually available to the simulated agent.

**Validation:** changing future ground truth while holding current state/forecast fixed must not change a decentralized observation. Check every observation against declared bounds on reset and every step.

### P1-10. Reputation scores are structurally degenerate and time weighting freezes updates

**Classification:** Confirmed model-validity defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Matching retains submitted-order and fill provenance; reputation uses quantity fulfilment and quote compliance with fixed smoothing, and omits unsupported grid marginal contribution.

**Evidence and location:** reliability counts trade fragments versus unmatched orders ([src/market/reputation.py:L124-L129](../src/market/reputation.py#L124-L129)), but DSO fallback makes unmatched orders empty and one order may create multiple trades. Fairness measures distance from a volume-weighted average settlement price rather than compliance with an agent's bid/ask ([src/market/reputation.py:L131-L136](../src/market/reputation.py#L131-L136)). Grid contribution is inferred from the final balance rather than a counterfactual marginal effect ([src/market/reputation.py:L138-L153](../src/market/reputation.py#L138-L153)). The update weight on old reputation equals `time_of_day`, so new evidence is almost ignored near episode end ([src/market/reputation.py:L80-L87](../src/market/reputation.py#L80-L87)).

**Paper correspondence:** Section 3.3.4, Equation (8), of the [MARLEM paper](marlem.pdf) defines reputation from reliability, price fairness, and grid contribution, and states that a decay factor gives greater weight to recent behavior. The code's fragment counts, degenerate unmatched set, and increasing weight on old reputation do not implement those stated semantics.

**Affected system:** preferred matching, observations, agent rankings, implicit-cooperation behavior, and fairness/reliability claims.

**Minimal fix:** postpone reputation-dependent matching until immutable orders and residual quantities exist. Then use quantity fulfilment for reliability, bid-compliant settlement for fairness, and a fixed exponential smoothing coefficient. Omit grid contribution unless a marginal calculation is available.

**Validation:** split fills must not inflate reliability; an unfilled residual must reduce it; equivalent settlement outcomes must produce time-independent updates under fixed smoothing.

### P1-11. Units and timestep semantics are inconsistent across the system

**Classification:** Model-definition gap with direct correctness consequences.

**Tracker**

- **Status:** `Fixed - pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The model contract defines kW, kWh, hours, and currency/kWh; `time_step_hours` limits battery power and environment-boundary profile conversion; focused tests reconcile equivalent hourly and 15-minute power profiles without changing energy.

**Evidence and location:** DER capacity is documented as W ([src/agent/der.py:L31-L39](../src/agent/der.py#L31-L39)), grid capacity as kW ([src/grid/network.py:L28-L34](../src/grid/network.py#L28-L34)), battery capacity as kWh ([src/agent/battery.py:L23-L38](../src/agent/battery.py#L23-L38)), and market quantities/prices as Wh and $/Wh ([src/market/matching.py:L33-L36](../src/market/matching.py#L33-L36)). Tests and notebooks variously label the same quantities kW, Wh, kWh, $/Wh, and $/MWh ([tests/utils.py:L61-L68](../tests/utils.py#L61-L68), [notebooks/case1_market_mechanisms.ipynb:L141-L159](../notebooks/case1_market_mechanisms.ipynb#L141-L159)). Synthetic profiles map any number of steps onto exactly 24 hours without an explicit `delta_t` ([src/profile/der.py:L187-L233](../src/profile/der.py#L187-L233), [src/profile/dso.py:L231-L337](../src/profile/dso.py#L231-L337)).

**Paper correspondence:** Section 4.1 of the [MARLEM paper](marlem.pdf) describes a 24-hour cycle, generation/grid capacity in kW, and bid quantities in kWh, but does not define the duration of a trading period or an explicit power-to-energy conversion. The paper therefore confirms the intended unit categories while sharing the missing-timestep ambiguity; it is context for the gap, not a complete unit specification.

**Affected system:** energy conservation, battery behavior, prices, fees, grid capacity, rewards, temporal resolution, and cross-scenario comparison.

**Minimal fix:** choose one internal unit system, preferably kW, kWh, hours, and currency/kWh. Add `timestep_hours`; convert power profiles to step energy exactly once at the environment boundary; store unit metadata with results.

**Validation:** dimensional-analysis tests and equivalent 15-, 30-, and 60-minute versions of the same physical day must reconcile to the same total energy and cost within tolerance.

### P1-12. CTCE is a centralized-information baseline, not a theoretical upper bound

**Classification:** Model-definition gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** CTCE is described as a centralized-information baseline, never an optimizer or upper bound; grouped rewards retain a total in info and train on per-agent mean reward. The focused group-reward regression and acceptance gate pass.

**Evidence and location:** grouped CTCE receives centralized observations but still uses an approximate learned policy. Group reward is the sum of individual rewards ([src/environment/train.py:L676-L686](../src/environment/train.py#L676-L686)), so returns scale with agent count. There is no exact optimizer establishing a true upper bound.

**Paper correspondence:** Sections 3.7.1 and 4.2 of the [MARLEM paper](marlem.pdf) explicitly call CTCE a “theoretical upper bound.” The paper is the source of the claim being corrected here: access to global information and joint actions can make CTCE a useful centralized-information baseline, but an approximate learned policy is not a mathematical upper bound without an exact optimization argument.

**Affected system:** CTCE-versus-DTDE/CTDE conclusions, scalability plots, and any “optimal” or “upper bound” language.

**Minimal fix:** label CTCE a centralized-information baseline and report per-agent-normalized as well as total outcomes. If an upper bound is required, solve a small deterministic instance exactly and use that only for the instance it covers.

**Validation:** compare all modes on identical small scenarios and include a solver/exhaustive optimum only where computationally feasible.

### P1-13. Preference matching and “clearing price” do not define one coherent market design

**Classification:** Model-definition gap with experimental consequences.

**Tracker**

- **Status:** `Fixed - pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** The active matcher uses deterministic price-time priority and does not apply partner/reputation ordering. Its heterogeneous settlement aggregate is explicitly named `volume_weighted_settlement_price`.

**Evidence and location:** preferred-partner matching runs before price-priority matching ([src/market/matching.py:L243-L279](../src/market/matching.py#L243-L279)), so a preference can consume liquidity that a higher-priority bid or lower-priority ask would otherwise receive. The paper explicitly makes social preference senior to price matching, so this ordering is intentional, but the code does not document the allocation consequence locally. P2P transactions can settle at different bilateral mechanism prices, DSO transactions settle at tariffs, and all are combined into one volume-weighted value labelled `clearing_price` ([src/market/matching.py:L309-L336](../src/market/matching.py#L309-L336), [src/market/matching.py:L360-L385](../src/market/matching.py#L360-L385)). Reputation is also inserted into price sorting ahead of timestamp ([src/market/matching.py:L273-L279](../src/market/matching.py#L273-L279)).

**Paper correspondence:** Algorithm 1 and Section 3.3.2 of the [MARLEM paper](marlem.pdf) explicitly prescribe preference matching before the price-based double auction, while Section 3.3.4 defines reputation as a tie-breaker. This resolves the intent question but does not make the rule price-time priority. Section 3.3.3 describes bilateral transaction prices; it does not justify labelling a volume-weighted mixture of heterogeneous P2P and DSO settlements as one uniform `clearing_price`.

**Affected system:** price priority, preference and reputation experiments, interpretation of clearing price, price volatility/fairness, mechanism comparison, and individual rationality.

**Minimal fix:** use a simple price-time-priority baseline with partner preference disabled. Name the reported aggregate `volume_weighted_settlement_price` when transactions are bilateral. Reintroduce preference/reputation priority only as an explicit alternative market rule with a written allocation algorithm.

**Validation:** golden order books must establish price compatibility, priority, partial fills, deterministic tie-breaking, and the exact aggregate price. Run the same order book with each optional priority rule and record the intended difference.

## P2 — experimental-validity blockers

### P2-01. Training evaluation is not a held-out, independently seeded protocol

**Classification:** Reproducibility gap.

**Tracker**

- **Status:** `Blocked`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Same-scenario evaluation is disabled by default. Enabling validation now requires separately declared train/validation scenarios and seeds. `ScenarioSplit` requires non-empty, unique, disjoint train/validation/test IDs and seeds, with a stable split fingerprint; `run_declared_training` starts exactly one independent trainer per declared training seed; and `run_declared_episodes` evaluates only the requested declared phase while appending per-seed records. [The experiment protocol](experiment-protocol.md) documents the required sequence and the bundled-data limitation: its profile columns have no day IDs and its raw tariff pairs violate the feed-in/utility contract. **External blocker:** a scientific multi-seed study requires user-selected valid tariff/day data or authorization for a documented synthetic-tariff benchmark.

**Evidence and location:** evaluation changes exploration behavior but otherwise reuses the training environment configuration ([src/environment/train.py:L275-L294](../src/environment/train.py#L275-L294)). Component resets reuse the configured seed ([src/environment/lem.py:L271-L300](../src/environment/lem.py#L271-L300)), and inference resets without episode-specific seeds ([src/environment/inference.py:L128-L132](../src/environment/inference.py#L128-L132), [src/environment/inference.py:L247-L250](../src/environment/inference.py#L247-L250)). There is no household, day, chronological, or scenario split.

**Paper correspondence:** Sections 4.2 and 5 of the [MARLEM paper](marlem.pdf) state that the reported results use zero-intelligence agents and that full MARL training is deferred to future work. The paper therefore does not provide a held-out MARL evaluation protocol against which this code can be validated; its general reproducibility claims do not substitute for independent train/validation/test splits and seeds.

**Affected system:** validation curves, checkpoint choice, generalisation, overfitting, and comparisons across algorithms.

**Minimal fix:** define scenario manifests with disjoint train/validation/test profile IDs and seed lists. Use validation only for checkpoint selection and run test scenarios once after selection. Report at least three independent training seeds, preferably more if variance is high.

**Validation:** save and compare manifest hashes; assert no profile ID/date/seed overlap; reproduce aggregate results from saved per-episode records.

### P2-02. Standalone inference does not reproduce RLlib's action or information path

**Classification:** Confirmed integration defect.

**Tracker**

- **Status:** `Fixed — pending checkpoint validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Inference restores the full RLlib `Algorithm`, obtains each registered policy module by its explicit agent ID, and samples through that module's registered distribution without hand-built Normal sampling. Shared environment metrics are extracted from the documented per-agent info envelope. Focused tests cover module IDs, info extraction, and cleanup; a one-iteration DTDE PPO train-to-checkpoint-to-inference smoke run passes.

**Evidence and location:** inference restores only RLModule components ([src/environment/inference.py:L86-L104](../src/environment/inference.py#L86-L104)) and manually splits means/log standard deviations, samples a raw Normal, and clips actions ([src/environment/inference.py:L144-L216](../src/environment/inference.py#L144-L216)) instead of using the algorithm's distribution/action connectors. The grouped tensor is manually sliced and depends on the ordering defect above. Metrics are read as top-level `info` fields ([src/environment/inference.py:L218-L235](../src/environment/inference.py#L218-L235)), but the environment returns a dictionary keyed by agents ([src/environment/lem.py:L485-L489](../src/environment/lem.py#L485-L489); [src/environment/train.py:L676-L686](../src/environment/train.py#L676-L686)), so price/volume/grid histories default to zero.

**Paper correspondence:** Section 3.7.1 of the [MARLEM paper](marlem.pdf) defines CTDE inference as execution of the centrally trained decentralized policies using local observations, and Section 3.7.2 describes a managed training-to-checkpoint-to-inference workflow. A separate hand-built sampling and tensor-slicing path cannot be assumed to reproduce the policy behavior described by that workflow.

**Affected system:** restored policy behavior, stochastic/deterministic evaluation, CTDE/CTCE actions, and all inference metrics.

**Minimal fix:** restore the RLlib Algorithm for evaluation and call its supported inference API. If module-only export is required later, build one tested adapter that uses the module's registered distribution and explicit agent order. Read metrics from one documented episode-info location.

**Validation:** for a fixed checkpoint, observation, and seed, Algorithm and standalone inference must produce identical deterministic actions and matching stochastic distributions; recorded info must match environment output.

### P2-03. CSV “measured profiles” are arbitrary, transformed samples rather than replayed data

**Classification:** Confirmed reproducibility/model-validity gap.

**Tracker**

- **Status:** `Fixed - pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Replay preserves named numeric value columns, zero values, timestamps, explicit intervals, and cadence validation without scaling, smoothing, clipping, or noise.

**Evidence and location:** the base loader chooses a random CSV column without identifying timestamp or household ([src/profile/base.py:L31-L43](../src/profile/base.py#L31-L43)). DER CSV values are randomly rescaled/noised and later clipped ([src/profile/der.py:L119-L170](../src/profile/der.py#L119-L170), [src/profile/der.py:L239-L248](../src/profile/der.py#L239-L248)); DSO tariffs are similarly normalized and randomized ([src/profile/dso.py:L154-L217](../src/profile/dso.py#L154-L217)). The requested `steps` value is not used to select, resample, or validate the CSV length. Convolution uses zero-padded `same` smoothing ([src/profile/base.py:L49-L62](../src/profile/base.py#L49-L62)), and a positive market minimum clips genuine zero generation/demand upward ([src/profile/der.py:L239-L248](../src/profile/der.py#L239-L248)). The environment also rejects supplied zero-valued physical profiles whenever the market's minimum order quantity is positive ([src/environment/lem.py:L223-L237](../src/environment/lem.py#L223-L237)), conflating profile physics with order rules.

**Paper correspondence:** Section 3.4.4 of the [MARLEM paper](marlem.pdf) distinguishes loading time-series data from external files from generating profiles procedurally. Randomly selecting, rescaling, noising, smoothing, and clipping an external series silently crosses that stated boundary and prevents the loaded data from functioning as measured replay.

**Affected system:** measured-data claims, household identity, daylight zeros, temporal alignment, tariff fidelity, holdout design, and repeatability.

**Minimal fix:** implement deterministic replay first: explicitly select named value/timestamp columns, validate numeric/finite values and frequency, slice a named interval, and preserve values. Put all augmentation behind a separate, seeded `synthetic` mode with saved parameters.

**Validation:** replay returns the exact expected array and metadata; invalid/short/NaN data fail clearly; synthetic mode is reproducible and never labelled measured replay.

### P2-04. Saved environment configuration cannot reconstruct the original scenario

**Classification:** Confirmed reproducibility gap.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** `EnvConfigHandler` now writes lossless profiles and preserves replay sources/columns, seeds, battery limits, and DSO/grid configuration; focused round-trip regressions cover profile and key-order restoration plus a complete seeded environment transition with matching rewards and recorded market/grid/KPI outputs.

**Evidence and location:** profiles are rounded during serialization ([src/environment/io.py:L133-L148](../src/environment/io.py#L133-L148)). Grid and profile handlers never store `self.seed`, yet serialization reads it with `getattr`, producing `None` ([src/grid/network.py:L25-L49](../src/grid/network.py#L25-L49), [src/profile/base.py:L17-L29](../src/profile/base.py#L17-L29), [src/environment/io.py:L105-L111](../src/environment/io.py#L105-L111), [src/environment/io.py:L150-L158](../src/environment/io.py#L150-L158)). Profile source paths and replay/augmentation choices are omitted and therefore cannot be restored ([src/environment/io.py:L150-L158](../src/environment/io.py#L150-L158), [src/environment/io.py:L234-L250](../src/environment/io.py#L234-L250)). DSO restoration depends on top-level grid having already been processed and ignores its serialized nested grid ([src/environment/io.py:L180-L207](../src/environment/io.py#L180-L207)). `json.dump(..., default=str)` silently stringifies unknown values ([src/environment/io.py:L49-L55](../src/environment/io.py#L49-L55)).

**Paper correspondence:** Sections 3.2, 3.7.2, and 4 of the [MARLEM paper](marlem.pdf) claim reproducible evolution, a reproducible end-to-end experimental workflow, and detailed configurations in the repository. The paper does not define a serialization or manifest schema, so these are capability claims that the current lossy environment snapshot cannot substantiate rather than a paper-provided reconstruction formula.

**Affected system:** checkpoint restoration, measured-data lineage, exact reruns, auditability, and sharing results.

**Minimal fix:** replace object snapshots with a versioned scenario schema containing scalar parameters, explicit units, seeds, ordered agent IDs, dataset paths/IDs/hashes, split IDs, and augmentation settings. Store generated profiles losslessly or store enough source metadata to regenerate them exactly.

**Validation:** serialize→restore→serialize must be equal; two environments created from the same manifest must produce identical seeded trajectories.

### P2-05. Training configuration contains validation, scheduling, and resource defects

**Classification:** Confirmed defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Positive integer evaluation durations are accepted (while booleans are rejected), request complete RLlib episodes with the literal `"episodes"` unit, and use no additional evaluation workers; one trial uses no PBT; names are collision-resistant; Ray shutdown covers both Tune setup and fitting; and checkpoint selection uses the predeclared held-out return only when evaluation is enabled. A configured training batch must cover one whole episode, so Tune always receives the declared episode-return selection metric. A real one-iteration Windows DTDE PPO CPU run with separately seeded train/validation configurations recorded one completed evaluation episode and `evaluation/env_runners/episode_return_mean`; the manifest verified afterwards. The focused configuration regressions and acceptance gate pass. The Windows startup disables unavailable PyTorch libuv and uses portable CSV/JSON Tune loggers.

**Evidence and location:** the boolean condition rejects every positive integer `evaluation_duration`; only `"auto"` passes ([src/environment/train.py:L108-L117](../src/environment/train.py#L108-L117)). The default CPU count is assigned both to training and parallel evaluation runners ([src/environment/train.py:L150-L154](../src/environment/train.py#L150-L154), [src/environment/train.py:L283-L294](../src/environment/train.py#L283-L294)), potentially doubling allocation. Population Based Training is always installed, even when `tune_samples=1` ([src/environment/train.py:L428-L437](../src/environment/train.py#L428-L437)). Experiment names have only minute precision ([src/environment/train.py:L438-L440](../src/environment/train.py#L438-L440)), and `ray.shutdown()` is not protected by `finally` around `tuner.fit()` ([src/environment/train.py:L448-L458](../src/environment/train.py#L448-L458)). Checkpoint selection uses shaped evaluation return ([src/environment/train.py:L443-L445](../src/environment/train.py#L443-L445)).

**Paper correspondence:** Section 3.7.2 of the [MARLEM paper](marlem.pdf) describes Population-Based Training as jointly optimizing a population of agents/runs and claims that the managed workflow supports reproducible comparison. That description supports treating unconditional PBT with one sample as incoherent, but the paper does not specify duration validation, resource accounting, cleanup, run naming, or checkpoint-selection rules.

**Affected system:** valid CLI/configuration values, machine stability, failed-run cleanup, experiment collisions, and selected models.

**Minimal fix:** correct the duration predicate; allocate a declared total CPU budget; use FIFO/no scheduler for one sample; add seconds plus a short manifest hash to run IDs; wrap Ray lifetime in `try/finally`; select checkpoints by a predeclared validation objective after P1 metrics are fixed.

**Validation:** configuration unit tests for all boundary values, a one-iteration CPU smoke test, forced-failure cleanup test, and unique-run-name test.

### P2-06. Experiments lack immutable manifests, baselines, and statistical reporting

**Classification:** Reproducibility gap.

**Tracker**

- **Status:** `Blocked`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Versioned manifests and append-only episode-record files are created before training; manifests include a stable content hash that `RLTrainer.verify_run_manifest` verifies before analysis, and provenance records commit/dirty-tree state and project, lockfile, metric-contract, and profile-source hashes. Deterministic random-valid, DSO-fallback, and perfect-current-state greedy baselines are available; the random baseline consumes the reset-seeded environment generator and baseline records use the same `episode_return` field as training/test raw records. RLlib's episode callback records completed raw training episode returns/lengths on the driver, while declared split runs append one raw record per seed. `python -m src.environment.reproducibility_smoke` executes the complete non-learning path over three declared seeds and produces a verified manifest, JSONL records, and a return summary. Raw-record summaries include mean, sample standard deviation, and a 95% normal-approximation interval. A compact real PPO run wrote `training_episode` JSONL records. **External blocker:** a reportable multi-seed RL study and independent clean-checkout reproduction need user-selected valid source data and a chosen experimental budget.

**Evidence and location:** training saves the environment configuration only after Tune completes ([src/environment/train.py:L448-L455](../src/environment/train.py#L448-L455)) and names runs by date/time ([src/environment/train.py:L438-L440](../src/environment/train.py#L438-L440)). The repository does not create a run manifest containing code commit, dirty-tree status, dependency lock hash, data hashes, unit convention, train/test split, seed list, or metric definitions. Case notebooks commonly run 200 demonstration iterations ([notebooks/case1_market_mechanisms.ipynb:L429-L458](../notebooks/case1_market_mechanisms.ipynb#L429-L458), [notebooks/case4_grid_constraints.ipynb:L548-L676](../notebooks/case4_grid_constraints.ipynb#L548-L676)); case 6 embeds machine-local historical checkpoint paths ([notebooks/case6_implicit_cooperation.ipynb:L157-L177](../notebooks/case6_implicit_cooperation.ipynb#L157-L177)). No independent random, rule-based self-consumption, greedy price, or optimization baseline is part of the training protocol.

**Paper correspondence:** Section 3.7.2 of the [MARLEM paper](marlem.pdf) claims reproducible training, checkpointing, metrics, and inference. Section 4.2 explicitly defines zero-intelligence agents as an essential lower-bound baseline and CTCE as a comparison benchmark. The paper therefore supplies baseline intent, but the repository lacks a centralized, immutable experiment protocol that can reproduce those comparisons; neither the paper nor code provides the required manifest or statistical seed design.

**Affected system:** thesis reproducibility, failure recovery, algorithm comparison, statistical significance, and external review.

**Minimal fix:** write the manifest before a run starts, write append-only raw episode results, and add three simple baselines before adding more MARL variants: random valid action, deterministic self-consumption/DSO fallback, and a small perfect-information optimizer where feasible. Report distributions/confidence intervals across seeds, not one best curve.

**Validation:** a clean checkout plus manifest can reproduce a run; interrupted runs retain their manifest/raw data; tables can be regenerated from raw records without notebook state.

## P3 — maintenance and documentation defects

### P3-01. The “blockchain validator” is incomplete for settlement integrity and is unnecessary in the critical path

**Classification:** Confirmed design/claim mismatch.

**Tracker**

- **Status:** `Fixed - pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Settlement logging is opt-in, hash-chained, and explicitly not proof-of-work or decentralized consensus; its record includes all trade settlement fields.

**Evidence and location:** block hashes include buyer, seller, price, quantity, and timestamp but omit distance, transmission loss, and fees ([src/market/validation.py:L19-L34](../src/market/validation.py#L19-L34)), so those settlement fields can change without invalidating the chain. The matcher calls the validator's private `_create_new_block` after every step ([src/market/matching.py:L390-L396](../src/market/matching.py#L390-L396)), overriding normal `block_size` behavior ([src/market/validation.py:L45-L56](../src/market/validation.py#L45-L56), [src/market/validation.py:L88-L107](../src/market/validation.py#L88-L107)). This is a single in-memory proof-of-work chain, not decentralized consensus.

**Paper correspondence:** Section 3.3.4 and Algorithm 1 of the [MARLEM paper](marlem.pdf) claim that all executed trades are hashed, aggregated into blocks, validated through simplified Proof-of-Work consensus, and added to an immutable ledger that provides auditability without a central arbiter. Omitting settlement fields and maintaining a single in-memory chain cannot support those claims. The paper is also the source of the stronger “decentralized validation” terminology that should be narrowed.

**Affected system:** performance, audit claims, validator tests, and terminology; it does not provide correctness for the settlement defects above.

**Minimal fix:** remove proof-of-work from the default simulation path. Use an append-only, hash-chained settlement log only if tamper evidence is a thesis requirement, and hash the complete canonical settlement record. Describe it as tamper-evident logging, not decentralized validation.

**Validation:** changing any settlement field invalidates the chain, normal execution does not call private methods, and disabling the log does not change market outcomes.

### P3-02. Defensive validation hides bad state or is internally ineffective

**Classification:** Confirmed maintenance defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** Invalid grid/topology/market inputs now fail before normalization, mutable profile defaults are isolated, profile numeric bounds accept integers, and DSO unknown-node checks fail deterministically. Focused P3 tests and the acceptance gate pass.

**Evidence and location:** grid capacity is clamped nonnegative before a later negative-capacity error check, making that check dead ([src/grid/network.py:L25-L38](../src/grid/network.py#L25-L38), [src/grid/network.py:L90-L96](../src/grid/network.py#L90-L96)). Procedural node-count validation compares enum instances with a value-keyed member map and therefore does not select the intended topologies ([src/grid/network.py:L98-L104](../src/grid/network.py#L98-L104)). `Location.distance_to` uses a bare `except` ([src/grid/base.py:L51-L57](../src/grid/base.py#L51-L57)), and DSO path/fee code catches broad exceptions and substitutes other metrics ([src/market/dso.py:L293-L308](../src/market/dso.py#L293-L308), [src/market/dso.py:L382-L387](../src/market/dso.py#L382-L387)). DER and DSO constructors use mutable list defaults ([src/agent/der.py:L24-L30](../src/agent/der.py#L24-L30), [src/market/dso.py:L25-L33](../src/market/dso.py#L25-L33)). Profile validators reject otherwise valid integer bounds because they require `float` specifically ([src/profile/der.py:L77-L81](../src/profile/der.py#L77-L81), [src/profile/dso.py:L74-L78](../src/profile/dso.py#L74-L78)). Market enum validation can evaluate membership against the Enum after a type failure ([src/market/matching.py:L47-L62](../src/market/matching.py#L47-L62)).

**Paper correspondence:** Section 3.2.3 and Algorithm 1 of the [MARLEM paper](marlem.pdf) claim two-layer action constraint enforcement and explicit order validation before clearing. Those claims provide only general intent; the paper does not define constructor validation, exception handling, topology-enum checks, or Python object defaults. The listed failures therefore remain primarily repository evidence.

**Affected system:** configuration errors, disconnected grids, shared object state, debugging, and deterministic failure behavior.

**Minimal fix:** reject invalid input before normalizing it, compare explicit topology sets, catch only expected NetworkX exceptions, replace list defaults with `None`, and convert/validate enums once at the boundary.

**Validation:** focused invalid-input tests with exact exception types/messages and a test proving two default-constructed agents do not share lists.

### P3-03. Documentation, notebooks, and packaging describe a different repository state

**Classification:** Confirmed documentation/repository defect.

**Tracker**

- **Status:** `Fixed — pending validation`
- [x] Resolution implemented
- [x] Verification added or completed
- [x] Relevant tests and acceptance gate pass
- [x] Thesis/documentation impact recorded
- **Evidence:** README, notebook inventory, test guide, supported topology list, and CPU/CUDA policy now describe the checked-in repository. The locked focused gate runs in `.github/workflows/validation.yml`. All executable case notebooks resolve the repository root whether Jupyter starts at the root or in `notebooks/`; cases 1–7 execute from fresh kernels. Cases 1–5 default to zero-intelligence simulations and no longer request the disabled CTDE mode; their fresh runs report 6/6, 4/4, 4/4, 3/3, and 6/6 successful scenarios with zero failures. Case 1's market quantity cap now covers its configured profile peak. Case 3 compares explicit DSO fallback caps rather than unsupported intervention-controller attributes. The case-6 notebook no longer embeds machine-local checkpoint paths and safely skips optional resume/inference until configured. Case 7 defaults to a no-training review; its smoke run and full analysis are explicit opt-ins, and it excludes the disabled CTDE path. Captured notebook outputs are cleared so stale failures cannot be mistaken for current results. Every repository notebook's JSON and Python code cells parse in the focused P3 gate, and every local Markdown target in README/docs/notebook guidance exists. A fresh isolated copy installs with `conda env create --file environment.yml` and passes the test gate; `--link-mode=copy` is required on this OneDrive filesystem because hard links are unavailable. A one-iteration Windows CUDA PPO run completed with one local GPU learner, one GPU per learner, a checkpoint, and no trial errors; the Windows local-learner path avoids unavailable NCCL.

**Evidence and location:** README commands and tree entries refer to a nonexistent `cases/` package ([README.md:L75](../README.md#L75), [README.md:L190-L217](../README.md#L190-L217), [README.md:L291](../README.md#L291)). README describes STAR and TREE topologies, but the enum exposes only IEEE34, IEEE13, MESH, RING, and LINE ([README.md:L270-L277](../README.md#L270-L277); [src/grid/base.py:L16-L23](../src/grid/base.py#L16-L23)). README says six case studies while a seventh scalability notebook exists ([README.md:L247-L291](../README.md#L247-L291); [notebooks/case7_scalability_analysis.ipynb:L128-L154](../notebooks/case7_scalability_analysis.ipynb#L128-L154)). `docs/tests.md` documents test modules that are absent ([docs/tests.md:L1-L56](tests.md#L1-L56)). The working tree currently contains `environment.yml` and `environment.yml`, but both are untracked; `environment.yml` also sets `package=false` and routes Torch through a CUDA 12.6 index ([environment.yml:L37-L47](../environment.yml#L37-L47)), which needs an explicit CPU/GPU support policy.

**Paper correspondence:** Sections 3, 4.1, and 4.3 of the [MARLEM paper](marlem.pdf) direct readers to the repository for detailed module documentation, reproducible configurations, and six comprehensive scenarios. Repository commands and inventories that no longer match the available package, notebooks, tests, or supported topologies directly undermine that paper-facing reproducibility claim.

**Affected system:** onboarding, thesis presentation, installation, reproducibility, supported-platform claims, and contributor expectations.

**Minimal fix:** after the model fixes, regenerate README/test documentation from what actually runs; either restore maintained case scripts or remove their commands; list all notebooks accurately; commit one canonical lock/workflow; document CPU versus CUDA installation. Keep notebooks as presentation layers over tested experiment functions, not independent implementations.

**Validation:** run every documented command in a clean checkout, execute notebooks from cleared state against small fixtures, check all links/paths, and install/test the declared CPU and supported GPU environments.

## Implementation order and acceptance gates

The issues should be fixed by dependency, not merely by file. This avoids rewriting reward and analytics on top of another incorrect settlement model.

### Phase 0 — freeze conventions and create the invariant harness

1. Write a one-page model contract for units, timestep, energy boundaries, action semantics, price convention, and episode horizon.
2. Convert the existing manual tests into a small assertion-based suite.
3. Add golden fixtures with two agents, one DSO, deterministic profiles, and no stochastic augmentation.

**Gate 0:** pytest runs cleanly and contains failing regression tests for the known P0 defects before those defects are fixed.

### Phase 1 — repair the simulation kernel

1. Implement immutable orders, fills, and energy/cash settlement ledgers.
2. Fix DER feasibility, action representation, battery equations, and horizon handling.
3. Fix the common pricing interface and DSO residual handling.
4. Replace global reseeding with component generators and exact profile replay.

**Gate 1:** every deterministic step conserves energy and cash; all actions are feasible; all profile steps execute once; replay is exact; pricing golden tests pass.

### Phase 2 — define the grid and learning baselines narrowly

1. Correct topology connectivity and make the abstract capacity-flow model internally consistent.
2. Simplify reward to auditable terms derived from the ledgers.
3. Keep DTDE with standard RLlib algorithms as the first learning baseline.
4. Re-enable CTCE as a centralized baseline and CTDE only after actor-gradient and agent-order tests pass.

**Gate 2:** random and rule-based baselines run end-to-end; grid constraints affect every matching path identically; executed policy parameters demonstrably learn in a toy environment.

### Phase 3 — rebuild metrics and the experiment protocol

1. Implement only metrics supported by recorded raw variables and golden definitions.
2. Add versioned scenario/run manifests and disjoint train/validation/test sets.
3. Make Algorithm-based evaluation the reference inference path.
4. Run multiple seeds and report raw distributions plus uncertainty.

**Gate 3:** a clean checkout can reproduce a saved experiment and regenerate every reported table/figure from immutable raw results.

### Phase 4 — update presentation and optional features

1. Update notebooks and documentation to consume the validated experiment API.
2. Remove or isolate the proof-of-work validator.
3. Add MARLEM Studio only after the same validated API/records are stable; the UI must not contain separate simulation or metric logic.

**Gate 4:** all documented commands and notebooks execute from cleared state, and UI outputs match CLI/API outputs for the same manifest.

## Required invariant suite

The following tests are the minimum evidence needed before running thesis experiments:

| Invariant | Required assertion |
|---|---|
| Energy conservation | generation + imports + battery discharge = demand + exports + battery charge + losses + curtailment/unserved terms |
| Cash conservation | buyer debits = seller credits + DSO/fee receipts for every settlement |
| Battery conservation | SOC changes and charge/discharge losses match the documented boundary equations |
| Feasibility | no settled quantity exceeds an order, physical availability, DSO limit, or path capacity |
| Price validity | P2P price is within compatible bid/ask bounds; DSO trades use the declared tariff |
| Order immutability | submitted orders remain unchanged; fills and residuals reconcile to them |
| Horizon | exactly `N` transitions consume exactly `N` profile values and one terminal reward |
| Causality | decentralized observations do not change when unavailable future truth changes |
| Reproducibility | same manifest and seeds reproduce profiles, actions, settlements, and metrics |
| Agent ordering | group/ungroup round trips preserve the identity, observation, action, and reward of every agent |
| Learning path | parameters used for execution receive updates during training |
| Metric provenance | every reported value is reproducible from raw ledger/state records and a documented equation |

## Thesis-safe status language

Until Gate 3 passes, use wording such as:

> The inherited MARLEM repository was treated as a prototype implementation. A repository-level audit identified correctness, model-validity, and reproducibility defects. Experiments were withheld until energy/cash conservation, episode semantics, action-policy consistency, metric definitions, and train/test separation were covered by executable invariants.

After each gate passes, record the fix commit, test names, before/after behavior, and any resulting change to experimental conclusions. That change log is stronger thesis evidence than silently correcting the code.
