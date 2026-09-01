"""
The actual web app. This is what Render will run.

Three routes:
  GET  /                -- serves the tappable screen
  GET  /api/stumble      -- returns one item, weighted by this device's taste
  POST /api/react        -- records a thumbs up/down

Run locally with: python app.py
Render runs it with: gunicorn app:app  (see Procfile)
"""

import os
import uuid

from flask import Flask, jsonify, request, send_from_directory

from db import init_db, get_conn, get_or_create_user, record_reaction
from serving import get_next_stumble

app = Flask(__name__, static_folder="static")

init_db()


def _device_id() -> str:
    """
    No login for v1 -- identify the phone by a cookie-less id it sends
    itself. The frontend generates this once and stores it in
    localStorage, then passes it as ?device=... on every call.
    """
    return request.args.get("device") or request.headers.get("X-Device-Id") or "anonymous"


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/stumble")
def api_stumble():
    device_id = _device_id()
    with get_conn() as conn:
        user_id = get_or_create_user(conn, device_id)
        item = get_next_stumble(user_id, conn)

    if item is None:
        return jsonify({"error": "no_more_items"}), 404

    return jsonify({
        "id": item["id"],
        "title": item["title"],
        "excerpt": item["excerpt"],
        "url": item["url"],
        "tags": item["tags"].split(","),
    })


@app.route("/api/react", methods=["POST"])
def api_react():
    body = request.get_json(force=True)
    item_id = body.get("item_id")
    reaction = body.get("reaction")  # "up" or "down"
    tags = body.get("tags", [])

    if reaction not in ("up", "down") or not item_id:
        return jsonify({"error": "invalid_request"}), 400

    device_id = _device_id()
    with get_conn() as conn:
        user_id = get_or_create_user(conn, device_id)
        record_reaction(conn, user_id, item_id, tags, reaction)

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
