#!/usr/bin/env python3
"""
Automated battery analysis for telemetry databases.

Generates summary statistics and insights about battery drain patterns.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import Optional


def analyze_battery(db_path: str, hours: Optional[int] = None) -> None:
    """Analyze battery data and print report."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Get time range
        if hours:
            cutoff_query = f"SELECT MAX(ts) - {hours * 3600} AS cutoff FROM system_sample"
            cutoff_ts = conn.execute(cutoff_query).fetchone()["cutoff"]
            time_filter = f"WHERE ts >= {cutoff_ts}"
            period_desc = f"last {hours} hours"
        else:
            time_filter = ""
            period_desc = "all data"
        
        # Basic stats
        stats_query = f"""
        SELECT
            COUNT(*) AS sample_count,
            MIN(ts) AS start_ts,
            MAX(ts) AS end_ts,
            AVG(watts) AS avg_watts,
            MIN(watts) AS min_watts,
            MAX(watts) AS max_watts,
            AVG(drain_mah_per_min) AS avg_drain,
            AVG(battery_pct) AS avg_battery_pct,
            MIN(battery_pct) AS min_battery_pct,
            MAX(battery_pct) AS max_battery_pct
        FROM training_view
        {time_filter} AND watts IS NOT NULL
        """
        stats = conn.execute(stats_query).fetchone()
        
        if not stats or stats["sample_count"] == 0:
            print(f"No battery data found for {period_desc}")
            return
        
        # Calculate duration
        duration_s = stats["end_ts"] - stats["start_ts"]
        duration_h = duration_s / 3600.0
        
        # Print header
        print("=" * 70)
        print("BATTERY ANALYSIS REPORT")
        print("=" * 70)
        print(f"\nPeriod: {period_desc}")
        print(f"Start: {datetime.fromtimestamp(stats['start_ts']).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End:   {datetime.fromtimestamp(stats['end_ts']).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {duration_h:.2f} hours ({stats['sample_count']} samples)")
        
        # Power consumption
        print("\n" + "-" * 70)
        print("POWER CONSUMPTION")
        print("-" * 70)
        print(f"Average power: {stats['avg_watts']:.2f} W")
        print(f"Min power:     {stats['min_watts']:.2f} W")
        print(f"Max power:     {stats['max_watts']:.2f} W")
        
        if stats["avg_drain"] is not None:
            print(f"Average drain: {stats['avg_drain']:.2f} mAh/min")
            print(f"Hourly drain:  {stats['avg_drain'] * 60:.2f} mAh/hour")
        
        # Battery level
        if stats["avg_battery_pct"] is not None:
            print("\n" + "-" * 70)
            print("BATTERY LEVEL")
            print("-" * 70)
            print(f"Average:  {stats['avg_battery_pct']:.1f}%")
            print(f"Min:      {stats['min_battery_pct']:.1f}%")
            print(f"Max:      {stats['max_battery_pct']:.1f}%")
            
            pct_change = stats["max_battery_pct"] - stats["min_battery_pct"]
            if duration_h > 0:
                pct_per_hour = pct_change / duration_h
                print(f"Change:   {pct_change:.1f}% ({pct_per_hour:.2f}%/hour)")
        
        # Estimated battery life (assume 5000 mAh battery)
        if stats["avg_drain"] is not None and stats["avg_drain"] > 0:
            battery_capacity_mah = 5000
            life_minutes = battery_capacity_mah / stats["avg_drain"]
            life_hours = life_minutes / 60.0
            
            print("\n" + "-" * 70)
            print("ESTIMATED BATTERY LIFE (assuming 5000 mAh capacity)")
            print("-" * 70)
            print(f"At current avg drain: {life_hours:.2f} hours ({life_minutes:.0f} minutes)")
        
        # Load patterns
        load_query = f"""
        SELECT
            CASE
                WHEN cpu_total < 10 THEN 'Idle (<10%)'
                WHEN cpu_total < 30 THEN 'Light (10-30%)'
                WHEN cpu_total < 60 THEN 'Medium (30-60%)'
                WHEN cpu_total < 80 THEN 'High (60-80%)'
                ELSE 'Very High (>80%)'
            END AS load_category,
            COUNT(*) AS samples,
            AVG(watts) AS avg_watts,
            AVG(cpu_total) AS avg_cpu
        FROM training_view
        {time_filter} AND watts IS NOT NULL
        GROUP BY load_category
        ORDER BY avg_cpu
        """
        
        print("\n" + "-" * 70)
        print("POWER BY LOAD CATEGORY")
        print("-" * 70)
        print(f"{'Category':<20} {'Samples':<10} {'Avg Watts':<12} {'Avg CPU':<10}")
        print("-" * 70)
        
        for row in conn.execute(load_query):
            print(f"{row['load_category']:<20} {row['samples']:<10} "
                  f"{row['avg_watts']:>10.2f} W  {row['avg_cpu']:>8.1f}%")
        
        # Top power-consuming processes
        proc_query = f"""
        SELECT p.name,
            COUNT(*) AS appearances,
            AVG(s.watts) AS avg_watts,
            AVG(p.cpu) AS avg_cpu
        FROM process_sample p
        JOIN training_view s ON s.ts = p.ts
        {time_filter.replace('WHERE', 'WHERE s.ts IS NOT NULL AND')} AND s.watts IS NOT NULL
        GROUP BY p.name
        HAVING appearances > 5
        ORDER BY avg_watts DESC
        LIMIT 10
        """
        
        print("\n" + "-" * 70)
        print("TOP POWER-CONSUMING PROCESSES")
        print("-" * 70)
        print(f"{'Process':<25} {'Appearances':<13} {'Avg Watts':<12} {'Avg CPU':<10}")
        print("-" * 70)
        
        for row in conn.execute(proc_query):
            print(f"{row['name']:<25} {row['appearances']:<13} "
                  f"{row['avg_watts']:>10.2f} W  {row['avg_cpu']:>8.1f}%")
        
        print("\n" + "=" * 70)
        
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze battery telemetry data"
    )
    parser.add_argument(
        "db",
        help="Path to telemetry database"
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Limit analysis to last N hours (default: all data)"
    )
    
    args = parser.parse_args()
    
    try:
        analyze_battery(args.db, args.hours)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
