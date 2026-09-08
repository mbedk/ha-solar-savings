<img src="logo.svg" width="88" height="88" align="left" alt="" />

# Solar Savings

<br clear="left" />

A Home Assistant custom integration that tracks money saved by a solar +
battery system, valued at real grid pricing — not just "how much solar did I
make," but "how much did that actually save me, and how much did the battery
save me separately by buying grid energy cheap and using it when it's
expensive."

## What it tells you

With a dynamically-priced grid tariff, a kWh is worth whatever the price was
at the moment you used it — and a battery that can be charged from *either*
solar surplus *or* cheap grid energy means savings come from several
different places. This integration keeps them apart:

- **Solar used directly** by the house, valued at the grid price you avoided
  paying at that moment.
- **Solar stored and used later**, valued at the price in effect when it
  actually came back out of the battery — usually worth more than using it
  at midday.
- **Battery arbitrage** — grid energy bought cheap overnight and used when
  the price is high. Only the spread counts as a saving.
- **Export revenue** — energy sent back to the grid, at the export price.
  Revenue rather than a saving, so it's tracked separately and never mixed
  into the savings totals.

Everything accumulates from the day you install it and survives restarts.

## Entities

**Money (DKK, `device_class: monetary`)**

| Entity | What it means |
|---|---|
| `sensor.solar_direct_savings` | Solar used immediately by the house, valued at grid price at time of use |
| `sensor.solar_via_battery_savings` | Solar stored then discharged later, valued at grid price at time of discharge |
| `sensor.total_solar_savings` | The two above, combined — "how much has solar saved me" |
| `sensor.battery_arbitrage_savings` | Grid energy bought cheap, stored, discharged when the price was higher |
| `sensor.total_system_savings` | Solar savings + arbitrage savings — everything the system has saved |
| `sensor.solar_export_revenue` | Energy fed back to the grid, at the export/compensation price |

**Period totals (DKK)** — `total_system_savings`, but counting only the
current day, week, month or year:

| Entity | Resets |
|---|---|
| `sensor.total_system_savings_daily` | Local midnight |
| `sensor.total_system_savings_weekly` | Monday (ISO week) |
| `sensor.total_system_savings_monthly` | The 1st |
| `sensor.total_system_savings_yearly` | January 1st |

Each of these also carries a `history` attribute holding previous closed
periods, so you can show last month's or last year's total without digging
through the Statistics view:

```
{{ state_attr('sensor.total_system_savings_yearly', 'history')['2025'] }}
```

History keeps the last 30 days, 4 weeks and 12 months; yearly is kept
indefinitely. Only periods the integration actually lived through appear —
nothing is estimated or backfilled.

**Diagnostics**

| Entity | Unit | What it means |
|---|---|---|
| `sensor.battery_solar_fraction` | ratio 0–1 | Share of what's in the battery right now that is solar-origin |
| `sensor.battery_grid_charge_cost_basis` | DKK/kWh | Weighted-average price paid for the grid-origin energy currently in the battery |

## Requirements

You need entities already in Home Assistant providing:

- Solar production, battery charge and battery discharge power, and grid
  feed-in power — **in kW**
- Grid import price and export price — **in currency per kWh**
- A binary sensor that is `on` while the battery is being charged *from the
  grid* rather than from solar

The defaults match a FoxESS inverter + evcc + Energi Data Service setup, but
any inverter or pricing integration works as long as the units match.

## Installation

**HACS (recommended):** add
`https://github.com/mbedk/ha-solar-savings` as a custom repository with
category "Integration," install it, then restart Home Assistant.

**Manual:** copy `custom_components/solar_savings/` into your Home Assistant
`config/custom_components/` directory and restart.

## Configuration

Add it via **Settings → Devices & Services → Add Integration → Solar
Savings**. The form asks for seven entities, all pre-filled and all
selectable from a dropdown:

| Field | Default |
|---|---|
| Solar power | `sensor.pv_power` |
| Battery charge power | `sensor.battery_charge` |
| Battery discharge power | `sensor.battery_discharge` |
| Grid feed-in (export) power | `sensor.feed_in` |
| Grid import price | `sensor.energi_data_service` |
| Export / compensation price | `sensor.energi_data_service_raw` |
| Battery grid-charge indicator | `binary_sensor.evcc_battery_grid_charge_active` |

To point it at different entities later — say you find a source that tracks
your billing meter more closely — use **Reconfigure** on the integration's
three-dot menu. Accumulated totals and period history are kept. Do not
remove and re-add it instead: the ledger is stored per config entry, so a
fresh entry starts from zero.

