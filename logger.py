#!/usr/bin/env python3
"""
Raspberry Pi telemetry logger.

Logs system metrics every N seconds into a SQLite database for later analysis.

Design goals:
- Low overhead: single process, single SQLite connection, one commit per interval.
- Reproducible on Raspberry Pi OS: standard library + psutil (from apt).
- Extensible: battery/power readings are abstracted behind a small interface.
"""

from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    import psutil
except ModuleNotFoundError as e:
    raise SystemExit(
        "psutil is required. On Raspberry Pi OS, install it with:\n"
        "  sudo apt update && sudo apt install -y python3-psutil\n"
    ) from e


@dataclass(frozen=True)
class BatteryReading:
    voltage: Optional[float] = None
    current: Optional[float] = None
    power: Optional[float] = None
    battery_pct: Optional[float] = None


class BatterySensor:
    def read(self) -> BatteryReading:
        raise NotImplementedError


class NullBatterySensor(BatterySensor):
    def read(self) -> BatteryReading:
        return BatteryReading()


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    txt = _read_text(path)
    if txt is None:
        return None
    try:
        return int(txt)
    except ValueError:
        return None


class SysfsPowerSupplyBatterySensor(BatterySensor):
    """
    Reads battery/power from Linux power_supply sysfs (common on UPS HATs and SBC PMICs).

    Units returned:
    - voltage: volts (V)
    - current: amps (A) (sign is driver-dependent)
    - power: watts (W)
    """

    def __init__(self, power_supply_name: str) -> None:
        self._base = os.path.join("/sys/class/power_supply", power_supply_name)

    @staticmethod
    def auto_detect() -> Optional["SysfsPowerSupplyBatterySensor"]:
        base = "/sys/class/power_supply"
        try:
            entries = sorted(os.listdir(base))
        except OSError:
            return None

        for name in entries:
            t = _read_text(os.path.join(base, name, "type"))
            if t == "Battery":
                return SysfsPowerSupplyBatterySensor(name)
        return None

    def read(self) -> BatteryReading:
        voltage_uv = _read_int(os.path.join(self._base, "voltage_now"))
        current_ua = _read_int(os.path.join(self._base, "current_now"))
        power_uw = _read_int(os.path.join(self._base, "power_now"))
        capacity_pct = _read_int(os.path.join(self._base, "capacity"))

        voltage_v = None if voltage_uv is None else float(voltage_uv) / 1_000_000.0
        current_a = None if current_ua is None else float(current_ua) / 1_000_000.0

        power_w = None
        # Some drivers expose power_now but always report 0. If so, fall back to V*A.
        if power_uw is not None and power_uw != 0:
            power_w = float(power_uw) / 1_000_000.0
        elif voltage_v is not None and current_a is not None:
            power_w = voltage_v * current_a

        battery_pct = None if capacity_pct is None else float(capacity_pct)
        return BatteryReading(voltage=voltage_v, current=current_a, power=power_w, battery_pct=battery_pct)


TABLES_SQL = """
CREATE TABLE IF NOT EXISTS system_sample (
  ts INTEGER PRIMARY KEY,
  voltage REAL,
  current REAL,
  power REAL,
  battery_pct REAL,
  cpu_total REAL NOT NULL,
  cpu_freq REAL NOT NULL,
  load1 REAL NOT NULL,
  load5 REAL NOT NULL,
  load15 REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cpu_core (
  ts INTEGER NOT NULL,
  core INTEGER NOT NULL,
  usage REAL NOT NULL,
  PRIMARY KEY (ts, core),
  FOREIGN KEY (ts) REFERENCES system_sample(ts) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS process_sample (
  ts INTEGER NOT NULL,
  pid INTEGER NOT NULL,
  name TEXT NOT NULL,
  cpu REAL NOT NULL,
  mem REAL NOT NULL,
  PRIMARY KEY (ts, pid),
  FOREIGN KEY (ts) REFERENCES system_sample(ts) ON DELETE CASCADE
);
"""

VIEW_SQL = """
DROP VIEW IF EXISTS training_view;
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
"""


def _configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA busy_timeout=5000;")


def _init_db(conn: sqlite3.Connection) -> None:
    _configure_sqlite(conn)
    conn.executescript(TABLES_SQL)
    # Lightweight forward-compatible migration for optional columns.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(system_sample);").fetchall()}
    if "battery_pct" not in cols:
        conn.execute("ALTER TABLE system_sample ADD COLUMN battery_pct REAL;")
        conn.commit()
    conn.executescript(VIEW_SQL)


def _safe_getloadavg() -> tuple[float, float, float]:
    # Raspberry Pi OS supports load averages; keep a safe fallback anyway.
    try:
        return psutil.getloadavg()
    except (AttributeError, OSError):
        return (0.0, 0.0, 0.0)


def _cpu_freq_mhz() -> float:
    freq = psutil.cpu_freq()
    if freq is None or freq.current is None:
        return 0.0
    return float(freq.current)


