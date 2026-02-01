---
name: raspberry-pi-telemetry
description: Work with Raspberry Pi telemetry logger systems that collect battery, CPU, and process metrics into SQLite databases. Use when the user needs to set up or configure telemetry logging on Raspberry Pi, analyze power consumption and battery drain patterns, build ML models to predict power usage, query or visualize telemetry data, troubleshoot systemd services, work with power_supply sysfs interfaces, or extract training datasets from time-series telemetry.
---

# Raspberry Pi Telemetry Logger

Work with telemetry logging systems for Raspberry Pi that track battery, CPU, and process-level resource usage in SQLite databases.

## Core Concepts

**System Architecture:**
- Python logger using `psutil` + SQLite (no pip required, uses apt packages)
- Samples every N seconds (default: 5s, minimum: 1s due to integer epoch timestamps)
- Three-table schema: `system_sample` (system metrics), `cpu_core` (per-core usage), `process_sample` (top-N processes)
- Auto-creates `training_view` for ML-friendly feature extraction
- Runs as systemd service with state directory `/var/lib/telemetry-logger/`

**Battery/Power Integration:**
- Uses Linux `power_supply` sysfs interface (`/sys/class/power_supply/`)
- Auto-detects battery sources (UPS HATs, PMIC chips)
- Reads: voltage (V), current (A), power (W), capacity (%)
- Computes: mAh/min drain rates, watts (absolute value)

**ML Workflow:**
- Features: `cpu_total`, `cpu_freq`, `load1/5/15`, process-level aggregates
- Targets: `watts` (power draw), `drain_mah_per_min` (battery drain rate)
- Export to CSV via `training_view` for external training

## Quick Start

### Installing and Running

Check dependencies:
```bash
dpkg -l | grep -E 'python3-psutil|sqlite3'
```

Install if missing:
```bash
sudo apt update && sudo apt install -y python3 python3-psutil sqlite3
```

Run logger:
```bash
python3 logger.py --db telemetry.db --interval 5 --top-procs 10 --verbose
```

### Setting Up as Service

Install systemd service (runs as current user):
```bash
./install_service.sh
```

Check status:
```bash
systemctl status telemetry-logger.service
journalctl -u telemetry-logger.service -f
```

Service defaults (edit `telemetry-logger.service` to customize):
- DB: `/var/lib/telemetry-logger/telemetry.db`
- Interval: 5s, Top processes: 10, Power: auto-detect

After editing service file:
```bash
sudo systemctl daemon-reload
sudo systemctl restart telemetry-logger.service
```

## Working with Battery/Power Data

### Detecting Power Sources

Check available power supplies:
```bash
ls /sys/class/power_supply/
for d in /sys/class/power_supply/*; do echo "== $d =="; cat "$d/type"; done
```

Test specific battery:
```bash
python3 logger.py --power-supply BAT0 --verbose
```

### Understanding Power Metrics

**Units in database:**
- `voltage`: volts (V)
- `current`: amps (A), sign convention driver-dependent (negative often = discharging)
- `power`: watts (W), computed as V×A if `power_now` unavailable
- `battery_pct`: 0-100%

**Derived metrics in `training_view`:**
- `watts`: `ABS(power)` - always positive magnitude
- `drain_mah_per_min`: when `current < 0`, converts to mAh/min
- `charge_mah_per_min`: when `current > 0`, converts to mAh/min

### Common Power Queries

Recent battery status:
```sql
SELECT ts, battery_pct, watts, drain_mah_per_min
FROM training_view
ORDER BY ts DESC LIMIT 60;
```

Average drain over last 10 minutes:
```sql
SELECT AVG(drain_mah_per_min) AS avg_drain_mah_per_min,
       AVG(watts) AS avg_watts
FROM training_view
WHERE ts >= (SELECT MAX(ts) - 600 FROM system_sample);
```

Battery % change rate (percent per hour):
```sql
WITH x AS (
  SELECT ts, battery_pct,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
    LAG(battery_pct) OVER (ORDER BY ts) AS prev_pct
  FROM training_view WHERE battery_pct IS NOT NULL
)
SELECT ts, battery_pct,
  (battery_pct - prev_pct) / ((ts - prev_ts) / 3600.0) AS pct_per_hour
FROM x WHERE prev_ts IS NOT NULL
ORDER BY ts DESC LIMIT 60;
```

