import csv
from io import StringIO
from flask import Blueprint, jsonify, request, render_template, Response, abort
from .db import query_one, query_all, execute_query
from .services.twin_service import update_twin_state

api = Blueprint("api", __name__)

def success_response(data=None, message="OK", status_code=200):
    return jsonify({
        "status": "success",
        "message": message,
        "data": data
    }), status_code

def validate_machine_payload(data):
    if not data:
        abort(400, description="Request body must be valid JSON.")

    name = str(data.get("name", "")).strip()
    machine_type = str(data.get("machine_type", "")).strip()
    location = str(data.get("location", "")).strip()

    if not name:
        abort(400, description="Machine name is required.")
    if not machine_type:
        abort(400, description="Machine type is required.")

    return {
        "name": name,
        "machine_type": machine_type,
        "location": location
    }

def parse_float_field(data, field_name, min_value=None):
    if field_name not in data:
        abort(400, description=f"{field_name} is required.")

    try:
        value = float(data[field_name])
    except (TypeError, ValueError):
        abort(400, description=f"{field_name} must be a number.")

    if min_value is not None and value < min_value:
        abort(400, description=f"{field_name} must be at least {min_value}.")

    return value

def validate_sensor_payload(data):
    if not data:
        abort(400, description="Request body must be valid JSON.")

    return {
        "temperature": parse_float_field(data, "temperature", 0),
        "vibration": parse_float_field(data, "vibration", 0),
        "pressure": parse_float_field(data, "pressure", 0),
        "rpm": parse_float_field(data, "rpm", 0),
        "runtime_hours": parse_float_field(data, "runtime_hours", 0),
    }

def get_machine_or_404(machine_id):
    machine = query_one("SELECT * FROM machines WHERE id = ?", (machine_id,))
    if not machine:
        abort(404, description="Machine not found.")
    return machine