def _sample_processes(
    *,
    ts: int,
    delta_wall_s: float,
    prev_cpu_time_s: dict[int, float],
    top_n: int,
) -> tuple[list[tuple[int, int, str, float, float]], dict[int, float]]:
    """
    Returns:
      - rows: (ts, pid, name, cpu_percent, mem_percent)
      - new_prev_cpu_time_s: pid -> total_cpu_time_s
    """
    candidates: list[tuple[float, int, str, float]] = []
    new_prev: dict[int, float] = {}

    for proc in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        try:
            pid = int(proc.info["pid"])
            cmdline = proc.info.get("cmdline") or []
            exe = proc.info.get("exe") or ""
            name = proc.info.get("name") or ""
            cpu_times = proc.cpu_times()
            mem_pct = float(proc.memory_percent())
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            continue

        display = ""
        if cmdline:
            display = " ".join(cmdline)
        elif exe:
            display = exe
        else:
            display = name
        if not display:
            display = f"[pid {pid}]"

        total_cpu_s = float(cpu_times.user + cpu_times.system)
        new_prev[pid] = total_cpu_s

        prev_total_cpu_s = prev_cpu_time_s.get(pid)
        cpu_pct = 0.0
        if prev_total_cpu_s is not None and delta_wall_s > 0:
            cpu_pct = (total_cpu_s - prev_total_cpu_s) / delta_wall_s * 100.0
            if cpu_pct < 0:
                cpu_pct = 0.0

        candidates.append((cpu_pct, pid, display, mem_pct))

    candidates.sort(key=lambda x: x[0], reverse=True)
    rows = [(ts, pid, name, cpu, mem) for (cpu, pid, name, mem) in candidates[:top_n]]
    return rows, new_prev


def _ensure_unique_ts(ts: int, last_ts: Optional[int]) -> int:
    if last_ts is None:
        return ts
    if ts <= last_ts:
        return last_ts + 1
    return ts


def run_logger(
    db_path: str,
    interval_s: float,
    top_n_procs: int,
    verbose: bool,
    power_supply: str,
) -> int:
    if interval_s < 1.0:
        raise ValueError("interval must be >= 1 second (schema uses epoch seconds as primary key)")
    if top_n_procs < 0:
        raise ValueError("top-procs must be >= 0")

    battery: BatterySensor
    if power_supply == "none":
        battery = NullBatterySensor()
    elif power_supply == "auto":
        battery = SysfsPowerSupplyBatterySensor.auto_detect() or NullBatterySensor()
    else:
        battery = SysfsPowerSupplyBatterySensor(power_supply)

    conn = sqlite3.connect(db_path)
    try:
        _init_db(conn)

        # Prime psutil's internal CPU percent measurement, and our per-process deltas.
        psutil.cpu_percent(interval=None, percpu=True)
        prev_proc_cpu_time_s: dict[int, float] = {}
        last_mono = time.monotonic()
        last_ts: Optional[int] = None

        stop = False

        def _handle_stop(_signum: int, _frame) -> None:  # type: ignore[no-untyped-def]
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, _handle_stop)
        signal.signal(signal.SIGTERM, _handle_stop)

        next_deadline = time.monotonic()

        while not stop:
            next_deadline += interval_s

            now_mono = time.monotonic()
            delta_wall_s = now_mono - last_mono
            last_mono = now_mono

            ts = _ensure_unique_ts(int(time.time()), last_ts)
            last_ts = ts

            core_usage = psutil.cpu_percent(interval=None, percpu=True)
            cpu_total = float(sum(core_usage) / len(core_usage)) if core_usage else 0.0

            cpu_freq = _cpu_freq_mhz()
            load1, load5, load15 = _safe_getloadavg()

            batt = battery.read()

            proc_rows: list[tuple[int, int, str, float, float]] = []
            if top_n_procs > 0:
                proc_rows, prev_proc_cpu_time_s = _sample_processes(
                    ts=ts,
                    delta_wall_s=delta_wall_s,
                    prev_cpu_time_s=prev_proc_cpu_time_s,
                    top_n=top_n_procs,
                )
            else:
                prev_proc_cpu_time_s = {}

            core_rows = [(ts, core_idx, float(usage)) for core_idx, usage in enumerate(core_usage)]

            cur = conn.cursor()
            try:
                cur.execute("BEGIN;")
                cur.execute(
                    """
                    INSERT INTO system_sample
                      (ts, voltage, current, power, battery_pct, cpu_total, cpu_freq, load1, load5, load15)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ts,
                        batt.voltage,
                        batt.current,
                        batt.power,
                        batt.battery_pct,
                        cpu_total,
                        cpu_freq,
                        float(load1),
                        float(load5),
                        float(load15),
                    ),
                )
                cur.executemany(
                    "INSERT INTO cpu_core (ts, core, usage) VALUES (?, ?, ?);",
                    core_rows,
                )
                if proc_rows:
                    cur.executemany(
                        "INSERT INTO process_sample (ts, pid, name, cpu, mem) VALUES (?, ?, ?, ?, ?);",
                        proc_rows,
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

            if verbose:
                print(
                    f"ts={ts} cpu_total={cpu_total:.1f}% cores={len(core_usage)} procs={len(proc_rows)}",
                    file=sys.stderr,
                )

            sleep_s = next_deadline - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # If we fall behind, resync to avoid runaway backlog.
                next_deadline = time.monotonic()

        if verbose:
            print("Stopping.", file=sys.stderr)
        return 0
    finally:
        conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Log Raspberry Pi telemetry into SQLite.")
    p.add_argument("--db", default="telemetry.db", help="SQLite database path (default: telemetry.db)")
    p.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Sampling interval in seconds (default: 5). Must be >= 1.",
    )
    p.add_argument(
        "--top-procs",
        type=int,
        default=10,
        help="Number of top processes (by CPU) to log each sample (default: 10).",
    )
    p.add_argument(
        "--power-supply",
        default="auto",
        help=(
            "Battery/power source from /sys/class/power_supply. "
            "Use 'auto' (default), a specific directory name (e.g. 'BAT0'), or 'none'."
        ),
    )
    p.add_argument("--verbose", action="store_true", help="Print one line per sample to stderr.")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return run_logger(args.db, args.interval, args.top_procs, args.verbose, args.power_supply)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
