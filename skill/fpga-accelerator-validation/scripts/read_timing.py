"""Parse setup/hold and clocks from a Vivado timing summary; not a constraint audit."""
import argparse
import json
import math
from pathlib import Path
import re


def parse(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    summary = re.search(r'^\s*WNS\(ns\)[^\n]*WHS\(ns\)[^\n]*\n\s*-+[^\n]*\n\s*([^\n]+)', text, re.M)
    if not summary:
        raise ValueError('Unsupported report: missing Vivado WNS/WHS summary')
    values = summary[1].split()
    if len(values) < 8:
        raise ValueError('Incomplete timing summary row')
    wns, whs = float(values[0]), float(values[4])
    clocks = re.findall(r'^(\S+)\s+\{[^}]+\}\s+([\d.]+)\s+([\d.]+)\s*$', text, re.M)
    if not clocks or not all(math.isfinite(v) for v in (wns, whs)):
        raise ValueError('Unsupported report: no clock table or nonfinite timing')
    table = [{'name': name, 'period_ns': float(period), 'frequency_mhz': float(freq)} for name, period, freq in clocks]
    if any(not math.isfinite(row['period_ns']) or row['period_ns'] <= 0 or not math.isfinite(row['frequency_mhz']) or row['frequency_mhz'] <= 0 for row in table):
        raise ValueError('Invalid clock period/frequency')
    return {'setup_met': wns >= 0, 'hold_met': whs >= 0, 'wns_ns': wns, 'whs_ns': whs, 'clocks': table}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        result = parse(args.report)
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc)}))
        return 2
    result['status'] = 'PASS' if result['setup_met'] and result['hold_met'] else 'FAIL'
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
