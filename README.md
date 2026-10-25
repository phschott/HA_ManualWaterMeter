# Manual Water Meter — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/phschott/HA_ManualWaterMeter.svg)](https://github.com/phschott/HA_ManualWaterMeter/releases)
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
- **Energy dashboard source** — a `sensor` with `device_class: water` and
  `state_class: total_increasing` (unit m³), so it can be selected as a **water source**
  in Settings → Dashboards → Energy.
- **Configurable reminder** — set a reminder frequency (in days). When a new reading is
  overdue the integration raises a persistent notification, turns on a
  `binary_sensor`, and fires a `manual_water_meter_reminder` event you can use in
  automations.

## Entities created

| Entity | Type | Purpose |
| --- | --- | --- |
| `number.<name>_meter_reading` | Number | Enter the current meter value (m³) |
| `sensor.<name>_water_consumption` | Sensor | Water source for the Energy dashboard |
| `sensor.<name>_days_since_last_reading` | Sensor | Days elapsed since the last reading |
| `binary_sensor.<name>_reading_reminder` | Binary sensor | `on` when a reading is overdue |

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

Settings → Dashboards → **Energy** → *Add water source* →
select `sensor.<name>_water_consumption`.

Because the reading is a cumulative meter value, it is exposed as
`total_increasing`: enter the raw number from your meter each time (always increasing),
and the Energy dashboard computes the consumption between readings.

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
**long-term statistics** for the water sensor, so it shows up retroactively in the
Energy dashboard. Consumption between two readings is spread evenly over each hour
of the interval, and re-importing the same range is idempotent (no double count).

### CSV format

Two columns: an ISO 8601 `date` (or datetime) and the absolute meter `reading` in m³.

```csv
date,reading
2025-01-01,123.456
2025-02-01,128.900
2025-03-01,134.010
```

- A date without a time is taken at local midnight.
- The reading is the cumulative meter index; it must never decrease.
- A header row is optional; `;` separators (French Excel) and `,` decimals are tolerated.

### Calling the service

```yaml
action: manual_water_meter.import_history
target:
  entity_id: sensor.water_meter_water_consumption
data:
  filename: /config/water_history.csv   # or inline with `csv:`
  update_current: true                  # also set the meter to the last reading
```

Inline variant:

```yaml
action: manual_water_meter.import_history
target:
  entity_id: sensor.water_meter_water_consumption
data:
  csv: |
    date,reading
    2025-01-01,123.456
    2025-02-01,128.900
```

> Note: this is meant to seed history *before* the sensor started recording. A small
> discontinuity may appear where imported data meets the live statistics.

## License

[MIT](LICENSE) © PH Schott