There is nothing to configure in YAML.

## How a kWh gets valued

Energy that goes into the battery doesn't lose its identity. Every charge
appends a "parcel" to the **back** of a queue, tagged with where the energy
came from and — for grid energy — what was paid for it. Every discharge
takes from the **front** of that queue, so each kWh is credited to the
stream it actually came from, in the order it was stored, rather than
smeared across an approximate solar-vs-grid ratio for the whole battery.

```mermaid
flowchart TD
    C(["Battery charging\n(this tick)"]) --> Q{"evcc grid-charge\nactive right now?"}
    Q -- yes --> G["Tag this slice GRID\nunit_cost = current grid price"]
    Q -- no --> S["Tag this slice SOLAR\nunit_cost = 0"]
    G --> A["Append to the BACK of the queue\n(merge into the previous parcel if\nsame source + same cost)"]
    S --> A

    D(["Battery discharging\n(this tick)"]) --> F["Take energy from the\nFRONT parcel"]
    F --> T{"That parcel's\nsource?"}
    T -- SOLAR --> SV["+= kWh × current grid price\n→ solar_via_battery_savings"]
    T -- GRID --> AV["+= kWh × (current grid price − parcel's unit_cost)\n→ battery_arbitrage_savings"]
    SV --> N{"Parcel fully\nconsumed?"}
    AV --> N
    N -- yes, energy remains --> P["Pop it, move to\nthe next parcel"]
    N -- no / nothing left to discharge --> E(["Done for this tick"])
    P --> F
```

<details>
<summary>Worked example with concrete numbers</summary>

```
1. charge 2.0 kWh from SOLAR
   queue:  [ SOLAR 2.0 kWh ]
            front ────────── back

2. charge 3.0 kWh from GRID at 1.00 DKK/kWh
   queue:  [ SOLAR 2.0 kWh ][ GRID 3.0 kWh @1.00 ]
            front ──────────────────────── back

3. discharge 1.0 kWh while the grid price is 2.00
   → takes 1.0 kWh off the FRONT parcel (SOLAR)
   → solar_via_battery_savings += 1.0 × 2.00 = 2.00 DKK
   queue:  [ SOLAR 1.0 kWh ][ GRID 3.0 kWh @1.00 ]

4. discharge 2.0 kWh while the grid price is 2.00
   → finishes the SOLAR parcel (1.0 kWh left): += 1.0 × 2.00 = 2.00 DKK
     (solar_via_battery_savings now 4.00 DKK total) — parcel emptied, popped
   → spills into the GRID parcel for the remaining 1.0 kWh:
     battery_arbitrage_savings += 1.0 × (2.00 − 1.00) = 1.00 DKK
   queue:  [ GRID 2.0 kWh @1.00 ]

Result: solar_via_battery_savings = 4.00 DKK, battery_arbitrage_savings =
1.00 DKK — each kWh landed in the stream it actually came from.
```

The two diagnostic sensors simply read out what's in the queue at any
moment: after step 4 it holds nothing but grid energy, so
`battery_solar_fraction` reads `0.0` and the cost basis reads `1.00`.

</details>

## Good to know

**Savings can go down.** Arbitrage is a bet: if grid-charged energy is
discharged after the price has fallen below what was paid for it, that trade
lost money and `battery_arbitrage_savings` — plus anything summing it —
decreases. This is why the money entities use `state_class: total` rather
than `total_increasing`.

**The grid-charge indicator can lag.** It may trail the real
charge-source switch by up to one poll cycle of whatever integration
provides it (~30 s for `evcc_intg`). For a charge or discharge lasting
minutes to hours, that misattributes a negligible sliver of energy at the
boundary.

**Downtime isn't backfilled.** After a restart, measurement resumes from
that moment. Energy that flowed while Home Assistant was down is not
estimated and not counted — the totals stay honest rather than complete.

**Prices that go unavailable are skipped.** If the price entity is briefly
unavailable, that slice isn't valued rather than valued at zero, which would
quietly invent savings.

**Weeks and years can disagree.** "Weekly" uses the ISO week, so the week
containing January 1st may belong to the previous year.

## Development

The accounting logic has no Home Assistant dependency and is unit tested on
its own:

```sh
python3 -m unittest discover -s tests -v
```

`ledger.py` (the FIFO queue and the per-interval accounting) and
`periods.py` (calendar rollover) are pure Python; `engine.py` is the thin
Home Assistant layer that reads the configured entities, feeds the ledger,
persists state and updates the sensors.
