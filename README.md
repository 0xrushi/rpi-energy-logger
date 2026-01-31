# Raspberry Pi Telemetry Logger (SQLite)

Logs battery, CPU, and process-level resource usage into a SQLite database at a configurable interval (default: 5s). Designed to be reproducible on a fresh Raspberry Pi OS install without `pip`.

## System dependencies (apt)

Required:
- `python3`
- `python3-psutil`
- `sqlite3`

Optional (for future I2C battery sensors):
- `i2c-tools`
- `python3-smbus`

Install:

```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-psutil sqlite3 i2c-tools python3-smbus
```

Notes:
- `python3-pip` is not required for this project, but is often useful on Pi images and is included in the prompt’s dependency list.
- This project uses only the Python standard library + `psutil`.

## Run

```bash
python3 logger.py
```

Common options:

```bash
python3 logger.py --db telemetry.db --interval 5 --top-procs 10 --verbose
```

## ML-friendly view (`training_view`)

On startup, the logger creates a SQLite view named `training_view` that gives one row per timestamp with common features + targets:
- Features: `cpu_total`, `cpu_freq`, `load1`, `load5`, `load15`
- Battery/power: `battery_pct`, `watts` (absolute value), plus `drain_mah_per_min` / `charge_mah_per_min`

If you updated `logger.py` after creating your DB, run the logger once to create/update the view:

```bash
python3 logger.py --db telemetry.db --power-supply auto --top-procs 0 --verbose
```

Then verify the view exists:

```bash
sqlite3 telemetry.db "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name;"
```

View columns (schema):

```bash
sqlite3 telemetry.db "PRAGMA table_info(training_view);"
```

Example:

```bash
sqlite3 -cmd ".headers on" -cmd ".mode column" telemetry.db \
  "SELECT ts, battery_pct, cpu_total, cpu_freq, load1, watts, drain_mah_per_min FROM training_view ORDER BY ts DESC LIMIT 20;"
```

How this helps ML:
- Typical supervised setup is regression:
  - `Y` (target) = `watts` (power draw) or `drain_mah_per_min` (battery drain rate).
  - `X` (features) = `cpu_total`, `cpu_freq`, `load1`, `load5`, `load15` (and optionally process-derived features shown below).
- Collect data under different real workloads and different power settings (CPU governor, screen brightness, radios on/off, etc.), then export `training_view` to a CSV for training.

Export to CSV (for training elsewhere):

```bash
sqlite3 -header -csv telemetry.db \
  "SELECT * FROM training_view WHERE watts IS NOT NULL" > training.csv
```

Optional: add simple process-level features for ML (based on the logged top-N list):

```sql
WITH proc AS (
  SELECT
    ts,
    SUM(cpu) AS topn_cpu_sum,
    MAX(cpu) AS top_cpu,
    SUM(mem) AS topn_mem_sum
  FROM process_sample
  GROUP BY ts
)
SELECT
  t.*,
  p.topn_cpu_sum,
  p.top_cpu,
  p.topn_mem_sum
FROM training_view t
LEFT JOIN proc p ON p.ts = t.ts
WHERE t.watts IS NOT NULL;
```

You can also derive labels over a window, like **energy used** (Wh) estimated from sampled watts (requires SQLite window functions):

```sql
WITH w AS (
  SELECT
    ts,
    watts,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts
  FROM training_view
  WHERE watts IS NOT NULL
)
SELECT
  SUM(watts * (ts - prev_ts) / 3600.0) AS watt_hours_est
FROM w
WHERE prev_ts IS NOT NULL;
```

## Run at boot (systemd service)

This repo includes:
- `telemetry-logger.service` (systemd unit)
- `install_service.sh` (installs + enables the unit)

Install and start at boot:

```bash
./install_service.sh
```

Useful commands:

```bash
systemctl status telemetry-logger.service
journalctl -u telemetry-logger.service -f
```

Service defaults (edit `telemetry-logger.service` to change):
- Database: `/var/lib/telemetry-logger/telemetry.db`
- Interval: 5 seconds
- Top processes: 10
- Power supply: `auto`
- Runs as user/group: `clockworkpi` (change `User=` / `Group=` if needed)

After editing:

```bash
sudo systemctl daemon-reload
sudo systemctl restart telemetry-logger.service
```

## Battery / power (Watts, current, mAh/min)

Raspberry Pi boards don’t have a built-in battery gauge. If you have a UPS HAT or PMIC driver that exposes measurements via Linux `power_supply` sysfs, this logger can auto-detect it.

Check what your system exposes:

```bash
ls /sys/class/power_supply
for d in /sys/class/power_supply/*; do echo "== $d =="; cat "$d/type"; done
```

If you see a `type` of `Battery`, the logger will use it by default (`--power-supply auto`) and will try to read:
- `voltage_now` (microvolts)
- `current_now` (microamps)
- `power_now` (microwatts) (optional; computed as V×A if missing)

You can also force a specific entry:

```bash
python3 logger.py --power-supply BAT0
```

Units stored in `system_sample`:
- `voltage` = volts (V)
- `current` = amps (A)
- `power` = watts (W). If `power_now` is missing/0, it is computed as `voltage * current` (so it may be negative depending on the driver’s sign convention).
- `battery_pct` = percent (0–100) if available (read from `capacity`)

To compute **mAh/min** from current (use `ABS()` if you only care about magnitude):

```sql
SELECT ts,
       current AS amps,
       (ABS(current) * 1000.0) / 60.0 AS mah_per_min,
       ABS(power) AS watts
FROM system_sample
ORDER BY ts DESC
LIMIT 20;
```

