from flask import Flask, render_template, jsonify, Response
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from io import BytesIO

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "score.csv"
PASS_MARK = 50

app = Flask(__name__, static_folder="static", template_folder="templates")

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
    df = df.copy()
    df["Total"] = df[numeric].sum(axis=1)
    df["Average"] = df[numeric].mean(axis=1).round(2)
    passed = int((df[numeric] >= PASS_MARK).all(axis=1).sum())
    failed = int(len(df) - passed)
    topper = df.loc[df["Total"].idxmax()]
    return {
        "students": len(df),
        "passed": passed,
        "failed": failed,
        "topper_name": topper["Name"],
        "topper_total": int(topper["Total"]),
    }, df


def plot_subject_means_png(df):
    numeric = [c for c in df.columns if c != "Name"]
    means = df[numeric].mean()
    fig, ax = plt.subplots(figsize=(8, 4))
    means.plot(kind="bar", color="#1f77b4", edgecolor="black", ax=ax)
    ax.set_title("Average Marks by Subject")
    ax.set_xlabel("Subject")
    ax.set_ylabel("Average Score")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    fig.tight_layout()
    output = BytesIO()
    fig.savefig(output, format="png")
    plt.close(fig)
    output.seek(0)
    return output


@app.route("/")
def index():
    df = load_data(CSV_PATH)
    stats = subject_stats(df).to_dict()
    overall, df = overall_stats(df)
    students = df[["Name", "Total", "Average"]].sort_values("Total", ascending=False).to_dict(orient="records")
    return render_template("index.html", stats=stats, overall=overall, students=students)


@app.route("/chart.png")
def chart_png():
    df = load_data(CSV_PATH)
    output = plot_subject_means_png(df)
    return Response(output.getvalue(), mimetype="image/png")


@app.route("/api/summary")
def api_summary():
    df = load_data(CSV_PATH)
    stats = subject_stats(df).to_dict()
    overall, _ = overall_stats(df)
    return jsonify({"subject_stats": stats, "overall": overall})


if __name__ == "__main__":
    app.run(debug=True)
