#!/usr/bin/env python3
"""
Export ML-ready feature matrix from telemetry database.

Combines system metrics with process-level aggregates and optional lag features.
"""

import argparse
import csv
import sqlite3
import sys
from typing import Optional


def export_features(
    db_path: str,
    output_path: str,
    include_lags: bool = False,
    lag_periods: Optional[list[int]] = None
) -> None:
    """Export features to CSV."""
    conn = sqlite3.connect(db_path)
    
    try:
        # Base query with process aggregates
        base_query = """
        WITH proc_agg AS (
          SELECT ts,
            SUM(cpu) AS total_proc_cpu,
            MAX(cpu) AS max_proc_cpu,
            SUM(mem) AS total_proc_mem,
            COUNT(*) AS num_procs
          FROM process_sample
          GROUP BY ts
        )
        SELECT
          t.ts,
          t.cpu_total,
          t.cpu_freq,
          t.load1, t.load5, t.load15,
          t.battery_pct,
          t.voltage,
          t.current,
          t.watts,
          t.drain_mah_per_min,
          t.charge_mah_per_min,
          COALESCE(p.total_proc_cpu, 0) AS total_proc_cpu,
          COALESCE(p.max_proc_cpu, 0) AS max_proc_cpu,
          COALESCE(p.total_proc_mem, 0) AS total_proc_mem,
          COALESCE(p.num_procs, 0) AS num_procs
        FROM training_view t
        LEFT JOIN proc_agg p ON p.ts = t.ts
        WHERE t.watts IS NOT NULL
        ORDER BY t.ts
        """
        
        if include_lags and lag_periods:
            # Build lag columns
            lag_cols = []
            for period in lag_periods:
                lag_cols.append(
                    f"LAG(t.watts, {period}) OVER (ORDER BY t.ts) AS watts_lag{period}"
                )
                lag_cols.append(
                    f"LAG(t.cpu_total, {period}) OVER (ORDER BY t.ts) AS cpu_total_lag{period}"
                )
            
            lag_select = ",\n          ".join(lag_cols)
            
            # Wrap base query to add lags
            query = f"""
            WITH base AS ({base_query})
            SELECT base.*,
              {lag_select}
            FROM base
            """
            
            # Filter out rows with NULL lags (first N rows)
            max_lag = max(lag_periods)
            query += f"\nWHERE watts_lag{max_lag} IS NOT NULL"
        else:
            query = base_query
        
        # Execute and write CSV
        cursor = conn.execute(query)
        
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            columns = [desc[0] for desc in cursor.description]
            writer.writerow(columns)
            
            # Write data
            row_count = 0
            for row in cursor:
                writer.writerow(row)
                row_count += 1
        
        print(f"Exported {row_count} rows to {output_path}")
        print(f"Columns: {', '.join(columns)}")
        
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export ML features from telemetry database"
    )
    parser.add_argument(
        "db",
        help="Path to telemetry database"
    )
    parser.add_argument(
        "-o", "--output",
        default="features.csv",
        help="Output CSV file (default: features.csv)"
    )
    parser.add_argument(
        "--lags",
        action="store_true",
        help="Include lagged features for time-series models"
    )
    parser.add_argument(
        "--lag-periods",
        type=int,
        nargs="+",
        default=[1, 2, 6, 12],
        help="Lag periods to include (default: 1 2 6 12 = 5s, 10s, 30s, 1min @ 5s sampling)"
    )
    
    args = parser.parse_args()
    
    try:
        export_features(
            args.db,
            args.output,
            include_lags=args.lags,
            lag_periods=args.lag_periods if args.lags else None
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
