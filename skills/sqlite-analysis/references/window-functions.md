# SQLite Window Functions Reference

Comprehensive guide to window functions for analytical queries.

## Window Function Syntax

```sql
function_name(...) OVER (
  [PARTITION BY expr1, expr2, ...]
  [ORDER BY expr3, expr4, ...]
  [frame_spec]
)
```

**Components:**
- `PARTITION BY`: Divides rows into groups (optional)
- `ORDER BY`: Defines ordering within partition (required for most functions)
- `frame_spec`: Defines the window frame (ROWS or RANGE)

## Aggregate Window Functions

### Running Totals

```sql
SELECT ts, amount,
  SUM(amount) OVER (ORDER BY ts) AS running_total
FROM transactions;
```

With partitions:
```sql
SELECT category, ts, amount,
  SUM(amount) OVER (
    PARTITION BY category 
    ORDER BY ts
  ) AS category_running_total
FROM transactions;
```

### Moving Averages

3-row moving average:
```sql
SELECT ts, value,
  AVG(value) OVER (
    ORDER BY ts 
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
  ) AS ma_3
FROM measurements;
```

Centered moving average (5 rows):
```sql
SELECT ts, value,
  AVG(value) OVER (
    ORDER BY ts 
    ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
  ) AS centered_ma_5
FROM measurements;
```

### Cumulative Aggregates

```sql
SELECT ts,
  COUNT(*) OVER (ORDER BY ts) AS cumulative_count,
  SUM(value) OVER (ORDER BY ts) AS cumulative_sum,
  AVG(value) OVER (ORDER BY ts) AS cumulative_avg,
  MIN(value) OVER (ORDER BY ts) AS running_min,
  MAX(value) OVER (ORDER BY ts) AS running_max
FROM measurements;
```

## Row-Relative Functions

### LAG and LEAD

Previous and next values:
```sql
SELECT ts, value,
  LAG(value, 1) OVER (ORDER BY ts) AS prev_value,
  LEAD(value, 1) OVER (ORDER BY ts) AS next_value
FROM measurements;
```

Calculate deltas:
```sql
SELECT ts, value,
  value - LAG(value) OVER (ORDER BY ts) AS delta,
  value - LAG(value, 5) OVER (ORDER BY ts) AS delta_5_periods
FROM measurements;
```

With default for missing values:
```sql
SELECT ts, value,
  LAG(value, 1, 0) OVER (ORDER BY ts) AS prev_value_or_zero
FROM measurements;
```

### FIRST_VALUE and LAST_VALUE

First and last in window:
```sql
SELECT ts, value,
  FIRST_VALUE(value) OVER (
    ORDER BY ts 
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS first_value,
  LAST_VALUE(value) OVER (
    ORDER BY ts 
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
  ) AS last_value
FROM measurements;
```

