"""
LSPDFR Custom Pack - Update Server
==================================
This is the piece that sits in the middle:
 - The DEV APP pushes new update .zip files to this server, and reads
   install stats / posts announcements through it.
 - The NORMAL (player) APP checks this server for the latest version,
   downloads the update .zip, and reports back once it has installed it.

Run this on any always-on machine or a small cloud host (a $5 VPS,
PythonAnywhere, Render, etc). Both other apps just need its URL.

CHANGE THE DEV_TOKEN BELOW before you give this to anyone. It's the
only thing stopping a random person from pushing "updates" or
announcements to your players.
"""

import json
import os
from flask import Flask, request, jsonify, send_from_directory, abort

# ----------------------------------------------------------------------
# CONFIG - edit these
# ----------------------------------------------------------------------
DEV_TOKEN = "k3f8-La9xQ2-mPz71-vR4nT8"   # <-- CHANGE THIS
PORT = 5000
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "data.json")
# ----------------------------------------------------------------------

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)


def load_db():
    if not os.path.exists(DB_PATH):
        db = {
            "current_version": None,
            "updates": {},        # version -> {filename, notes, installs}
            "announcement": "Welcome! No announcements yet.",
        }
        save_db(db)
        return db
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2)


def check_token(req):
    token = req.form.get("token") or (req.json or {}).get("token") if req.is_json else req.form.get("token")
    if req.is_json:
        token = (req.get_json(silent=True) or {}).get("token")
    else:
        token = req.form.get("token") or req.args.get("token")
    return token == DEV_TOKEN


# ---------------------- PLAYER APP ENDPOINTS ---------------------------

@app.route("/manifest", methods=["GET"])
def manifest():
    """Player app calls this to find out the latest version available."""
    db = load_db()
    version = db["current_version"]
    if not version:
        return jsonify({"version": None})
    info = db["updates"][version]
    return jsonify({
        "version": version,
        "notes": info["notes"],
        "download_url": request.host_url.rstrip("/") + "/download/" + info["filename"],
    })


@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    """Serves the actual update zip file."""
    if not os.path.exists(os.path.join(UPLOAD_DIR, filename)):
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@app.route("/report_install", methods=["POST"])
def report_install():
    """Player app calls this after it finishes installing an update,
    so the dev app can show how many people have it."""
    data = request.get_json(silent=True) or {}
    version = data.get("version")
    db = load_db()
    if version in db["updates"]:
        db["updates"][version]["installs"] = db["updates"][version].get("installs", 0) + 1
        save_db(db)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "unknown version"}), 400


@app.route("/announcement", methods=["GET"])
def get_announcement():
    db = load_db()
    return jsonify({"announcement": db.get("announcement", "")})


# ------------------------ DEV APP ENDPOINTS -----------------------------

@app.route("/upload", methods=["POST"])
def upload():
    """Dev app calls this to push a new update."""
    if not check_token(request):
        return jsonify({"ok": False, "error": "bad token"}), 403

    version = request.form.get("version")
    notes = request.form.get("notes", "")
    file = request.files.get("file")
    if not version or not file:
        return jsonify({"ok": False, "error": "version and file are required"}), 400

    filename = f"update_{version}.zip"
    file.save(os.path.join(UPLOAD_DIR, filename))

    db = load_db()
    db["updates"][version] = {
        "filename": filename,
        "notes": notes,
        "installs": db["updates"].get(version, {}).get("installs", 0),
    }
    db["current_version"] = version
    save_db(db)
    return jsonify({"ok": True, "version": version})


@app.route("/stats", methods=["GET"])
def stats():
    """Dev app calls this to see install counts per version."""
    token = request.args.get("token")
    if token != DEV_TOKEN:
        return jsonify({"ok": False, "error": "bad token"}), 403
    db = load_db()
    return jsonify({
        "current_version": db["current_version"],
        "updates": db["updates"],
    })


@app.route("/announcement", methods=["POST"])
def set_announcement():
    """Dev app calls this to broadcast a message to everyone using the app."""
    data = request.get_json(silent=True) or {}
    if data.get("token") != DEV_TOKEN:
        return jsonify({"ok": False, "error": "bad token"}), 403
    db = load_db()
    db["announcement"] = data.get("text", "")
    save_db(db)
    return jsonify({"ok": True})


if __name__ == "__main__":
    load_db()
    print(f"LSPDFR update server running on http://0.0.0.0:{PORT}")
    print("Give the client/dev apps this machine's address + port, e.g. http://YOUR_IP:5000")
    app.run(host="0.0.0.0", port=PORT)