If your driver reports **negative current while discharging** (common), you can compute separate charge vs. drain rates:

```sql
SELECT ts,
       voltage,
       current,
       power,
       ABS(power) AS watts_abs,
       CASE WHEN current < 0 THEN (-current * 1000.0) / 60.0 ELSE 0 END AS drain_mah_per_min,
       CASE WHEN current > 0 THEN ( current * 1000.0) / 60.0 ELSE 0 END AS charge_mah_per_min
FROM system_sample
ORDER BY ts DESC
LIMIT 20;
```

## Database schema

WAL mode is enabled (`journal_mode=WAL`) and `synchronous=NORMAL` is used for lower write overhead.

Time reference:
- `ts` is Unix epoch seconds (`int(time.time())`) and is the primary key for `system_sample`.
- For safety, if two samples would have the same `ts`, the logger increments the timestamp to keep it unique and monotonic.

Tables:

1) `system_sample`
- `ts` (INTEGER PRIMARY KEY)
- `voltage` (REAL, nullable)
- `current` (REAL, nullable)
- `power` (REAL, nullable)
- `cpu_total` (REAL) — average of per-core CPU usage (%)
- `cpu_freq` (REAL) — current CPU frequency in MHz
- `load1` / `load5` / `load15` (REAL)

2) `cpu_core`
- `ts` (INTEGER)
- `core` (INTEGER)
- `usage` (REAL) — CPU usage (%) for that core over the last interval
- PRIMARY KEY (`ts`, `core`)

3) `process_sample`
- `ts` (INTEGER)
- `pid` (INTEGER)
- `name` (TEXT)
- `cpu` (REAL) — CPU usage (%) for the process over the last interval (can exceed 100 on multi-core)
- `mem` (REAL) — process memory usage as percent of total physical RAM (`psutil.Process.memory_percent()`)
- PRIMARY KEY (`ts`, `pid`)

## Example SQL queries

Battery % + drain rate (most recent samples):

```sql
SELECT ts, battery_pct, watts, drain_mah_per_min
FROM training_view
ORDER BY ts DESC
LIMIT 60;
```

Battery % change rate (percent per hour, requires SQLite window functions):

```sql
WITH x AS (
  SELECT
    ts,
    battery_pct,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
    LAG(battery_pct) OVER (ORDER BY ts) AS prev_pct
  FROM training_view
  WHERE battery_pct IS NOT NULL
)
SELECT
  ts,
  battery_pct,
  (battery_pct - prev_pct) / ((ts - prev_ts) / 3600.0) AS pct_per_hour
FROM x
WHERE prev_ts IS NOT NULL
ORDER BY ts DESC
LIMIT 60;
```

Average drain over the last ~10 minutes:

```sql
SELECT AVG(drain_mah_per_min) AS avg_drain_mah_per_min,
       AVG(watts) AS avg_watts
FROM training_view
WHERE ts >= (SELECT MAX(ts) - 600 FROM system_sample);
```

Quick CLI view (mAh/min drain + watts):

```bash
sqlite3 -cmd ".mode column" -cmd ".headers on" telemetry.db \
  "SELECT ts, battery_pct, watts, drain_mah_per_min FROM training_view ORDER BY ts DESC LIMIT 30;"
```

Most recent top processes (no manual timestamp needed):

```sql
SELECT pid, name, cpu, mem
FROM process_sample
WHERE ts = (SELECT MAX(ts) FROM system_sample)
ORDER BY cpu DESC;
```

Top process names overall (CPU-heavy apps):

```sql
SELECT name, COUNT(*) AS appearances, AVG(cpu) AS avg_cpu
FROM process_sample
GROUP BY name
ORDER BY avg_cpu DESC
LIMIT 20;
```

Correlate watts with the top processes at each timestamp:

```sql
SELECT s.ts, ABS(s.power) AS watts, p.pid, p.name, p.cpu, p.mem
FROM system_sample s
JOIN process_sample p ON p.ts = s.ts
WHERE s.ts >= (SELECT MAX(ts) - 600 FROM system_sample)
ORDER BY s.ts DESC, p.cpu DESC;
```

Top CPU processes at a given timestamp:

```sql
SELECT ts, pid, name, cpu, mem
FROM process_sample
WHERE ts = 1730000000
ORDER BY cpu DESC
LIMIT 10;
```

Correlate system CPU vs. top process CPU over time:

```sql
SELECT s.ts, s.cpu_total, p.pid, p.name, p.cpu
FROM system_sample s
JOIN process_sample p ON p.ts = s.ts
WHERE s.ts BETWEEN 1730000000 AND 1730003600
ORDER BY s.ts, p.cpu DESC;
```

Find CPU hotspots (processes frequently appearing in the top list):

```sql
SELECT name, COUNT(*) AS appearances, AVG(cpu) AS avg_cpu
FROM process_sample
GROUP BY name
ORDER BY appearances DESC, avg_cpu DESC
LIMIT 20;
```

Per-core usage over time:

```sql
SELECT ts, core, usage
FROM cpu_core
WHERE core = 0
ORDER BY ts;
```

Quick CLI view (using `sqlite3`):

```bash
sqlite3 -cmd ".mode column" -cmd ".headers on" telemetry.db \
  "SELECT pid, name, cpu, mem FROM process_sample WHERE ts = (SELECT MAX(ts) FROM system_sample) ORDER BY cpu DESC;"
```

## Battery / power integration

Battery readings are abstracted behind `BatterySensor` in `logger.py`. If a `power_supply` battery is detected (or specified), it is read from sysfs; otherwise the fallback returns `None` for battery fields.
