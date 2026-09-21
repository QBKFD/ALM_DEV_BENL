import matplotlib.pyplot as plt
import pandas as pd

from config import FIG_DIR, TEST_START
from loader import load_data

data = load_data()
x = data.index.to_timestamp()

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, c in zip(axes, ["nl", "be"]):
    ax.plot(x, data["euribor3m"], color="black", lw=1.2, label="3M Euribor")
    ax.plot(x, data[f"{c}_savings"], lw=1.6, label="Savings")
    ax.plot(x, data[f"{c}_current"], lw=1.2, ls="--", label="Overnight deposits")
    ax.axhline(0, color="grey", lw=0.6)
    ax.axvline(pd.Period(TEST_START, freq="M").to_timestamp(), color="grey", ls=":", lw=1)
    ax.set_title(c.upper())
    ax.set_ylabel("% per annum")
    ax.legend(frameon=False, fontsize=8)

fig.tight_layout()

out = FIG_DIR / "fig_rates.png"
out.parent.mkdir(exist_ok=True)
fig.savefig(out, dpi=150)
print(f"Saved {out}")
plt.show()