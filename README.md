# Solar Savings

A Home Assistant custom integration that tracks money saved by a solar +
battery system, valued at real grid pricing — not just "how much solar did I
make," but "how much did that actually save me, and how much did the battery
save me separately by buying grid energy cheap and using it when it's
expensive."

## Why this exists

A solar+battery system with a dynamically-priced grid (Nord Pool / Energi
Data Service in this case) produces savings from several distinct sources,
and a home battery that can be charged from *either* solar surplus *or* the
grid (for price arbitrage) means every kWh leaving the battery has to be
traced back to where it came from before it can be valued correctly. See
[`custom_components/solar_savings/ledger.py`](custom_components/solar_savings/ledger.py)
for the accounting model (a FIFO queue of energy "parcels," each tagged with
its source and, for grid parcels, the price paid).

## Entities created

| Entity | Unit | What it means |
|---|---|---|
| `sensor.solar_direct_savings` | DKK | Solar used immediately by the house, valued at grid price at time of use |
| `sensor.solar_via_battery_savings` | DKK | Solar stored then discharged later, valued at grid price at time of discharge |
| `sensor.total_solar_savings` | DKK | The two above, combined — "how much has solar saved me" |
| `sensor.battery_arbitrage_savings` | DKK | Grid energy bought cheap, stored, discharged when the price was higher |
| `sensor.total_system_savings` | DKK | Solar savings + arbitrage savings — everything the system has saved, regardless of source |
| `sensor.solar_export_revenue` | DKK | Energy fed back to the grid, valued at the export/compensation price. Revenue, not a saving — kept separate on purpose |
| `sensor.battery_solar_fraction` | ratio 0–1 | Diagnostic: share of what's currently in the battery that's solar-origin |
| `sensor.battery_grid_charge_cost_basis` | DKK/kWh | Diagnostic: weighted-average price paid for the grid-origin energy currently in the battery |

All money entities are `device_class: monetary`, `state_class: total_increasing`
(they only ever grow) — use HA's History/Statistics graphs on them for
daily/monthly/yearly breakdowns.

## Configuration

Added via **Settings → Devices & Services → Add Integration → Solar
Savings**. The setup form asks for seven entities (all pre-filled with
sensible defaults, all EntitySelector fields so nothing is hardcoded):

| Field | Default |
|---|---|
| Solar power | `sensor.pv_power` |
| Battery charge power | `sensor.battery_charge` |
| Battery discharge power | `sensor.battery_discharge` |
| Grid feed-in (export) power | `sensor.feed_in` |
| Grid import price | `sensor.energi_data_service` |
| Export / compensation price | `sensor.energi_data_service_raw` |
| Battery grid-charge indicator | `binary_sensor.evcc_battery_grid_charge_active` |

The defaults match a FoxESS inverter + evcc + Energi Data Service setup; any
field can point at different entities for a different inverter/pricing
integration, as long as the power entities are in kW and the price entities
are in currency/kWh.

## Installation

**Manual (always works):** copy `custom_components/solar_savings/` into your
Home Assistant `config/custom_components/` directory, restart Home
Assistant, then add the integration from the UI.

**HACS custom repository:** HACS's "add custom repository" flow expects a
GitHub URL; a self-hosted Forgejo repository (like this one, on
`git.eskesen.eu`) may not be accepted there. If it isn't, use the manual
copy method above instead.

## Development

The core accounting logic (`ledger.py`) has no Home Assistant dependency and
is unit tested on its own:

```sh
python3 -m unittest discover -s tests -v
```

`engine.py` is the thin Home Assistant-facing layer: it listens for state
changes on the configured entities (plus a ~30s backstop timer, matching
`evcc_intg`'s own poll cadence, for sensors that hold steady and never fire a
state-changed event), does the power→energy integration, feeds the ledger,
persists it via Home Assistant's `Store` helper, and notifies the sensor
platform.

### Known limitation

The battery grid-charge indicator can lag the real charge-source switch by
up to one poll cycle of whatever integration provides it (~30s for
`evcc_intg`, confirmed empirically). For a charge/discharge event lasting
minutes to hours this misattributes a negligible sliver of energy at the
boundary.
