import uuid
import time
import sqlite3
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


EXPIRATION_DAYS = 30  # Change this value to adjust expiration time
EXPIRATION_SECONDS = EXPIRATION_DAYS * 24 * 60 * 60

# Determine the base URL based on whether the script is running as the main module
if __name__ == "__main__":
    BASE_URL = "http://localhost:5000"
else:
    BASE_URL = "https://zstrout.pythonanywhere.com"


# Initialize the SQLite database
def init_db():
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            """
        CREATE TABLE IF NOT EXISTS bool_store (
            write_uuid TEXT PRIMARY KEY,
            read_uuid TEXT UNIQUE NOT NULL,
            bit INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """
        )
        conn.commit()


# Cleanup expired entries
def cleanup_expired():
    current_time = int(time.time())
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM bool_store WHERE ? - created_at > ?",
            (current_time, EXPIRATION_SECONDS),
        )
        conn.commit()


# Base route: Generate new UUIDs and show them
@app.route("/")
def index():
    cleanup_expired()
    write_uuid = str(uuid.uuid4())
    read_uuid = str(uuid.uuid4())
    created_at = int(time.time())
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO bool_store (write_uuid, read_uuid, bit, created_at) VALUES (?, ?, ?, ?)",
            (write_uuid, read_uuid, 0, created_at),
        )
        conn.commit()
    return render_template_string(
        f"""
    <h1>UUIDs Generated</h1>
    <p><strong>Write/Read UUID:</strong> <a href="/{write_uuid}">{write_uuid}</a></p>
    <p><strong>Read UUID:</strong> <a href="/{read_uuid}">{read_uuid}</a></p>

    <h2>How to Use This Database</h2>
    <p>This simple boolean database works with UUID-based endpoints for reading and writing values.</p>

    <h3>Write Operation</h3>
    <p>To update the boolean value, make a GET request with the write UUID and the <code>bit</code> query parameter:</p>
    <pre>GET {BASE_URL}/write/{write_uuid}?bit=true</pre>
    <p>This will update the value to <strong>true</strong>. Similarly, you can use <code>bit=false</code> to set it to <strong>false</strong>.</p>

    <h3>Read Operation</h3>
    <p>To read the current boolean value, visit the read UUID endpoint:</p>
    <pre>GET {BASE_URL}/read/{read_uuid}</pre>
    <p>The response will be a JSON object like this:</p>
    <pre>{{ '{{' }} \"bit\": true {{ '}}' }}</pre>

    <h3>Expiration</h3>
    <p>UUID pairs automatically expire after {EXPIRATION_DAYS} days of inactivity. Each write refreshes the expiration timer.</p>

    <h3>Error Handling</h3>
    <p>If an invalid UUID is used, the system returns a 404 error with a JSON message:</p>
    <pre>{{ '{{' }} \"error\": \"Invalid UUID\" {{ '}}' }}</pre>

    <h3>Example Usage with Curl</h3>
    <p>Write (set to true):</p>
    <pre>curl \"{BASE_URL}/write/{write_uuid}?bit=true\"</pre>
    <p>Read current value:</p>
    <pre>curl \"{BASE_URL}/read/{read_uuid}\"</pre>

    <h3>Database info</h3>
    <p>Each UUID is random, so there is nothing tying them to anything meaningful. This lets us open the database. You can find the content of the database at the link below:</p>
    <pre>{BASE_URL}/all</pre>

    <p><em>Refresh this page to generate new UUID pairs.</em></p>
    """
    )


# Write route: Update the bit value or show the read UUID
@app.route("/write/<write_uuid>", methods=["GET"])
def write_bit(write_uuid):
    bit = request.args.get("bit")

    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT read_uuid FROM bool_store WHERE write_uuid = ?", (write_uuid,)
        )
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Invalid write UUID"}), 404

        read_uuid = row[0]

        if bit is not None:
            bit_value = 1 if bit.lower() == "true" else 0
            c.execute(
                "UPDATE bool_store SET bit = ?, created_at = ? WHERE write_uuid = ?",
                (bit_value, int(time.time()), write_uuid),
            )
            conn.commit()
            return jsonify(
                {
                    "message": "Bit updated",
                    "bit": bool(bit_value),
                    "read_uuid": read_uuid,
                }
            )

        return jsonify({"write_uuid": write_uuid, "read_uuid": read_uuid})


# Read route: Get the current boolean value
@app.route("/read/<read_uuid>", methods=["GET"])
def read_bit(read_uuid):
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute("SELECT bit FROM bool_store WHERE read_uuid = ?", (read_uuid,))
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Invalid read UUID"}), 404

        bit_value = bool(row[0])
        return jsonify({"bit": bit_value})


# Route to display all entries
@app.route("/all", methods=["GET"])
def all_entries():
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute("SELECT read_uuid, bit FROM bool_store")
        rows = c.fetchall()

    table_html = """
    <h1>All UUID Entries</h1>
    <table border="1">
        <tr>
            <th>Read UUID</th>
            <th>State (Bit)</th>
        </tr>
    """

    for read_uuid, bit in rows:
        table_html += f"<tr><td>{read_uuid}</td><td>{bool(bit)}</td></tr>"

    table_html += "</table>"

    return table_html


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
