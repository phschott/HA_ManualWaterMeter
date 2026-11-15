# Manual Water Meter — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/phschott/HA_ManualWaterMeter.svg)](https://github.com/phschott/HA_ManualWaterMeter/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/phschott/HA_ManualWaterMeter/total.svg)](https://github.com/phschott/HA_ManualWaterMeter/releases)
[![GitHub license](https://img.shields.io/github/license/phschott/HA_ManualWaterMeter.svg)](LICENSE)
[![HA community](https://img.shields.io/badge/community-Home%20Assistant-blue.svg)](https://community.home-assistant.io)

A [Home Assistant](https://www.home-assistant.io/) custom integration to record your
water consumption **by hand** — for meters that aren't connected — and feed the reading
into the HA **Energy** dashboard.

It is useful when your water meter has no smart module: you simply type the value
printed on the meter whenever you read it, and Home Assistant does the rest.

## Features

- **Meter reading input** — a `number` entity in m³ (min `0`, max `9999`, step `0.001`)
  where you enter the value shown on your physical meter.
- **Energy dashboard source** — the integration publishes smoothed **external
  statistics** (`<name> water consumption` in m³) selectable as a **water source** in
  Settings → Dashboards → Energy.
- **Price & cost tracking** — a `number` entity to set/update the water price (currency
  per m³) and a smoothed **cost** statistic (`<name> water cost`) you select as the Energy
  cost statistic.
- **Configurable reminder** — set a reminder frequency (in days). When a new reading is
  overdue the integration raises a persistent notification, turns on a
  `binary_sensor`, and fires a `manual_water_meter_reminder` event you can use in
  automations.

## Entities created

| Entity | Type | Purpose |
| --- | --- | --- |
| `number.<name>_meter_reading` | Number | Enter the current meter value (m³) |
| `number.<name>_water_price` | Number | Set/update the water price (currency per m³) |
| `sensor.<name>_water_consumption` | Sensor | Shows the current meter reading (display) |
| `sensor.<name>_water_cost` | Sensor | Shows the current cumulative cost (display) |
| `sensor.<name>_days_since_last_reading` | Sensor | Days elapsed since the last reading |
| `binary_sensor.<name>_reading_reminder` | Binary sensor | `on` when a reading is overdue |
| `<name> water consumption` | Statistic | Smoothed consumption (m³) — the Energy water source |
| `<name> water cost` | Statistic | Smoothed cost — the Energy cost statistic |

## Installation

### HACS (recommended)

1. In HACS → Integrations → three-dot menu → **Custom repositories**, add
   `https://github.com/phschott/HA_ManualWaterMeter` as an *Integration*.
2. Install **Manual Water Meter**, then restart Home Assistant.

### Manual

Copy `custom_components/manual_water_meter` into your Home Assistant
`config/custom_components/` folder and restart Home Assistant.

## Configuration

1. Settings → Devices & Services → **Add Integration** → **Manual Water Meter**.
2. Choose a **name** and the **reminder frequency** (in days).
3. The reminder frequency can be changed anytime via the integration's **Configure** button.

## Adding to the Energy dashboard

Enter the raw cumulative number from your meter each time (always increasing).

The integration publishes its data as **external statistics** it fully owns, which show
up in the Energy pickers by name:

- `<name> water consumption` (m³) — the water source
- `<name> water cost` (currency) — the cost

Settings → Dashboards → **Energy** → *Add water source* → select **`<name> water
consumption`**. For cost, choose **Use a statistic for costs** and select **`<name> water
cost`**.

> With an external-statistics source, Home Assistant disables the "fixed price" and "cost
> entity" cost options — that is why the integration provides a ready-made cost statistic.

### Smoothed consumption

Because days often pass between two manual readings, a naïve meter would dump the whole
consumption onto the single day you enter the value — one tall spike, zeros around it.
Instead, this integration **owns its statistics** and spreads the consumption **evenly,
hour by hour, between the previous reading and the new one**, so the daily Energy curve
is smooth. The same smoothing applies to imported history.

> **Why external statistics?** An entity-based water source must carry a `state_class`,
> but then Home Assistant's recorder would compute its statistics from the state and
> double-count the smoothed values the integration injects. Publishing self-owned
> external statistics avoids both the double-count and the "unexpected state class"
> Energy warning.
>
> **Upgrading from an earlier version** that used an entity source: clear the old
> statistics of `sensor.<name>_water_consumption` and `sensor.<name>_water_cost` once in
> Developer Tools → Statistics, remove the old entity from the Energy dashboard, and add
> the new `<name> water consumption` / `<name> water cost` statistics instead.

### Tracking cost

Set the price with `number.<name>_water_price` (currency per m³). Cost is accrued as the
`<name> water cost` statistic (consumption × price), which you select as the Energy cost
statistic. Imported history carries its own per-date prices (see below).

## Reminder event

When a reading becomes overdue, a `manual_water_meter_reminder` event is fired with:

```yaml
event_type: manual_water_meter_reminder
data:
  entry_id: "<config entry id>"
  name: "<your meter name>"
  days_since_update: 31
  reminder_days: 30
```

Use it in an automation to send a mobile notification, an email, etc.

## Importing a consumption history

You can back-fill past consumption from a CSV of **absolute meter readings** with
the `manual_water_meter.import_history` service. The data is written as
**long-term statistics** for the water (and cost) sensor, so it shows up retroactively in
the Energy dashboard. Consumption between two readings is spread evenly over each hour
of the interval, and re-importing the same range is idempotent (no double count).

### CSV format

An ISO 8601 `date` (or datetime), the absolute meter `reading` in m³, and an **optional**
`price` (currency per m³ in effect from that date).

```csv
date,reading,price
2025-01-01,123.456,4.30
2025-02-01,128.900,4.30
2025-03-01,134.010,4.55
```

- A date without a time is taken at local midnight.
- The reading is the cumulative meter index; it must never decrease.
- The `price` column is optional. When present, cost is computed hourly from consumption
  times the price in effect (a step function, so a mid-history rate change is honored).
  When absent, the service's `price` field is used as a flat fallback; with neither, no
  cost is imported.
- A header row is optional; `;` separators (French Excel) and `,` decimals are tolerated.

### Calling the service

```yaml
action: manual_water_meter.import_history
target:
  entity_id: sensor.water_meter_water_consumption
data:
  filename: /config/water_history.csv   # or inline with `csv:`
  price: 4.30                           # flat fallback if the CSV has no price column
  update_current: true                  # also set the meter + cost to the last values
```

Inline variant:

```yaml
action: manual_water_meter.import_history
target:
  entity_id: sensor.water_meter_water_consumption
data:
  csv: |
    date,reading,price
    2025-01-01,123.456,4.30
    2025-02-01,128.900,4.55
```

> Note: this is meant to seed history *before* the sensor started recording. A small
> discontinuity may appear where imported data meets the live statistics.

## License

[MIT](LICENSE) © PH Schott
