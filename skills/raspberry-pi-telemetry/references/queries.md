# Advanced SQL Query Patterns

Complex analytics queries for telemetry data.

## Time-Series Analysis

### Rolling Averages

10-minute rolling average of power consumption:
```sql
WITH samples AS (
  SELECT ts, watts,
    ROW_NUMBER() OVER (ORDER BY ts) AS rn
  FROM training_view WHERE watts IS NOT NULL
)
SELECT s1.ts, s1.watts,
  AVG(s2.watts) AS avg_watts_10min
FROM samples s1
JOIN samples s2 ON s2.rn BETWEEN s1.rn - 120 AND s1.rn  -- 10 min = 120 samples @ 5s
GROUP BY s1.ts, s1.watts
ORDER BY s1.ts DESC;
```

### Rate of Change

Battery drain acceleration (mAh/min change per hour):
```sql
WITH drain AS (
  SELECT ts, drain_mah_per_min,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
    LAG(drain_mah_per_min) OVER (ORDER BY ts) AS prev_drain
  FROM training_view WHERE drain_mah_per_min > 0
)
SELECT ts, drain_mah_per_min,
  (drain_mah_per_min - prev_drain) / ((ts - prev_ts) / 3600.0) AS drain_accel
FROM drain WHERE prev_ts IS NOT NULL
ORDER BY ts DESC;
```

## Process Correlation Analysis

### Power per Process

Correlate specific processes with power draw:
```sql
SELECT p.name,
  COUNT(*) AS samples,
  AVG(s.watts) AS avg_watts_when_present,
  AVG(p.cpu) AS avg_cpu
FROM process_sample p
JOIN training_view s ON s.ts = p.ts
WHERE s.watts IS NOT NULL
GROUP BY p.name
HAVING samples > 10
ORDER BY avg_watts_when_present DESC;
```

### Process Impact on Battery

Compare drain rates with vs. without specific process:
```sql
WITH firefox_samples AS (
  SELECT DISTINCT ts FROM process_sample WHERE name = 'firefox'
)
SELECT
  CASE WHEN f.ts IS NOT NULL THEN 'Firefox running' ELSE 'Firefox not running' END AS status,
  COUNT(*) AS samples,
  AVG(t.drain_mah_per_min) AS avg_drain,
  AVG(t.watts) AS avg_watts
FROM training_view t
LEFT JOIN firefox_samples f ON f.ts = t.ts
WHERE t.drain_mah_per_min IS NOT NULL
GROUP BY CASE WHEN f.ts IS NOT NULL THEN 'Firefox running' ELSE 'Firefox not running' END;
```

### Top Process Co-occurrences

Find processes that frequently run together:
```sql
WITH pairs AS (
  SELECT p1.name AS proc1, p2.name AS proc2, p1.ts
  FROM process_sample p1
  JOIN process_sample p2 ON p2.ts = p1.ts AND p2.name > p1.name
)
SELECT proc1, proc2, COUNT(*) AS co_occur_count
FROM pairs
GROUP BY proc1, proc2
HAVING co_occur_count > 20
ORDER BY co_occur_count DESC
LIMIT 30;
```

## Battery Life Predictions

### Estimated Time to Empty

Based on current drain rate:
```sql
WITH latest AS (
  SELECT battery_pct, drain_mah_per_min
  FROM training_view
  WHERE drain_mah_per_min > 0
  ORDER BY ts DESC LIMIT 1
)
SELECT
  battery_pct,
  drain_mah_per_min,
  -- Assume 5000 mAh total capacity (adjust for your battery)
  (battery_pct / 100.0) * 5000.0 AS remaining_mah,
  ((battery_pct / 100.0) * 5000.0) / drain_mah_per_min AS minutes_remaining,
  ((battery_pct / 100.0) * 5000.0) / drain_mah_per_min / 60.0 AS hours_remaining
FROM latest;
```

### Battery Discharge Curve

Model battery % over time (requires sufficient discharge data):
```sql
SELECT
  battery_pct,
  AVG(drain_mah_per_min) AS avg_drain_at_this_pct,
  COUNT(*) AS samples
FROM training_view
WHERE drain_mah_per_min > 0
GROUP BY CAST(battery_pct AS INTEGER)
ORDER BY battery_pct DESC;
```

## CPU Frequency Analysis

### Frequency vs Power Relationship

Analyze power scaling across CPU frequencies:
```sql
SELECT
  ROUND(cpu_freq / 100) * 100 AS freq_bucket_mhz,
  COUNT(*) AS samples,
  AVG(watts) AS avg_watts,
  AVG(cpu_total) AS avg_cpu_usage
FROM training_view
WHERE watts IS NOT NULL AND cpu_freq > 0
GROUP BY ROUND(cpu_freq / 100)
ORDER BY freq_bucket_mhz;
```

### Throttling Detection

Find periods of thermal throttling (freq drop despite load):
```sql
SELECT ts, cpu_total, cpu_freq, watts,
  LAG(cpu_freq) OVER (ORDER BY ts) AS prev_freq
FROM training_view
WHERE cpu_total > 70
  AND cpu_freq < 0.8 * (SELECT MAX(cpu_freq) FROM training_view)
ORDER BY ts DESC;
```

## Load Pattern Analysis

### Daily Load Patterns