**Important:** Default frame for LAST_VALUE is `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, which gives unexpected results. Always specify the frame explicitly.

### NTH_VALUE

Nth value in window:
```sql
SELECT ts, value,
  NTH_VALUE(value, 2) OVER (
    ORDER BY ts 
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS second_value
FROM measurements;
```

## Ranking Functions

### ROW_NUMBER

Sequential numbering:
```sql
SELECT ts, value,
  ROW_NUMBER() OVER (ORDER BY value DESC) AS row_num
FROM measurements;
```

Per-partition numbering:
```sql
SELECT category, ts, value,
  ROW_NUMBER() OVER (
    PARTITION BY category 
    ORDER BY value DESC
  ) AS rank_in_category
FROM measurements;
```

### RANK and DENSE_RANK

With gaps (RANK):
```sql
SELECT ts, value,
  RANK() OVER (ORDER BY value DESC) AS rank
FROM measurements;
-- Values: 100, 90, 90, 80
-- Ranks:  1,   2,  2,  4
```

Without gaps (DENSE_RANK):
```sql
SELECT ts, value,
  DENSE_RANK() OVER (ORDER BY value DESC) AS dense_rank
FROM measurements;
-- Values: 100, 90, 90, 80
-- Ranks:  1,   2,  2,  3
```

### PERCENT_RANK and CUME_DIST

Percentile rank (0 to 1):
```sql
SELECT value,
  PERCENT_RANK() OVER (ORDER BY value) AS pct_rank,
  CUME_DIST() OVER (ORDER BY value) AS cumulative_dist
FROM measurements;
```

### NTILE

Divide into N buckets:
```sql
SELECT ts, value,
  NTILE(4) OVER (ORDER BY value) AS quartile,
  NTILE(10) OVER (ORDER BY value) AS decile
FROM measurements;
```

## Frame Specifications

### ROWS vs RANGE

**ROWS:** Physical number of rows
```sql
-- 5 physical rows (current + 4 preceding)
AVG(value) OVER (
  ORDER BY ts 
  ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
)
```

**RANGE:** Logical range based on ORDER BY expression
```sql
-- All rows within 300 seconds
AVG(value) OVER (
  ORDER BY ts 
  RANGE BETWEEN 300 PRECEDING AND CURRENT ROW
)
```

### Frame Boundaries

```sql
-- Unbounded
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING

-- Fixed offset
ROWS BETWEEN 10 PRECEDING AND 5 FOLLOWING

-- Current row
ROWS BETWEEN CURRENT ROW AND 5 FOLLOWING

-- Everything before current
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Everything after current
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

### Default Frames

If no frame specified:
- **With ORDER BY:** `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`
- **Without ORDER BY:** `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`

## Practical Examples

### Top-N per Group

Top 3 values per category:
```sql
SELECT * FROM (
  SELECT category, ts, value,
    ROW_NUMBER() OVER (
      PARTITION BY category 
      ORDER BY value DESC
    ) AS rn
  FROM measurements
)
WHERE rn <= 3;
```

### Running Percentage

```sql
SELECT ts, amount,
  SUM(amount) OVER (ORDER BY ts) AS running_total,
  SUM(amount) OVER (ORDER BY ts) * 100.0 / 
    SUM(amount) OVER () AS pct_of_total
FROM transactions;
```

### Change Detection

Detect when value changes from previous:
```sql
SELECT ts, status,
  LAG(status) OVER (ORDER BY ts) AS prev_status,
  CASE 
    WHEN status != LAG(status) OVER (ORDER BY ts) THEN 1 
    ELSE 0 
  END AS changed
FROM events;
```

### Grouped Change Detection

Count consecutive same values:
```sql
WITH changes AS (
  SELECT ts, status,
    CASE 
      WHEN status != LAG(status) OVER (ORDER BY ts) THEN 1 
      ELSE 0 
    END AS is_change
  FROM events
),
groups AS (
  SELECT ts, status,
    SUM(is_change) OVER (ORDER BY ts) AS group_id
  FROM changes
)
SELECT group_id, status, 
  MIN(ts) AS start_ts, 
  MAX(ts) AS end_ts, 
  COUNT(*) AS duration
FROM groups
GROUP BY group_id, status
ORDER BY start_ts;
```

### Gap and Island Problem

Find continuous sequences:
```sql
WITH numbered AS (
  SELECT ts, value,
    ts - ROW_NUMBER() OVER (ORDER BY ts) AS island_id
  FROM measurements
  WHERE value > threshold
)
SELECT island_id,
  MIN(ts) AS island_start,
  MAX(ts) AS island_end,
  COUNT(*) AS island_length
FROM numbered
GROUP BY island_id
ORDER BY island_start;
```

## Performance Considerations

**Faster:**
- Window functions over single table
- Simple ORDER BY on indexed column
- ROWS frame (physical) over RANGE frame (logical)

**Slower:**
- Complex PARTITION BY with many groups
- ORDER BY on non-indexed column
- RANGE frames with complex calculations
- Nested window functions

**Optimization tips:**
1. Create indexes on PARTITION BY and ORDER BY columns
2. Use ROWS instead of RANGE when possible
3. Limit frame size (avoid UNBOUNDED when possible)
4. Filter data before window calculation (WHERE before window)
5. Consider materializing intermediate results in CTEs

## Common Pitfalls

### Wrong Frame for LAST_VALUE

**Wrong:**
```sql
LAST_VALUE(value) OVER (ORDER BY ts)
-- Uses default frame: UNBOUNDED PRECEDING to CURRENT ROW
-- Always returns current row's value!
```

**Correct:**
```sql
LAST_VALUE(value) OVER (
  ORDER BY ts 
  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

### Missing ORDER BY

```sql
-- Wrong: LAG requires ORDER BY
LAG(value) OVER (PARTITION BY category)

-- Correct:
LAG(value) OVER (PARTITION BY category ORDER BY ts)
```

### PARTITION BY vs GROUP BY

Window functions don't reduce rows (like GROUP BY does):
```sql
-- Returns all rows with running total
SELECT ts, amount,
  SUM(amount) OVER (ORDER BY ts) AS running_total
FROM transactions;

-- Returns one row with total
SELECT SUM(amount) AS total
FROM transactions;
```
