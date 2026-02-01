---
name: sqlite-analysis
description: Analyze and query SQLite databases, particularly time-series telemetry data. Use when the user needs to explore SQLite database schemas, write complex analytical queries, optimize query performance, debug data quality issues, generate reports from SQLite data, or work with time-series analysis patterns including window functions, aggregations, and correlations.
---

# SQLite Analysis

Comprehensive SQLite querying and analysis, specialized for time-series telemetry and analytical workloads.

## Quick Database Inspection

### Schema Discovery

List all tables and views:
```bash
sqlite3 database.db "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name;"
```

View table schema:
```bash
sqlite3 database.db "PRAGMA table_info(table_name);"
```

Show indexes:
```bash
sqlite3 database.db "PRAGMA index_list(table_name);"
```

Database statistics:
```bash
sqlite3 database.db "
SELECT name, type, 
  (SELECT COUNT(*) FROM \`name\`) AS row_count 
FROM sqlite_master 
WHERE type='table';"
```

### Interactive Exploration

Launch interactive shell with headers and column mode:
```bash
sqlite3 -cmd ".mode column" -cmd ".headers on" database.db
```

Common `.` commands in sqlite3 shell:
- `.tables` - List all tables
- `.schema table_name` - Show CREATE statement
- `.mode csv` - Switch to CSV output
- `.output file.csv` - Redirect output to file
- `.read script.sql` - Execute SQL from file
- `.quit` - Exit

## Time-Series Query Patterns

### Window Functions

**Rolling aggregates:**
```sql
SELECT ts, value,
  AVG(value) OVER (
    ORDER BY ts 
    ROWS BETWEEN 10 PRECEDING AND CURRENT ROW
  ) AS moving_avg_10
FROM measurements;
```

**Previous/next values:**
```sql
SELECT ts, value,
  LAG(value) OVER (ORDER BY ts) AS prev_value,
  LEAD(value) OVER (ORDER BY ts) AS next_value
FROM measurements;
```

**Row numbering and ranking:**
```sql
SELECT ts, value,
  ROW_NUMBER() OVER (ORDER BY value DESC) AS rank,
  DENSE_RANK() OVER (ORDER BY value DESC) AS dense_rank
FROM measurements;
```

### Time-Based Grouping

Group by 5-minute intervals:
```sql
SELECT 
  (ts / 300) * 300 AS interval_start,
  COUNT(*) AS samples,
  AVG(value) AS avg_value
FROM measurements
GROUP BY interval_start;
```

Group by hour:
```sql
SELECT
  strftime('%Y-%m-%d %H:00:00', datetime(ts, 'unixepoch')) AS hour,
  AVG(value) AS avg_value
FROM measurements
GROUP BY hour;
```

### Gap Detection

Find missing data:
```sql
WITH gaps AS (
  SELECT ts,
    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
    ts - LAG(ts) OVER (ORDER BY ts) AS gap_seconds
  FROM measurements
)
SELECT * FROM gaps 
WHERE gap_seconds > 60  -- Expected 5s interval
ORDER BY gap_seconds DESC;
```

## Analytical Query Patterns

### Correlation Analysis

Cross-correlate two metrics:
```sql
WITH stats AS (
  SELECT 
    AVG(metric_a) AS avg_a, 
    AVG(metric_b) AS avg_b
  FROM data
),
deviations AS (
  SELECT 
    (metric_a - stats.avg_a) AS dev_a,
    (metric_b - stats.avg_b) AS dev_b
  FROM data, stats
)
SELECT 
  SUM(dev_a * dev_b) / 
  (SQRT(SUM(dev_a * dev_a)) * SQRT(SUM(dev_b * dev_b))) 
  AS correlation
FROM deviations;
```

### Percentiles and Quantiles

Using window functions (SQLite 3.25+):
```sql
SELECT DISTINCT
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY value) OVER () AS q1,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY value) OVER () AS median,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY value) OVER () AS q3,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) OVER () AS p95
FROM measurements;
```

Manual percentile calculation:
```sql
WITH ranked AS (
  SELECT value,
    ROW_NUMBER() OVER (ORDER BY value) AS rn,
    COUNT(*) OVER () AS total
  FROM measurements
)
SELECT value AS median
FROM ranked
WHERE rn = (total + 1) / 2;
```

### Trend Detection

Simple linear trend (slope):
```sql
WITH indexed AS (
  SELECT ts, value,
    ROW_NUMBER() OVER (ORDER BY ts) AS idx
  FROM measurements
),
stats AS (
  SELECT 
    AVG(idx) AS avg_x,
    AVG(value) AS avg_y,
    COUNT(*) AS n
  FROM indexed
)
SELECT 
  SUM((idx - stats.avg_x) * (value - stats.avg_y)) / 
  SUM((idx - stats.avg_x) * (idx - stats.avg_x)) AS slope
FROM indexed, stats;
```

## Performance Optimization

### Index Strategies

Create index on timestamp column:
```sql
CREATE INDEX idx_ts ON measurements(ts);
```

Composite index for filtered queries:
```sql
CREATE INDEX idx_ts_category ON events(ts, category);
```

Check if query uses index:
```sql
EXPLAIN QUERY PLAN
SELECT * FROM measurements WHERE ts > 1700000000;
```

### Query Optimization Tips

