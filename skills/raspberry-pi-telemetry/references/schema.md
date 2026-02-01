# Database Schema Reference

Complete schema documentation for the Raspberry Pi telemetry SQLite database.

## Database Configuration

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA busy_timeout=5000;
```

**WAL Mode Benefits:**
- Concurrent readers don't block writers
- Better performance for write-heavy workloads
- `synchronous=NORMAL` balances safety and speed

## Table: system_sample

Core system-level metrics sampled every interval.

```sql
CREATE TABLE system_sample (
  ts INTEGER PRIMARY KEY,         -- Unix epoch seconds (monotonic, unique)
  voltage REAL,                   -- Battery voltage (V), NULL if unavailable
  current REAL,                   -- Battery current (A), NULL if unavailable
  power REAL,                     -- Power draw (W), NULL if unavailable
  battery_pct REAL,               -- Battery percentage 0-100, NULL if unavailable
  cpu_total REAL NOT NULL,        -- Average CPU usage across all cores (%)
  cpu_freq REAL NOT NULL,         -- Current CPU frequency (MHz)
  load1 REAL NOT NULL,            -- 1-minute load average
  load5 REAL NOT NULL,            -- 5-minute load average
  load15 REAL NOT NULL            -- 15-minute load average
);
```

**Key points:**
- `ts` is the primary key and timestamp reference for all tables
- Battery fields (`voltage`, `current`, `power`, `battery_pct`) are NULL when no battery detected or `--power-supply none`
- Logger ensures `ts` is monotonically increasing (increments if collision)
- `power` is computed as `voltage * current` if sysfs `power_now` is missing/zero

## Table: cpu_core

Per-core CPU usage for detailed analysis.

```sql
CREATE TABLE cpu_core (
  ts INTEGER NOT NULL,
  core INTEGER NOT NULL,
  usage REAL NOT NULL,            -- CPU usage (%) for this core over the interval
  PRIMARY KEY (ts, core),
  FOREIGN KEY (ts) REFERENCES system_sample(ts) ON DELETE CASCADE
);
```

**Key points:**
- One row per core per timestamp
- `core` is 0-indexed (0, 1, 2, 3 for quad-core)
- `usage` is from `psutil.cpu_percent(percpu=True)`, measured since last call
- CASCADE delete ensures cleanup when system_sample rows are deleted

## Table: process_sample

Top-N processes by CPU usage at each timestamp.

```sql
CREATE TABLE process_sample (
  ts INTEGER NOT NULL,
  pid INTEGER NOT NULL,
  name TEXT NOT NULL,
  cpu REAL NOT NULL,              -- CPU usage (%) over the interval (can exceed 100 on multi-core)
  mem REAL NOT NULL,              -- Memory usage as % of total physical RAM
  PRIMARY KEY (ts, pid),
  FOREIGN KEY (ts) REFERENCES system_sample(ts) ON DELETE CASCADE
);
```

**Key points:**
- Number of rows per `ts` = `--top-procs` argument (default: 10)
- `cpu` can exceed 100% on multi-core systems (e.g., 250% = 2.5 cores)
- `cpu` is computed from delta of process CPU time over wall time
- `mem` is from `psutil.Process.memory_percent()`
- Only captures top-N by CPU; low-CPU processes not logged

## View: training_view

ML-friendly denormalized view combining system metrics with derived battery features.

```sql
CREATE VIEW training_view AS
SELECT
  ts,
  cpu_total,
  cpu_freq,
  load1,
  load5,
  load15,
  voltage,
  current,
  power,
  battery_pct,
  ABS(power) AS watts,
  CASE
    WHEN current IS NULL THEN NULL
    WHEN current < 0 THEN (-current * 1000.0) / 60.0
    ELSE 0.0
  END AS drain_mah_per_min,
  CASE
    WHEN current IS NULL THEN NULL
    WHEN current > 0 THEN ( current * 1000.0) / 60.0
    ELSE 0.0
  END AS charge_mah_per_min
FROM system_sample;
```

**Computed columns:**
- `watts`: Absolute value of power (always positive magnitude)
- `drain_mah_per_min`: Battery drain rate when `current < 0` (discharging)
- `charge_mah_per_min`: Battery charge rate when `current > 0` (charging)

**ML use:**
- Features: `cpu_total`, `cpu_freq`, `load1`, `load5`, `load15`
- Targets: `watts`, `drain_mah_per_min`
- Export: `sqlite3 -header -csv db.db "SELECT * FROM training_view" > train.csv`

## Data Types and Ranges

| Column | Type | Range/Notes |
|--------|------|-------------|
| `ts` | INTEGER | Unix epoch seconds, >= 0 |
| `voltage` | REAL | Typically 3.0-5.2V for Li-ion/LiPo, NULL if unavailable |
| `current` | REAL | Driver-dependent sign (negative often = discharge), NULL if unavailable |
| `power` | REAL | Driver-dependent sign, NULL if unavailable |
| `battery_pct` | REAL | 0.0-100.0, NULL if unavailable |
| `cpu_total` | REAL | 0.0-100.0 (average across cores) |
| `cpu_freq` | REAL | MHz, 0.0 if unavailable |
| `load1/5/15` | REAL | >= 0.0 (can exceed CPU count) |
| `core` | INTEGER | 0-indexed core number |
| `usage` | REAL | 0.0-100.0 (per core) |
| `pid` | INTEGER | Process ID, > 0 |
| `cpu` (process) | REAL | >= 0.0 (can exceed 100 on multi-core) |
| `mem` | REAL | 0.0-100.0 (% of total RAM) |

## Schema Evolution Notes

**Adding `battery_pct` (forward-compatible):**
```sql
-- Older DBs missing battery_pct can be migrated
ALTER TABLE system_sample ADD COLUMN battery_pct REAL;
```

Logger automatically applies this migration on startup if the column is missing.

**Changing time resolution:**
Current schema uses integer epoch seconds (`ts`), limiting sampling to >= 1 second intervals. To support sub-second sampling, the schema would need:
- Change `ts` to REAL (float seconds)
- Adjust PRIMARY KEY constraints
- Update all SQL queries expecting integer timestamps

## Query Performance Tips

**Index recommendations:**
- `ts` is already indexed (PRIMARY KEY)
- For frequent process name lookups: `CREATE INDEX idx_proc_name ON process_sample(name);`
- For time-range queries on cores: `CREATE INDEX idx_core_ts ON cpu_core(ts);`

**Efficient time-range queries:**
```sql
-- Good: uses ts index
SELECT * FROM system_sample WHERE ts >= 1730000000 AND ts < 1730003600;

-- Avoid: full table scan
SELECT * FROM system_sample WHERE datetime(ts, 'unixepoch') >= '2024-10-27';
```

**Join optimization:**
Always join on `ts` (indexed):
```sql
-- Efficient join
SELECT s.ts, s.watts, p.name, p.cpu
FROM training_view s
JOIN process_sample p ON p.ts = s.ts;
```
