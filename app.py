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
CORS(app)  # Dodaj CORS podršku

BASE_DIR    = Path(__file__).parent
HTML_FILE   = BASE_DIR / "generator-testova.html"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


def get_api_key():
    """Učitaj API ključ iz environment varijable ili .env fajla."""
    # Prvo provjeri environment varijablu (važno za Render)
    key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if key:
        return key
    
    # Fallback na .env fajl (za lokalni razvoj)
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


@app.route("/api/extract-text", methods=["POST"])
def extract_text():
    """
    Ekstraktuj tekst iz uploadanih fajlova (PDF, DOCX, TXT, MD).
    Potrebno za generisanje testova baziranih na lekcijama.
    """
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Nema fajla u zahtjevu"}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "Prazan naziv fajla"}), 400
            
        filename = file.filename.lower()
        ext = filename.split('.')[-1] if '.' in filename else ''
        
        # Podržani formati
        supported = ['pdf', 'docx', 'doc', 'txt', 'md']
        if ext not in supported:
            return jsonify({"error": f"Format .{ext} nije podržan. Podržani: {', '.join(supported)}"}), 400
        
        # Spremi privremeno
        temp_dir = BASE_DIR / "temp_uploads"
        temp_dir.mkdir(exist_ok=True)
        
        # Generiši jedinstveno ime da izbjegnemo konflikte
        import uuid
        temp_filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = temp_dir / temp_filename
        
        try:
            file.save(file_path)
            
            text = ""
            
            # Obrada prema tipu fajla
            if ext == 'pdf':
                try:
                    import PyPDF2
                    with open(file_path, 'rb') as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n\n"
                except ImportError:
                    return jsonify({"error": "PyPDF2 biblioteka nije instalirana. Pokreni: pip install PyPDF2"}), 500
                except Exception as e:
                    return jsonify({"error": f"Greška pri čitanju PDF: {str(e)}"}), 500
                    
            elif ext in ['docx', 'doc']:
                try:
                    import docx2txt
                    text = docx2txt.process(str(file_path))
                except ImportError:
                    # Fallback: pokušaj sa python-docx
                    try:
                        from docx import Document
                        doc = Document(str(file_path))
                        text = "\n\n".join([paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()])
                    except ImportError:
                        return jsonify({"error": "Biblioteke za DOCX nisu instalirane. Pokreni: pip install docx2txt python-docx"}), 500
                except Exception as e:
                    return jsonify({"error": f"Greška pri čitanju DOCX: {str(e)}"}), 500
                    
            else:
                # Tekstualni fajlovi (txt, md)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text = f.read()
                except UnicodeDecodeError:
                    # Pokušaj sa drugim encodingom
                    with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                        text = f.read()
            
            # Očisti tekst
            text = text.strip()
            if not text:
                return jsonify({"error": "Fajl je prazan ili ne sadrži čitljiv tekst"}), 400
            
            # Limit za API (Mistral ima limit na dužinu)
            max_chars = 50000
            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[... tekst skraćen zbog limita ...]"
            
            return jsonify({
                "text": text,
                "filename": file.filename,
                "chars": len(text),
                "format": ext
            })
            
        finally:
            # Očisti privremeni fajl
            try:
                if file_path.exists():
                    file_path.unlink()
            except:
                pass
                
    except Exception as e:
        return jsonify({"error": f"Neočekivana greška: {str(e)}"}), 500


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

        return Response(body, status=200, mimetype="application/json")

    except urllib.error.HTTPError as e:
        err = e.read()
        return Response(err, status=e.code, mimetype="application/json")

    except Exception as e:
        return jsonify({"error": {"message": str(e)}}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    key = get_api_key()
    print(f"\n  Generator Testova: http://localhost:{port}")
    print(f"  Kljuc: {key[:8] + '...' + key[-4:] if key else 'NIJE POSTAVLJEN'}")
    print(f"  API za ekstrakciju teksta: /api/extract-text (PDF, DOCX, TXT, MD)\n")
    app.run(host="0.0.0.0", port=port, debug=False)
