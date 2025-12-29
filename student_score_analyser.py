import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CSV_PATH = "score.csv"
PASS_MARK = 50

def load_data(path):
    df = pd.read_csv(path)
    for col in df.columns:
        if col != "Name":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def subject_stats(df):
    numeric = [c for c in df.columns if c != "Name"]
    stats = df[numeric].agg(["mean", "min", "max"]).round(2)
    return stats

def overall_stats(df):
    numeric = [c for c in df.columns if c != "Name"]
    df["Total"] = df[numeric].sum(axis=1)
    df["Average"] = df[numeric].mean(axis=1).round(2)
    passed = (df[numeric] >= PASS_MARK).all(axis=1).sum()
    failed = len(df) - passed
    topper = df.loc[df["Total"].idxmax(), ["Name", "Total"]]
    return {
        "students": len(df),
        "passed": int(passed),
        "failed": int(failed),
        "topper_name": topper["Name"],
        "topper_total": int(topper["Total"]),
    }, df

def plot_subject_means(df):
    numeric = [c for c in df.columns if c != "Name" and c not in ("Total","Average")]
    means = df[numeric].mean()
    plt.figure()
    means.plot(kind="bar", color="skyblue", edgecolor="black")
    plt.title("Average Marks by Subject")
    plt.xlabel("Subject")
    plt.ylabel("Average")
    out = Path("subject_averages.png")
    plt.tight_layout()
    plt.savefig(out)
    print(f"[INFO] Saved chart -> {out.resolve()}")

def main():
    df = load_data(CSV_PATH)
    print("=== SUBJECT STATS (mean/min/max) ===")
    print(subject_stats(df), "\n")

    overall, df = overall_stats(df)
    print("=== OVERALL SUMMARY ===")
    for k,v in overall.items():
        print(f"{k}: {v}")
    print("\n=== PER-STUDENT TOTALS & AVERAGES ===")
    print(df[["Name","Total","Average"]])

    plot_subject_means(df)

if __name__ == "__main__":
    main()
