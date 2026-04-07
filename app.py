"""Flask app: upload a receipt -> OCR -> find survey code -> auto-complete survey."""
from __future__ import annotations

import os
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename

from receipt_scanner import scan_receipt, parse_receipt, ReceiptDetails
from survey_automator import complete_survey

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "tiff", "webp"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())


def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    # Accept either an uploaded image or pasted receipt text (for testing / accessibility).
    pasted_text = (request.form.get("receipt_text") or "").strip()
    receipt: ReceiptDetails

    if pasted_text:
        receipt = parse_receipt(pasted_text)
    else:
        if "receipt" not in request.files:
            flash("No file uploaded.")
            return redirect(url_for("index"))
        f = request.files["receipt"]
        if not f or not f.filename:
            flash("No file selected.")
            return redirect(url_for("index"))
        if not _allowed(secure_filename(f.filename)):
            flash(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")
            return redirect(url_for("index"))
        try:
            receipt = scan_receipt(f.read())
        except RuntimeError as e:
            flash(str(e))
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Failed to read receipt image: {e}")
            return redirect(url_for("index"))

    result = complete_survey(
        retailer=receipt.retailer,
        survey_url=receipt.survey_url,
        survey_code=receipt.survey_code,
    )

    if request.headers.get("Accept") == "application/json" or request.form.get("format") == "json":
        return jsonify({"receipt": receipt.as_dict(), "survey": result.as_dict()})

    return render_template("result.html", receipt=receipt.as_dict(), survey=result.as_dict())


@app.route("/api/process", methods=["POST"])
def api_process():
    """JSON API: accepts `receipt_text` (form/json) or `receipt` (multipart file)."""
    if request.is_json:
        body = request.get_json(silent=True) or {}
        text = (body.get("receipt_text") or "").strip()
        if not text:
            return jsonify({"error": "Provide 'receipt_text' in the JSON body."}), 400
        receipt = parse_receipt(text)
    elif "receipt" in request.files:
        try:
            receipt = scan_receipt(request.files["receipt"].read())
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    else:
        text = (request.form.get("receipt_text") or "").strip()
        if not text:
            return jsonify({"error": "Send a 'receipt' file or 'receipt_text'."}), 400
        receipt = parse_receipt(text)

    result = complete_survey(
        retailer=receipt.retailer,
        survey_url=receipt.survey_url,
        survey_code=receipt.survey_code,
    )
    return jsonify({"receipt": receipt.as_dict(), "survey": result.as_dict()})


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
