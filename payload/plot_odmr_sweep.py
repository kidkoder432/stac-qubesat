#!/usr/bin/env python3
"""
Simple ODMR Sweep Plotter: plots raw contrast data vs frequency using matplotlib.
"""

import sys
import os
import matplotlib
matplotlib.use("Agg")  # Safe for terminal/headless use
import matplotlib.pyplot as plt

def main():
    filename = sys.argv[1] if len(sys.argv) > 1 else "sweep.csv"

    if not os.path.exists(filename):
        print(f"Error: file '{filename}' not found.")
        sys.exit(1)

    with open(filename, "r") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not lines:
        print(f"Error: no valid data in '{filename}'.")
        sys.exit(1)

    x = []
    y = []

    for l in lines:
        if "FREQ=" in l and "CONTRAST=" in l:
            # Satellite SD mission log format: e.g. "12.4,FREQ=2870MHz,CONTRAST=0.8521,PD=1.23e-06A"
            import re
            f_match = re.search(r"FREQ=([0-9.]+)", l)
            c_match = re.search(r"CONTRAST=([0-9.]+)", l)
            if f_match and c_match:
                x.append(float(f_match.group(1)))
                y.append(float(c_match.group(1)))
        elif "," in l:
            # Two-column CSV format: freq, value
            parts = l.split(",")
            try:
                x.append(float(parts[0]))
                y.append(float(parts[1]))
            except ValueError:
                continue
        else:
            # Single-column raw floats
            try:
                y.append(float(l))
            except ValueError:
                continue

    if not x and y:
        # Generate frequencies across 2800..2950 MHz for raw single-column lists
        n = len(y)
        x = [2800.0 + i * (150.0 / (n - 1)) for i in range(n)] if n > 1 else [2800.0]

    plt.figure(figsize=(9, 5))
    plt.plot(x, y, "b.-", linewidth=1.5, markersize=5, label="Raw Contrast")
    plt.title(f"ODMR Microwave Sweep ({os.path.basename(filename)})")
    plt.xlabel("Microwave Frequency (MHz)")
    plt.ylabel("Contrast")
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()

    out_file = "odmr_w_curve_plot.png"
    plt.savefig(out_file, dpi=150)
    print(f"Saved plot to {out_file}")

if __name__ == "__main__":
    main()