def csv_response(filename, headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@api.route("/health", methods=["GET"])
def health():
    return success_response({"server": "running"})

@api.route("/machines", methods=["POST"])
def create_machine():
    payload = validate_machine_payload(request.get_json())

    cursor = execute_query("""
        INSERT INTO machines (name, machine_type, location)
        VALUES (?, ?, ?)
    """, (payload["name"], payload["machine_type"], payload["location"]))

    return success_response(
        {"machine_id": cursor.lastrowid},
        message="Machine created successfully.",
        status_code=201
    )

@api.route("/machines", methods=["GET"])
def list_machines():
    rows = query_all("""
        SELECT *
        FROM machines
        ORDER BY id DESC
    """)
    return success_response([dict(r) for r in rows])

@api.route("/machines/<int:machine_id>/sensor", methods=["POST"])
def add_sensor_reading(machine_id):
    get_machine_or_404(machine_id)
    payload = validate_sensor_payload(request.get_json())

    execute_query("""
        INSERT INTO sensor_readings (
            machine_id, temperature, vibration, pressure, rpm, runtime_hours
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        machine_id,
        payload["temperature"],
        payload["vibration"],
        payload["pressure"],
        payload["rpm"],
        payload["runtime_hours"]
    ))

    twin_result = update_twin_state(machine_id)

    return success_response(
        twin_result,
        message="Sensor reading added successfully.",
        status_code=201
    )

@api.route("/machines/<int:machine_id>/status", methods=["GET"])
def get_status(machine_id):
    get_machine_or_404(machine_id)

    row = query_one("""
        SELECT *
        FROM twin_state
        WHERE machine_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    """, (machine_id,))

    if not row:
        abort(404, description="No twin state found for this machine.")

    return success_response(dict(row))

@api.route("/machines/<int:machine_id>/history", methods=["GET"])
def get_history(machine_id):
    get_machine_or_404(machine_id)

    limit = request.args.get("limit", default=50, type=int)
    if limit < 1 or limit > 500:
        abort(400, description="limit must be between 1 and 500.")

    rows = query_all("""
        SELECT *
        FROM sensor_readings
        WHERE machine_id = ?
        ORDER BY recorded_at DESC, id DESC
        LIMIT ?
    """, (machine_id, limit))

    return success_response([dict(r) for r in rows])

@api.route("/machines/<int:machine_id>/alerts", methods=["GET"])
def get_alerts(machine_id):
    get_machine_or_404(machine_id)

    rows = query_all("""
        SELECT *
        FROM alerts
        WHERE machine_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 50
    """, (machine_id,))

    return success_response([dict(r) for r in rows])

@api.route("/machines/<int:machine_id>/summary", methods=["GET"])
def get_summary(machine_id):
    get_machine_or_404(machine_id)

    total_readings = query_one("""
        SELECT COUNT(*) AS count
        FROM sensor_readings
        WHERE machine_id = ?
    """, (machine_id,))["count"]

    total_alerts = query_one("""
        SELECT COUNT(*) AS count
        FROM alerts
        WHERE machine_id = ?
    """, (machine_id,))["count"]

    avg_health_row = query_one("""
        SELECT AVG(health_score) AS avg_health
        FROM twin_state
        WHERE machine_id = ?
    """, (machine_id,))
    average_health_score = round(avg_health_row["avg_health"], 2) if avg_health_row["avg_health"] is not None else 0

    high_risk_count = query_one("""
        SELECT COUNT(*) AS count
        FROM twin_state
        WHERE machine_id = ? AND failure_risk > 60
    """, (machine_id,))["count"]

    runtime_row = query_one("""
        SELECT MAX(runtime_hours) AS total_runtime
        FROM sensor_readings
        WHERE machine_id = ?
    """, (machine_id,))
    total_runtime = runtime_row["total_runtime"] if runtime_row["total_runtime"] is not None else 0

    failure_count = query_one("""
        SELECT COUNT(*) AS count
        FROM alerts
        WHERE machine_id = ? AND alert_type IN ('anomaly', 'risk', 'critical')
    """, (machine_id,))["count"]

    estimated_mtbf = round(total_runtime / failure_count, 2) if failure_count > 0 else round(total_runtime, 2)
    estimated_mttr = round(1.5 if failure_count > 0 else 0, 2)

    last_updated_row = query_one("""
        SELECT updated_at
        FROM twin_state
        WHERE machine_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
    """, (machine_id,))
    last_updated = last_updated_row["updated_at"] if last_updated_row else None

    return success_response({
        "total_readings": total_readings,
        "total_alerts": total_alerts,
        "average_health_score": average_health_score,
        "high_risk_count": high_risk_count,
        "estimated_mtbf": estimated_mtbf,
        "estimated_mttr": estimated_mttr,
        "last_updated": last_updated
    })

@api.route("/machines/<int:machine_id>/history/export", methods=["GET"])
def export_history(machine_id):
    get_machine_or_404(machine_id)

    rows = query_all("""
        SELECT machine_id, temperature, vibration, pressure, rpm, runtime_hours, recorded_at
        FROM sensor_readings
        WHERE machine_id = ?
        ORDER BY recorded_at DESC, id DESC
    """, (machine_id,))

    csv_rows = [
        [
            row["machine_id"],
            row["temperature"],
            row["vibration"],
            row["pressure"],
            row["rpm"],
            row["runtime_hours"],
            row["recorded_at"]
        ]
        for row in rows
    ]

    return csv_response(
        f"machine_{machine_id}_history.csv",
        ["machine_id", "temperature", "vibration", "pressure", "rpm", "runtime_hours", "recorded_at"],
        csv_rows
    )

@api.route("/machines/<int:machine_id>/alerts/export", methods=["GET"])
def export_alerts(machine_id):
    get_machine_or_404(machine_id)

    rows = query_all("""
        SELECT machine_id, alert_type, message, created_at
        FROM alerts
        WHERE machine_id = ?
        ORDER BY created_at DESC, id DESC
    """, (machine_id,))

    csv_rows = [
        [row["machine_id"], row["alert_type"], row["message"], row["created_at"]]
        for row in rows
    ]

    return csv_response(
        f"machine_{machine_id}_alerts.csv",
        ["machine_id", "alert_type", "message", "created_at"],
        csv_rows
    )