## ML Training Workflow

### Export Training Data

Export to CSV:
```bash
sqlite3 -header -csv telemetry.db \
  "SELECT * FROM training_view WHERE watts IS NOT NULL" > training.csv
```

### Feature Engineering

Add process-level features:
```sql
WITH proc AS (
  SELECT ts,
    SUM(cpu) AS topn_cpu_sum,
    MAX(cpu) AS top_cpu,
    SUM(mem) AS topn_mem_sum
  FROM process_sample GROUP BY ts
)
SELECT t.*, p.topn_cpu_sum, p.top_cpu, p.topn_mem_sum
FROM training_view t
LEFT JOIN proc p ON p.ts = t.ts
WHERE t.watts IS NOT NULL;
```

Compute energy used (Wh) from sampled watts:
```sql
WITH w AS (
  SELECT ts, watts,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts
  FROM training_view WHERE watts IS NOT NULL
)
SELECT SUM(watts * (ts - prev_ts) / 3600.0) AS watt_hours_est
FROM w WHERE prev_ts IS NOT NULL;
```

### Typical ML Setup

**Regression task:**
- Target (Y): `watts` or `drain_mah_per_min`
- Features (X): `cpu_total`, `cpu_freq`, `load1`, `load5`, `load15`
- Optional: Process aggregates (`topn_cpu_sum`, `top_cpu`, `topn_mem_sum`)

**Data collection strategy:**
- Collect under diverse workloads (idle, compile, video, gaming)
- Vary power settings (CPU governor, screen brightness, WiFi/BT on/off)
- Export `training_view` and train externally (scikit-learn, PyTorch, etc.)

## Process Analysis

### Top Processes by CPU

Most recent top processes:
```sql
SELECT pid, name, cpu, mem
FROM process_sample
WHERE ts = (SELECT MAX(ts) FROM system_sample)
ORDER BY cpu DESC;
```

CPU-intensive apps over time:
```sql
SELECT name, COUNT(*) AS appearances, AVG(cpu) AS avg_cpu
FROM process_sample
GROUP BY name
ORDER BY avg_cpu DESC LIMIT 20;
```

Correlate watts with processes:
```sql
SELECT s.ts, ABS(s.power) AS watts, p.pid, p.name, p.cpu, p.mem
FROM system_sample s
JOIN process_sample p ON p.ts = s.ts
WHERE s.ts >= (SELECT MAX(ts) - 600 FROM system_sample)
ORDER BY s.ts DESC, p.cpu DESC;
```

### Per-Core Analysis

View specific core usage:
```sql
SELECT ts, core, usage
FROM cpu_core WHERE core = 0 ORDER BY ts;
```

## Database Schema Reference

See references/schema.md for complete table definitions and indexes.

**Key tables:**
- `system_sample`: System-wide metrics (ts is PRIMARY KEY)
- `cpu_core`: Per-core CPU usage (PRIMARY KEY: ts, core)
- `process_sample`: Top-N processes (PRIMARY KEY: ts, pid)

**Important view:**
- `training_view`: ML-friendly denormalized view with computed features

**WAL mode:** Enabled for better concurrency (`journal_mode=WAL`, `synchronous=NORMAL`)

## Common Issues

### Timestamp Conflicts

Logger increments `ts` if samples collide (same epoch second). If interval < 1s requested, logger will error:
```
ValueError: interval must be >= 1 second (schema uses epoch seconds as primary key)
```

### Missing Battery Data

If `--power-supply auto` finds nothing:
1. Check `/sys/class/power_supply/` exists and has entries
2. Verify at least one entry has `type` = `Battery`
3. Force specific battery: `--power-supply BAT0`
4. Use `--power-supply none` to disable (nulls in DB)

### Service Permission Issues

Service runs as user specified during `install_service.sh`. Check:
```bash
systemctl cat telemetry-logger.service | grep User=
```

If DB path is inaccessible, either:
- Change `StateDirectory` in service file, or
- Adjust file permissions for the service user

## Advanced Resources

For detailed information:
- **references/schema.md**: Complete database schema with column types and constraints
- **references/queries.md**: Advanced SQL query patterns and analytics
- **scripts/analyze_battery.py**: Automated battery analysis script
- **scripts/export_features.py**: Feature extraction for ML pipelines
