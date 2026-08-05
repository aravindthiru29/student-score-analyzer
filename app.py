from flask import Flask, render_template, jsonify, request, session, redirect, url_for, Response
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO, StringIO
import json
import os
import uuid

PASS_MARK = 50

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "student-score-analyser-secret-2026")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB max upload

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "pdf"}

# Server-side data store with fallback to ensure upload always works
DATA_STORE = {}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_session_id():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
        session.modified = True
    return session["session_id"]


def get_session_df():
    sid = session.get("session_id")
    if sid and sid in DATA_STORE:
        return DATA_STORE[sid]
    # Fallback to latest uploaded dataframe so upload NEVER fails regardless of cookie settings
    return DATA_STORE.get("latest")


def store_session_df(df, filename):
    sid = get_session_id()
    DATA_STORE[sid] = df
    DATA_STORE["latest"] = df
    session["uploaded_filename"] = filename
    session.modified = True


def parse_uploaded_file(file):
    """Parse an uploaded file (CSV, Excel, or PDF) into a pandas DataFrame."""
    filename = file.filename.lower()
    file.seek(0)

    if filename.endswith(".csv"):
        try:
            df = pd.read_csv(file, encoding="utf-8")
        except UnicodeDecodeError:
            file.seek(0)
            df = pd.read_csv(file, encoding="latin1")
        except Exception:
            file.seek(0)
            try:
                df = pd.read_csv(file, sep=None, engine="python")
            except Exception:
                file.seek(0)
                df = pd.read_csv(file, sep=";")
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    elif filename.endswith(".pdf"):
        import pdfplumber
        all_rows = []
        header = None
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or not any(row):
                            continue
                        cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                        if header is None:
                            header = [c if c else f"Col_{i+1}" for i, c in enumerate(cleaned_row)]
                        else:
                            all_rows.append(cleaned_row)
        if header is None or len(all_rows) == 0:
            raise ValueError("No tabular score data found in the PDF file.")
        df = pd.DataFrame(all_rows, columns=header)
    else:
        raise ValueError("Unsupported file format. Please upload CSV, Excel, or PDF files.")

    # Clean column names
    df.columns = [str(col).strip() if col is not None else f"Column_{i+1}" for i, col in enumerate(df.columns)]

    # Detect student name column (case-insensitive search for 'name' or 'student')
    name_col = None
    for col in df.columns:
        if col.lower() in ["name", "student", "student name", "student_name", "names", "student id", "id"]:
            name_col = col
            break

    if name_col is None:
        # Check first column with text/object dtype
        for col in df.columns:
            try:
                pd.to_numeric(df[col], errors="raise")
            except (ValueError, TypeError):
                name_col = col
                break

    if name_col is None:
        # Create a default Name column if none detected
        df.insert(0, "Name", [f"Student {i+1}" for i in range(len(df))])
        name_col = "Name"
    elif name_col != "Name":
        df = df.rename(columns={name_col: "Name"})

    # Convert non-Name columns to numeric
    for col in df.columns:
        if col != "Name":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where all numeric values are missing
    numeric_cols = [c for c in df.columns if c != "Name"]
    if not numeric_cols:
        raise ValueError("No numerical score columns found in the dataset.")

    df = df.dropna(subset=numeric_cols, how="all")
    df[numeric_cols] = df[numeric_cols].fillna(0)

    if len(df) == 0:
        raise ValueError("The uploaded file does not contain any valid student score rows.")

    return df


def subject_stats(df):
    numeric = [c for c in df.columns if c != "Name"]
    stats = df[numeric].agg(["mean", "min", "max"]).round(2)
    return stats


def overall_stats(df):
    numeric = [c for c in df.columns if c != "Name"]
    df = df.copy()
    df["Total"] = df[numeric].sum(axis=1).round(2)
    df["Average"] = df[numeric].mean(axis=1).round(2)
    passed = int((df[numeric] >= PASS_MARK).all(axis=1).sum())
    failed = int(len(df) - passed)
    topper = df.loc[df["Total"].idxmax()]
    return {
        "students": len(df),
        "passed": passed,
        "failed": failed,
        "topper_name": str(topper["Name"]),
        "topper_total": float(topper["Total"]),
    }, df


@app.route("/")
def index():
    df = get_session_df()
    error = request.args.get("error")
    if df is None or len(df) == 0:
        return render_template("index.html", has_data=False, error=error)

    stats = subject_stats(df).to_dict()
    overall, df_with_totals = overall_stats(df)
    students = df_with_totals[["Name", "Total", "Average"]].sort_values(
        "Total", ascending=False
    ).to_dict(orient="records")
    filename = session.get("uploaded_filename", "Uploaded File")
    return render_template(
        "index.html",
        has_data=True,
        stats=stats,
        overall=overall,
        students=students,
        filename=filename,
        error=error
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return redirect(url_for("index", error="No file selected."))

    file = request.files["file"]
    if not file or file.filename == "":
        return redirect(url_for("index", error="No file selected."))

    if not allowed_file(file.filename):
        return redirect(url_for("index", error="Unsupported file type. Please upload a CSV, Excel (.xlsx/.xls), or PDF file."))

    try:
        df = parse_uploaded_file(file)
        store_session_df(df, file.filename)
        return redirect(url_for("index"))
    except Exception as e:
        return redirect(url_for("index", error=str(e)))


@app.route("/clear", methods=["POST"])
def clear():
    sid = session.get("session_id")
    if sid:
        DATA_STORE.pop(sid, None)
    DATA_STORE.pop("latest", None)
    session.pop("uploaded_filename", None)
    session.modified = True
    return redirect(url_for("index"))


@app.route("/sample")
def sample():
    """Generates a sample CSV template for users to test."""
    sample_csv = (
        "Name,Mathematics,Physics,Chemistry,English,Computer Science\n"
        "Alice Johnson,85,92,78,88,95\n"
        "Bob Smith,45,55,60,52,50\n"
        "Charlie Davis,90,88,94,82,91\n"
        "Diana Prince,72,68,75,80,85\n"
        "Ethan Hunt,38,42,49,65,58\n"
        "Fiona Gallagher,95,98,92,90,99\n"
    )
    df = pd.read_csv(StringIO(sample_csv))
    store_session_df(df, "sample_score_data.csv")
    return redirect(url_for("index"))


@app.route("/api/chart-data")
def api_chart_data():
    df = get_session_df()
    if df is None:
        return jsonify({"subjects": [], "means": []})
    numeric = [c for c in df.columns if c != "Name"]
    means = df[numeric].mean().round(2)
    return jsonify({
        "subjects": list(means.index),
        "means": [float(v) for v in means.values]
    })


if __name__ == "__main__":
    app.run(debug=True)