Average load by hour of day:
```sql
SELECT
  CAST(strftime('%H', datetime(ts, 'unixepoch', 'localtime')) AS INTEGER) AS hour,
  AVG(load1) AS avg_load1,
  AVG(cpu_total) AS avg_cpu,
  AVG(watts) AS avg_watts
FROM training_view
WHERE watts IS NOT NULL
GROUP BY hour
ORDER BY hour;
```

### Load Spikes

Identify sudden load increases:
```sql
WITH load_changes AS (
  SELECT ts, load1,
    LAG(load1) OVER (ORDER BY ts) AS prev_load,
    load1 - LAG(load1) OVER (ORDER BY ts) AS load_delta
  FROM system_sample
)
SELECT ts, load1, prev_load, load_delta
FROM load_changes
WHERE load_delta > 2.0  -- Spike threshold
ORDER BY load_delta DESC
LIMIT 50;
```

## Multi-Core Utilization

### Core Balance

Check if load is balanced across cores:
```sql
SELECT
  ts,
  MAX(usage) - MIN(usage) AS core_usage_spread,
  AVG(usage) AS avg_core_usage
FROM cpu_core
GROUP BY ts
HAVING core_usage_spread > 30  -- Imbalance threshold
ORDER BY core_usage_spread DESC
LIMIT 100;
```

### Core-Specific Hotspots

Find which cores are used most:
```sql
SELECT core,
  COUNT(*) AS samples,
  AVG(usage) AS avg_usage,
  MAX(usage) AS max_usage
FROM cpu_core
GROUP BY core
ORDER BY avg_usage DESC;
```

## Energy Efficiency Metrics

### Watts per Unit Work

Estimate energy efficiency (lower is better):
```sql
SELECT
  CAST(load1 AS INTEGER) AS load_bucket,
  AVG(watts) AS avg_watts,
  AVG(watts / NULLIF(load1, 0)) AS watts_per_unit_load
FROM training_view
WHERE watts IS NOT NULL AND load1 > 0
GROUP BY CAST(load1 AS INTEGER)
ORDER BY load_bucket;
```

### Idle vs Active Power

Compare baseline idle power to active power:
```sql
SELECT
  CASE
    WHEN cpu_total < 10 AND load1 < 0.5 THEN 'Idle'
    WHEN cpu_total BETWEEN 10 AND 50 THEN 'Light'
    WHEN cpu_total BETWEEN 50 AND 80 THEN 'Medium'
    ELSE 'Heavy'
  END AS load_category,
  COUNT(*) AS samples,
  AVG(watts) AS avg_watts,
  MIN(watts) AS min_watts,
  MAX(watts) AS max_watts
FROM training_view
WHERE watts IS NOT NULL
GROUP BY load_category
ORDER BY avg_watts;
```

## Data Export Patterns

### ML Feature Matrix with Process Aggregates

Complete feature set for training:
```sql
WITH proc_agg AS (
  SELECT ts,
    SUM(cpu) AS total_proc_cpu,
    MAX(cpu) AS max_proc_cpu,
    SUM(mem) AS total_proc_mem,
    COUNT(*) AS num_procs,
    GROUP_CONCAT(name, ',') AS proc_list
  FROM process_sample
  GROUP BY ts
)
SELECT
  t.ts,
  t.cpu_total,
  t.cpu_freq,
  t.load1, t.load5, t.load15,
  t.battery_pct,
  t.watts,
  t.drain_mah_per_min,
  COALESCE(p.total_proc_cpu, 0) AS total_proc_cpu,
  COALESCE(p.max_proc_cpu, 0) AS max_proc_cpu,
  COALESCE(p.total_proc_mem, 0) AS total_proc_mem,
  COALESCE(p.num_procs, 0) AS num_procs
FROM training_view t
LEFT JOIN proc_agg p ON p.ts = t.ts
WHERE t.watts IS NOT NULL;
```

### Time-Windowed Features

Create lagged features for sequence models:
```sql
WITH lagged AS (
  SELECT ts, watts,
    LAG(watts, 1) OVER (ORDER BY ts) AS watts_lag1,
    LAG(watts, 2) OVER (ORDER BY ts) AS watts_lag2,
    LAG(watts, 6) OVER (ORDER BY ts) AS watts_lag30s,  -- 6 samples * 5s
    LAG(watts, 12) OVER (ORDER BY ts) AS watts_lag1min
  FROM training_view WHERE watts IS NOT NULL
)
SELECT * FROM lagged WHERE watts_lag1min IS NOT NULL;
```

## Debugging Queries

### Check Data Quality

Find gaps in sampling:
```sql
WITH gaps AS (
  SELECT ts,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
    ts - LAG(ts) OVER (ORDER BY ts) AS gap_seconds
  FROM system_sample
)
SELECT ts, prev_ts, gap_seconds
FROM gaps
WHERE gap_seconds > 10  -- Expected 5s, flag >10s gaps
ORDER BY gap_seconds DESC;
```

### NULL Battery Data Counts

```sql
SELECT
  COUNT(*) AS total_samples,
  SUM(CASE WHEN voltage IS NULL THEN 1 ELSE 0 END) AS null_voltage,
  SUM(CASE WHEN watts IS NULL THEN 1 ELSE 0 END) AS null_watts,
  SUM(CASE WHEN battery_pct IS NULL THEN 1 ELSE 0 END) AS null_battery_pct
FROM system_sample;
```
