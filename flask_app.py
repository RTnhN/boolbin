import uuid
import time
import sqlite3
import threading
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

EXPIRATION_DAYS = 3  # UUID pairs expire after 3 days of inactivity
EXPIRATION_SECONDS = EXPIRATION_DAYS * 24 * 60 * 60

if __name__ == "__main__":
    BASE_URL = "http://localhost:5000"
else:
    BASE_URL = "https://zstrout.pythonanywhere.com"


def init_db():
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS bool_store (
                write_uuid TEXT PRIMARY KEY,
                read_uuid TEXT UNIQUE NOT NULL,
                bit INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                gravity_enabled INTEGER NOT NULL DEFAULT 0,
                gravity_expires_at INTEGER
            )
        """
        )
        conn.commit()


def cleanup_expired():
    current_time = int(time.time())
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "DELETE FROM bool_store WHERE ? - created_at > ?",
            (current_time, EXPIRATION_SECONDS),
        )
        conn.commit()


def gravity_monitor():
    """Background thread that runs every 10 minutes and resets bits that have expired."""
    while True:
        current_time = int(time.time())
        with sqlite3.connect("bool_db.db") as conn:
            c = conn.cursor()
            c.execute(
                """
                UPDATE bool_store 
                SET bit = 0, gravity_enabled = 0, gravity_expires_at = NULL 
                WHERE gravity_enabled = 1 AND gravity_expires_at IS NOT NULL AND ? >= gravity_expires_at
            """,
                (current_time,),
            )
            conn.commit()
        time.sleep(10 * 60)  # Sleep for 10 minutes


@app.route("/", methods=["GET"])
def index():
    cleanup_expired()
    write_uuid = str(uuid.uuid4())
    read_uuid = str(uuid.uuid4())
    created_at = int(time.time())
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        # New entries are created with gravity disabled by default.
        c.execute(
            """
            INSERT INTO bool_store (write_uuid, read_uuid, bit, created_at, gravity_enabled, gravity_expires_at)
            VALUES (?, ?, ?, ?, 0, NULL)
        """,
            (write_uuid, read_uuid, 0, created_at),
        )
        conn.commit()
    return render_template_string(
        """
        <h1>UUIDs Generated</h1>
        <p><strong>Write UUID:</strong> <a href="{{ BASE_URL }}/write/{{ write_uuid }}">{{ write_uuid }}</a></p>
        <p><strong>Read UUID:</strong> <a href="{{ BASE_URL }}/read/{{ read_uuid }}">{{ read_uuid }}</a></p>

        <h2>How to Use This Database</h2>
        <p>This simple boolean database works with UUID-based endpoints for reading and writing values.</p>

        <h3>Write Operation</h3>
        <p>To update the boolean value, make a GET request with the write UUID and the <code>bit</code> query parameter.
        Optionally, include the <code>gravity_time</code> parameter (in seconds) to set an expiration time for the bit.
        For example:</p>
        <pre>GET {{ BASE_URL }}/write/{{ write_uuid }}?bit=true&gravity_time=5</pre>
        <p>This will update the value to <strong>true</strong> and automatically reset it after 5 seconds.</p>

        <h3>Read Operation</h3>
        <p>To read the current boolean value, visit the read UUID endpoint:</p>
        <pre>GET {{ BASE_URL }}/read/{{ read_uuid }}</pre>
        <p>The response will be a JSON object like this:</p>
        <pre>{ "bit": true }</pre>

        <h3>Expiration</h3>
        <p>UUID pairs automatically expire after {{ EXPIRATION_DAYS }} days of inactivity. Each write refreshes the expiration timer.</p>

        <h3>Error Handling</h3>
        <p>If an invalid UUID is used, the system returns a 404 error with a JSON message:</p>
        <pre>{ "error": "Invalid UUID" }</pre>

        <h3>Example Usage with Curl</h3>
        <p>Write (set to true with gravity):</p>
        <pre>curl "{{ BASE_URL }}/write/{{ write_uuid }}?bit=true&gravity_time=5"</pre>
        <p>Read current value:</p>
        <pre>curl "{{ BASE_URL }}/read/{{ read_uuid }}"</pre>

        <h3>Database Info</h3>
        <p>Each UUID is random, so there is nothing tying them to anything meaningful. You can view the database contents at:</p>
        <a href="{{ BASE_URL }}/all">{{ BASE_URL }}/all</a>
        <p><i>Note that the might not be up to date since the clean up thread runs every 10 minutes. Reads will always return the current value.</i></p>

        <p><em>Refresh this page to generate new UUID pairs.</em></p>
        """,
        write_uuid=write_uuid,
        read_uuid=read_uuid,
        BASE_URL=BASE_URL,
        EXPIRATION_DAYS=EXPIRATION_DAYS,
    )


@app.route("/write/<write_uuid>", methods=["GET"])
def write_bit(write_uuid):
    bit = request.args.get("bit")
    gravity_time_param = request.args.get("gravity_time")
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT read_uuid FROM bool_store WHERE write_uuid = ?", (write_uuid,)
        )
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Invalid write UUID"}), 404
        read_uuid = row[0]
        current_time = int(time.time())
        if bit is not None:
            bit_value = 1 if bit.lower() == "true" else 0
            if gravity_time_param is not None:
                try:
                    gravity_seconds = int(gravity_time_param)
                except ValueError:
                    return jsonify({"error": "Invalid gravity_time value"}), 400
                if gravity_seconds > 0:
                    gravity_enabled = 1
                    gravity_expires_at = current_time + gravity_seconds
                else:
                    gravity_enabled = 0
                    gravity_expires_at = None
                c.execute(
                    """
                    UPDATE bool_store 
                    SET bit = ?, created_at = ?, gravity_enabled = ?, gravity_expires_at = ?
                    WHERE write_uuid = ?
                """,
                    (
                        bit_value,
                        current_time,
                        gravity_enabled,
                        gravity_expires_at,
                        write_uuid,
                    ),
                )
            else:
                c.execute(
                    """
                    UPDATE bool_store 
                    SET bit = ?, created_at = ?
                    WHERE write_uuid = ?
                """,
                    (bit_value, current_time, write_uuid),
                )
            conn.commit()
            response = {
                "message": "Bit updated",
                "bit": bool(bit_value),
                "read_uuid": read_uuid,
            }
            if gravity_time_param is not None:
                response["gravity"] = True if gravity_seconds > 0 else False
                response["gravity_expires_at"] = gravity_expires_at
            return jsonify(response)
    return jsonify({"write_uuid": write_uuid, "read_uuid": read_uuid})


@app.route("/read/<read_uuid>", methods=["GET"])
def read_bit(read_uuid):
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT bit, gravity_enabled, gravity_expires_at 
            FROM bool_store 
            WHERE read_uuid = ?
        """,
            (read_uuid,),
        )
        row = c.fetchone()
        if not row:
            return jsonify({"error": "Invalid read UUID"}), 404
        bit_value = bool(row[0])
        gravity_enabled = bool(row[1])
        gravity_expires_at = row[2]
        current_time = int(time.time())
        if (
            gravity_enabled
            and gravity_expires_at
            and current_time >= gravity_expires_at
        ):
            bit_value = False
            c.execute(
                """
                UPDATE bool_store 
                SET bit = 0, gravity_enabled = 0, gravity_expires_at = NULL 
                WHERE read_uuid = ?
            """,
                (read_uuid,),
            )
            conn.commit()
        return jsonify({"bit": bit_value})


@app.route("/all", methods=["GET"])
def all_entries():
    with sqlite3.connect("bool_db.db") as conn:
        c = conn.cursor()
        c.execute(
            "SELECT read_uuid, bit, gravity_enabled, gravity_expires_at FROM bool_store"
        )
        rows = c.fetchall()
    table_html = """
    <h1>All UUID Entries</h1>
    <table border="1">
        <tr>
            <th>Read UUID</th>
            <th>State (Bit)</th>
            <th>Gravity Enabled</th>
            <th>Gravity Expires At</th>
        </tr>
    """
    for read_uuid, bit, gravity_enabled, gravity_expires_at in rows:
        table_html += f"<tr><td>{read_uuid}</td><td>{bool(bit)}</td><td>{bool(gravity_enabled)}</td><td>{gravity_expires_at}</td></tr>"
    table_html += "</table>"
    return table_html


init_db()
threading.Thread(target=gravity_monitor, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
