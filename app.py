#!/usr/bin/env python3
"""
Generator Testova - Flask Server
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from flask import Flask, send_file, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BASE_DIR    = Path(__file__).parent
HTML_FILE   = BASE_DIR / "generator-testova.html"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


def get_api_key():
    """Učitaj API ključ iz environment varijable ili .env fajla."""
    key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if key:
        return key
    
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MISTRAL_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


@app.route("/")
@app.route("/index.html")
@app.route("/generator-testova.html")
def index():
    return send_file(HTML_FILE)


@app.route("/api/key-status")
def key_status():
    key = get_api_key()
    preview = ""
    if len(key) > 14:
        preview = key[:8] + "..." + key[-4:]
    elif key:
        preview = "*" * len(key)
    return jsonify({"configured": bool(key), "preview": preview})


@app.route("/api/compile", methods=["POST"])
def compile_latex():
    try:
        data = request.get_json()
        latex = data.get("latex", "")
        if not latex:
            return jsonify({"error": "Nema LaTeX sadrzaja"}), 400

        boundary = "----FormBoundary7MA4YWxkTrZu0gW"
        CRLF = "\r\n"

        def form_field(name, value):
            return (
                "--" + boundary + CRLF +
                'Content-Disposition: form-data; name="' + name + '"' + CRLF + CRLF +
                value + CRLF
            )

        body_str = (
            form_field("filecontents[]", latex) +
            form_field("filename[]", "document.tex") +
            form_field("engine", "pdflatex") +
            form_field("return", "pdf") +
            "--" + boundary + "--" + CRLF
        )
        body = body_str.encode("utf-8")

        req = urllib.request.Request(
            "https://texlive.net/cgi-bin/latexcgi",
            data=body,
            headers={
                "Content-Type": "multipart/form-data; boundary=" + boundary,
                "Content-Length": str(len(body)),
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            pdf_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "")

        if "pdf" in content_type:
            return Response(
                pdf_bytes,
                status=200,
                mimetype="application/pdf"
            )
        else:
            return jsonify({
                "error": "LaTeX kompajliranje nije uspjelo",
                "log": pdf_bytes.decode("utf-8", errors="replace")[:500]
            }), 422