**Do:**
- Use indexes on columns in WHERE, JOIN, and ORDER BY
- Filter early with WHERE before JOIN
- Use BETWEEN for range queries on indexed columns
- Limit result sets with LIMIT
- Use prepared statements for repeated queries

**Avoid:**
- Functions on indexed columns in WHERE (breaks index use)
- `SELECT *` when you only need specific columns
- Unnecessary ORDER BY (especially without LIMIT)
- String operations (LIKE '%pattern%') at query time

**Example - Good:**
```sql
SELECT ts, value FROM measurements 
WHERE ts >= 1700000000 AND ts < 1700003600
ORDER BY ts LIMIT 1000;
```

**Example - Bad (doesn't use ts index):**
```sql
SELECT * FROM measurements 
WHERE datetime(ts, 'unixepoch') >= '2023-11-15'
ORDER BY value;
```

### Batch Operations

Wrap bulk updates in transaction:
```sql
BEGIN TRANSACTION;
UPDATE measurements SET processed = 1 WHERE category = 'A';
UPDATE measurements SET processed = 1 WHERE category = 'B';
COMMIT;
```

Use INSERT with multiple VALUES:
```sql
INSERT INTO measurements (ts, value) VALUES
  (1700000000, 1.5),
  (1700000005, 2.3),
  (1700000010, 1.8);
```

## Data Quality Checks

### Null and Missing Data

Count nulls by column:
```sql
SELECT 
  SUM(CASE WHEN col1 IS NULL THEN 1 ELSE 0 END) AS col1_nulls,
  SUM(CASE WHEN col2 IS NULL THEN 1 ELSE 0 END) AS col2_nulls,
  COUNT(*) AS total_rows
FROM table_name;
```

### Duplicate Detection

Find duplicate timestamps:
```sql
SELECT ts, COUNT(*) AS duplicates
FROM measurements
GROUP BY ts
HAVING COUNT(*) > 1
ORDER BY duplicates DESC;
```

### Outlier Detection

Using IQR method:
```sql
WITH quartiles AS (
  SELECT 
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY value) OVER () AS q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY value) OVER () AS q3
  FROM measurements
),
bounds AS (
  SELECT DISTINCT
    q1 - 1.5 * (q3 - q1) AS lower_bound,
    q3 + 1.5 * (q3 - q1) AS upper_bound
  FROM quartiles
)
SELECT ts, value
FROM measurements, bounds
WHERE value < lower_bound OR value > upper_bound;
```

## Exporting and Reporting

### Export to CSV

From command line:
```bash
sqlite3 -header -csv database.db "SELECT * FROM measurements" > output.csv
```

From SQL:
```sql
.mode csv
.output report.csv
SELECT * FROM measurements;
.output stdout
```

### Generate Summary Reports

```bash
sqlite3 -cmd ".mode column" -cmd ".headers on" database.db > report.txt << 'EOF'
.print "========== DATABASE SUMMARY =========="
.print ""

SELECT 'Total Tables:' AS metric, COUNT(*) AS value
FROM sqlite_master WHERE type='table';

.print ""
.print "========== TABLE ROW COUNTS =========="
.print ""

SELECT name AS table_name, 
  (SELECT COUNT(*) FROM sqlite_master sm WHERE sm.name = m.name) AS rows
FROM sqlite_master m
WHERE type='table';
EOF
```

## Advanced Patterns

### Recursive CTEs

Generate date sequence:
```sql
WITH RECURSIVE dates(ts) AS (
  SELECT 1700000000
  UNION ALL
  SELECT ts + 86400 FROM dates WHERE ts < 1700259600
)
SELECT ts, datetime(ts, 'unixepoch') AS date FROM dates;
```

Hierarchical queries:
```sql
WITH RECURSIVE hierarchy AS (
  SELECT id, parent_id, name, 0 AS level
  FROM categories WHERE parent_id IS NULL
  UNION ALL
  SELECT c.id, c.parent_id, c.name, h.level + 1
  FROM categories c
  JOIN hierarchy h ON c.parent_id = h.id
)
SELECT * FROM hierarchy ORDER BY level, name;
```

### JSON Support (SQLite 3.38+)

Extract from JSON column:
```sql
SELECT 
  json_extract(data, '$.temperature') AS temp,
  json_extract(data, '$.humidity') AS humidity
FROM sensor_readings;
```

Build JSON array:
```sql
SELECT json_group_array(
  json_object('ts', ts, 'value', value)
) AS readings
FROM measurements;
```

## Troubleshooting

### Database Locked Errors

Check WAL mode:
```sql
PRAGMA journal_mode;
```

Enable WAL mode (better concurrency):
```sql
PRAGMA journal_mode=WAL;
```

Set busy timeout:
```sql
PRAGMA busy_timeout=5000;  -- 5 seconds
```

### Slow Queries

Analyze query plan:
```sql
EXPLAIN QUERY PLAN
SELECT * FROM measurements WHERE ts > 1700000000;
```

Gather statistics:
```sql
ANALYZE;
```

### Database Corruption

Check integrity:
```sql
PRAGMA integrity_check;
```

Quick check:
```sql
PRAGMA quick_check;
```

## Resources

For more advanced patterns:
- **references/window-functions.md**: Comprehensive window function examples
- **references/optimization.md**: Performance tuning techniques
- **scripts/query_builder.py**: Generate complex queries programmatically
