#!/usr/bin/env python3
"""
Generator Testova - Flask Server
"""

import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from flask import Flask, send_file, request, jsonify

app = Flask(__name__)

BASE_DIR    = Path(__file__).parent
HTML_FILE   = BASE_DIR / "generator-testova.html"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


def get_api_key():
    key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if key:
        return key
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MISTRAL_API_KEY="):
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
                "Content-Disposition: form-data; name=\"" + name + "\"" + CRLF + CRLF +
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
            from flask import Response
            return Response(
                pdf_bytes,
                status=200,
                mimetype="application/pdf",
                headers={"Access-Control-Allow-Origin": "*"}
            )
        else:
            return jsonify({
                "error": "LaTeX kompajliranje nije uspjelo",
                "log": pdf_bytes.decode("utf-8", errors="replace")[:500]
            }), 422

    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        return jsonify({"error": "TeXLive HTTP greska " + str(e.code), "log": err[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mistral", methods=["POST"])
def mistral_proxy():
    try:
        data = request.get_json()

        api_key = get_api_key()
        if not api_key:
            api_key = data.pop("__api_key", "")
        else:
            data.pop("__api_key", None)

        if not api_key:
            return jsonify({"error": {"message": "API kljuc nije postavljen."}}), 400

        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            MISTRAL_URL,
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read()

        return app.response_class(
            response=body,
            status=200,
            mimetype="application/json"
        )

    except urllib.error.HTTPError as e:
        err = e.read()
        return app.response_class(response=err, status=e.code, mimetype="application/json")

    except Exception as e:
        return jsonify({"error": {"message": str(e)}}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    key = get_api_key()
    print(f"\n  Generator Testova: http://localhost:{port}")
    print(f"  Kljuc: {key[:8] + '...' + key[-4:] if key else 'NIJE POSTAVLJEN'}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
