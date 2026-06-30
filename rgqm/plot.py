import json
import sys


def summarize(path="results.json"):
    with open(path) as f:
        r = json.load(f)
    print("=== EpochForge Lite — Run Summary ===")
    print(f"mode            : {r['mode']}")
    print(f"budget          : {r['budget']}  (checkpoint: {r['checkpoint']})")
    print(f"nodes           : {r['nodes']}")
    print(f"utility_records : {r['utility_records']}")
    print(f"blended_tokens  : {r['blended_tokens']}  (~${r['blended_cost_usd']})")
    print(f"best_node_id    : {r['best_node_id']}")
    print(f"epoch_events    : {len(r['epoch_events'])}")
    for e in r["epoch_events"]:
        print(f"  step {e['step']}: {e['outcome']}  "
              f"(erased={e.get('records_erased', 0)}, "
              f"winner={e.get('winner_id')})")
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib not installed; skipping chart. install with: pip install matplotlib)")
        return 0
    fig, ax = plt.subplots(figsize=(8, 4))
    steps = list(range(r["budget"]))
    ax.plot(steps, [r["utility_records"]] * len(steps), label="records (cumulative)")
    if r["mode"] == "rqgm" and r["checkpoint"] >= 0:
        ax.axvline(r["checkpoint"], color="r", linestyle="--", label="epoch boundary")
    ax.set_xlabel("step")
    ax.set_ylabel("cumulative utility_records")
    ax.set_title(f"RQGM scaffold — {r['mode']}")
    ax.legend()
    out = "results.png"
    fig.savefig(out)
    print(f"\nchart written to {out}")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "results.json"
    sys.exit(summarize(path))
