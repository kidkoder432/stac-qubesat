#!/usr/bin/env python3
"""
ODMR sweep plotter: console log (or CSV) in, CSV and PNG out.

Typical use after a sweep (`q` for the quick one, or `mw sweep 2 5 5`):
  1. Copy the serial console output into a text file, e.g. sweep_log.txt.
     (Timestamps from the monitor and the progress line are fine; only lines containing
     DATA,<cycle>,<freq_mhz>,<contrast> are used, so a cancelled sweep still plots.)
  2. python3 plot_odmr_sweep.py sweep_log.txt
     -> sweep_log.csv  (cycle,freq_mhz,contrast) and odmr_w_curve_plot.png

Options:
  --csv OUT.csv   where to write the CSV (default: <input name>.csv, never the input itself)
  --png OUT.png   where to write the plot (default: odmr_w_curve_plot.png)
  --show          also open the plot in a window (needs a GUI matplotlib backend)
  --no-plot       only write the CSV
  -               read the log from standard input

With several cycles the plot shows each cycle faintly, the mean as a bold line with a +/- 1 std
band, and marks the lowest point of the mean (the ODMR dip). Contrast is the mean photocurrent at
the frequency divided by the mean at the 1500 MHz reference, so it is about 0.85 to 1.0.

The older formats still work: two-column "freq,value" CSV, one value per line (spread over
2800..2950 MHz), and the mission log lines "t,FREQ=2870MHz,CONTRAST=0.85,...".
"""

import argparse
import csv
import math
import os
import re
import sys

DATA_RE = re.compile(r"DATA,(\d+),(\d+),(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")


def parse_console_log(text):
    """Every DATA,<cycle>,<freq_mhz>,<contrast> in the text, as (cycle, freq_mhz, contrast)."""
    rows = []
    for m in DATA_RE.finditer(text):
        rows.append((int(m.group(1)), int(m.group(2)), float(m.group(3))))
    return rows


def parse_legacy(text):
    """Older formats. Returns (freqs, values); freqs is [] for a plain list of values."""
    x, y = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "FREQ=" in line and "CONTRAST=" in line:
            f = re.search(r"FREQ=([0-9.]+)", line)
            c = re.search(r"CONTRAST=([0-9.]+)", line)
            if f and c:
                x.append(float(f.group(1)))
                y.append(float(c.group(1)))
        elif "," in line:
            parts = line.split(",")
            try:
                x.append(float(parts[0]))
                y.append(float(parts[1]))
            except ValueError:
                continue
        else:
            try:
                y.append(float(line))
            except ValueError:
                continue
    if not x and len(y) > 1:
        x = [2800.0 + i * (150.0 / (len(y) - 1)) for i in range(len(y))]
    elif not x and y:
        x = [2800.0]
    return x, y


def write_csv(rows, path):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cycle", "freq_mhz", "contrast"])
        w.writerows(rows)


def summarize(rows):
    """{freq: (mean, std, n)} over cycles, sorted by frequency."""
    by_freq = {}
    for _cycle, freq, value in rows:
        by_freq.setdefault(freq, []).append(value)
    out = {}
    for freq in sorted(by_freq):
        vals = by_freq[freq]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        out[freq] = (mean, math.sqrt(var), len(vals))
    return out


def dip(summary):
    """(freq, mean contrast) of the lowest mean point, or None."""
    if not summary:
        return None
    freq = min(summary, key=lambda f: summary[f][0])
    return freq, summary[freq][0]


def plot_rows(rows, png_path, title, show=False):
    import matplotlib

    if not show:
        matplotlib.use("Agg")  # headless-safe
    import matplotlib.pyplot as plt

    summary = summarize(rows)
    cycles = sorted({r[0] for r in rows})
    fig, ax = plt.subplots(figsize=(9, 5))

    if len(cycles) > 1:
        for c in cycles:
            pts = sorted((f, v) for cyc, f, v in rows if cyc == c)
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-", linewidth=1, alpha=0.35, label=f"cycle {c}")
    freqs = list(summary)
    means = [summary[f][0] for f in freqs]
    stds = [summary[f][1] for f in freqs]
    label = "mean of %d cycles" % len(cycles) if len(cycles) > 1 else "contrast"
    ax.plot(freqs, means, "b.-", linewidth=2, markersize=6, label=label)
    if len(cycles) > 1:
        ax.fill_between(freqs, [m - s for m, s in zip(means, stds)], [m + s for m, s in zip(means, stds)],
                        color="b", alpha=0.15, label="±1 std")

    d = dip(summary)
    if d:
        ax.axvline(d[0], color="r", linestyle=":", linewidth=1)
        ax.annotate("lowest: %.4f at %d MHz" % (d[1], d[0]), xy=d, xytext=(25, 30),
                    textcoords="offset points", color="r", arrowprops=dict(arrowstyle="->", color="r"))

    ax.set_title(title)
    ax.set_xlabel("Microwave Frequency (MHz)")
    ax.set_ylabel("Contrast (signal / reference)")
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    if show:
        plt.show()
    plt.close(fig)


def plot_legacy(x, y, png_path, title, show=False):
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(x, y, "b.-", linewidth=1.5, markersize=5, label="Raw Contrast")
    ax.set_title(title)
    ax.set_xlabel("Microwave Frequency (MHz)")
    ax.set_ylabel("Contrast")
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=150)
    if show:
        plt.show()
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Plot an ODMR sweep from a console log or CSV.")
    ap.add_argument("input", nargs="?", default="sweep.csv", help="log or CSV file, or - for stdin")
    ap.add_argument("--csv", help="CSV output path")
    ap.add_argument("--png", default="odmr_w_curve_plot.png", help="plot output path")
    ap.add_argument("--show", action="store_true", help="also show the plot in a window")
    ap.add_argument("--no-plot", action="store_true", help="only write the CSV")
    args = ap.parse_args(argv)

    if args.input == "-":
        text, name = sys.stdin.read(), "stdin"
    else:
        if not os.path.exists(args.input):
            print(f"Error: file '{args.input}' not found.")
            return 1
        with open(args.input, "r", errors="replace") as fh:
            text = fh.read()
        name = os.path.basename(args.input)

    rows = parse_console_log(text)
    if rows:
        csv_path = args.csv
        if csv_path is None and args.input != "-":
            stem = os.path.splitext(args.input)[0]
            csv_path = stem + ".csv"
            if os.path.abspath(csv_path) == os.path.abspath(args.input):
                csv_path = stem + "_data.csv"
        if csv_path:
            write_csv(rows, csv_path)
            print(f"Wrote {len(rows)} points to {csv_path}")
        summary = summarize(rows)
        d = dip(summary)
        cycles = sorted({r[0] for r in rows})
        print(f"{len(cycles)} cycle(s), {len(summary)} frequencies" + (f"; lowest mean contrast {d[1]:.4f} at {d[0]} MHz" if d else ""))
        if not args.no_plot:
            plot_rows(rows, args.png, f"ODMR Microwave Sweep ({name})", args.show)
            print(f"Saved plot to {args.png}")
        return 0

    x, y = parse_legacy(text)
    if not y:
        print(f"Error: no data in '{args.input}' (looked for DATA,<cycle>,<freq>,<contrast> lines and the older formats).")
        return 1
    if not args.no_plot:
        plot_legacy(x, y, args.png, f"ODMR Microwave Sweep ({name})", args.show)
        print(f"Saved plot to {args.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
