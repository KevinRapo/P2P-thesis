# MARLEM model contract

This contract defines the currently validated abstract market model. It is not an
AC power-flow model.

- Power ratings (`DERAgent.capacity`, battery power limits, grid capacity) are in kW.
- Every market/order/trade quantity is energy in kWh for one timestep.
- `time_step_hours` is explicit (default `1.0`) and converts a kW action limit to
  kWh per step: `max_energy = max_power * time_step_hours`.
- Supplied generation/demand profiles are kWh by default. Set
  `profile_values_are_power=True` only for kW samples; the environment converts
  them to kWh exactly once at construction.
- Prices and fees are currency/kWh; cash is currency.
- Battery SOC is internal kWh. Charge input and discharge output are grid-side kWh.
- A positive signed action quantity requests an import; a negative value offers an
  export. Zero submits no order.
- A trade records source energy, delivered energy, and transmission loss separately.
- The grid is an abstract signed capacity graph. It begins each timestep at zero
  baseline flow and rejects disconnected or overloaded P2P paths.
- Episode `max_steps` is the exact number of market transitions. The terminal
  observation repeats the last causal profile state rather than indexing beyond it.

Experiments must record `time_step_hours`, unit convention, scenario seed, and
profile source alongside their results.
