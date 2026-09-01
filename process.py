#!/usr/bin/env python3
"""
Attendance & Punctuality processor
-----------------------------------
Reads a biometric/GPS "Punches" export CSV and produces a single JSON file
(attendance_data.json) consumed by index.html and employee-details.html.

Shift rules (grace = the shift's own minute, i.e. HH:MM:00-HH:MM:59 is on
time, HH:(MM+1):00 onward is late):
    Shift A  08:00 AM  -> Naveenkumar (T3001)
    Shift B  08:30 AM  -> Santhosh Ananthan, Mohammed Haroon, Fouziya Thabasum S
    Shift C  09:30 AM  -> everyone else
    Saturdays -> everyone reports to the 09:30 AM shift, regardless of normal shift.

A day with zero punches for EVERY employee is treated as a company holiday
and excluded from Present/Absent/Late totals.
A day with zero punches for one employee (on a working day) = Absent.
A day with only one punch (an IN, no OUT) = Present but "Not Logged Out".
"""

import csv
import json
import datetime
from collections import defaultdict

SRC = "punches.csv"
OUT = "attendance_data.json"

# ---- Shift configuration -------------------------------------------------
SHIFT_A = {"code": "A", "label": "8:00 AM", "hour": 8, "minute": 0}
SHIFT_B = {"code": "B", "label": "8:30 AM", "hour": 8, "minute": 30}
SHIFT_C = {"code": "C", "label": "9:30 AM", "hour": 9, "minute": 30}
SATURDAY_SHIFT = SHIFT_C

EMP_SHIFT = {
    "T3001": SHIFT_A,      # Naveenkumar
    "2055": SHIFT_B,       # Santhosh Ananthan
    "2050": SHIFT_B,       # Mohammed Haroon
    "2056": SHIFT_B,       # Fouziya Thabasum S
    # all others default to SHIFT_C (assigned below when first seen)
}


def shift_for(emp_id, punch_date):
    """Return the shift dict that applies to this employee on this date."""
    base = EMP_SHIFT.get(emp_id, SHIFT_C)
    if punch_date.strftime("%A") == "Saturday":
        return SATURDAY_SHIFT
    return base


def is_late(punch_time, shift):
    """Grace period = the shift's own minute. Late starts at the next minute."""
    shift_total_seconds = shift["hour"] * 3600 + shift["minute"] * 60 + 59
    punch_total_seconds = punch_time.hour * 3600 + punch_time.minute * 60 + punch_time.second
    return punch_total_seconds > shift_total_seconds


def late_by_seconds(punch_time, shift):
    shift_start = shift["hour"] * 3600 + shift["minute"] * 60
    grace_end = shift_start + 59
    punch_total_seconds = punch_time.hour * 3600 + punch_time.minute * 60 + punch_time.second
    diff = punch_total_seconds - grace_end
    return max(diff, 0)


def fmt_hms(total_seconds):
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not h and not m:
        parts.append(f"{s}s")
    return " ".join(parts) if parts else "0m"


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))

    employees = {}  # emp_id -> name
    # punches[emp_id][date] = list of datetime.time
    punches = defaultdict(lambda: defaultdict(list))
    all_dates = set()

    for r in rows:
        emp_id = r["Employee Number"].strip()
        name = r["Employee Name"].strip()
        d = datetime.datetime.strptime(r["Punch Date"].strip(), "%d-%m-%Y").date()
        t = datetime.datetime.strptime(r["Punch Time"].strip(), "%H:%M:%S").time()
        employees[emp_id] = name
        punches[emp_id][d].append(t)
        all_dates.add(d)

    min_date, max_date = min(all_dates), max(all_dates)

    # Build the full calendar of days in range, Mon-Sat only (Sunday = weekly off)
    calendar_days = []
    d = min_date
    while d <= max_date:
        if d.strftime("%A") != "Sunday":
            calendar_days.append(d)
        d += datetime.timedelta(days=1)

    # A day is a company holiday if NOBODY punched at all that day
    punched_dates = set()
    for emp_id in punches:
        punched_dates.update(punches[emp_id].keys())

    working_days = [d for d in calendar_days if d in punched_dates]
    holidays = [d for d in calendar_days if d not in punched_dates]

    emp_ids_sorted = sorted(employees.keys(), key=lambda e: employees[e])

    daily_records = []       # flat list, one row per employee per working day
    per_employee_summary = {}

    for emp_id in emp_ids_sorted:
        name = employees[emp_id]
        shift_default = EMP_SHIFT.get(emp_id, SHIFT_C)
        summary = {
            "id": emp_id,
            "name": name,
            "shift": shift_default["label"],
            "shift_code": shift_default["code"],
            "present": 0,
            "absent": 0,
            "late": 0,
            "on_time": 0,
            "no_logout": 0,
            "working_days": len(working_days),
        }

        for d in working_days:
            times = sorted(punches[emp_id].get(d, []))
            shift = shift_for(emp_id, d)
            record = {
                "emp_id": emp_id,
                "name": name,
                "date": d.isoformat(),
                "weekday": d.strftime("%A"),
                "shift_label": shift["label"] + (" (Sat)" if d.strftime("%A") == "Saturday" else ""),
            }

            if not times:
                record["status"] = "Absent"
                record["in_time"] = None
                record["out_time"] = None
                record["late_by"] = None
                record["punch_count"] = 0
                summary["absent"] += 1
            else:
                in_time = times[0]
                out_time = times[-1] if len(times) > 1 else None
                late = is_late(in_time, shift)
                record["in_time"] = in_time.strftime("%H:%M:%S")
                record["out_time"] = out_time.strftime("%H:%M:%S") if out_time else None
                record["punch_count"] = len(times)
                record["late_by"] = fmt_hms(late_by_seconds(in_time, shift)) if late else None

                summary["present"] += 1
                if late:
                    summary["late"] += 1
                    record["status"] = "Late"
                else:
                    summary["on_time"] += 1
                    record["status"] = "On Time"

                if out_time is None:
                    summary["no_logout"] += 1
                    record["no_logout"] = True
                else:
                    record["no_logout"] = False

            daily_records.append(record)

        summary["attendance_pct"] = round(100 * summary["present"] / summary["working_days"], 1) if summary["working_days"] else 0
        summary["punctuality_pct"] = round(100 * summary["on_time"] / summary["present"], 1) if summary["present"] else 0
        per_employee_summary[emp_id] = summary

    data = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_file": SRC,
        "date_range": {"start": min_date.isoformat(), "end": max_date.isoformat()},
        "working_days": [d.isoformat() for d in working_days],
        "holidays": [d.isoformat() for d in holidays],
        "shift_rules": {
            "A": "8:00 AM (Naveenkumar)",
            "B": "8:30 AM (Santhosh, Haroon, Fouziya)",
            "C": "9:30 AM (all others)",
            "saturday": "Everyone reports at 9:30 AM on Saturdays",
            "grace": "On time up to HH:MM:59 of the shift minute; late begins at HH:(MM+1):00",
        },
        "employees": per_employee_summary,
        "daily_records": daily_records,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {OUT}")
    print(f"Employees: {len(employees)}  Working days: {len(working_days)}  Holidays: {holidays}")
    total_late = sum(s["late"] for s in per_employee_summary.values())
    total_absent = sum(s["absent"] for s in per_employee_summary.values())
    total_no_logout = sum(s["no_logout"] for s in per_employee_summary.values())
    print(f"Total late instances: {total_late}  Total absent-days: {total_absent}  Total no-logout: {total_no_logout}")


if __name__ == "__main__":
    main()
