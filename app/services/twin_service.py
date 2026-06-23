from ..db import query_one, execute_query
from .ml_service import predict_anomaly_and_risk

def calculate_health_score(temperature, vibration, pressure, rpm):
    score = 100

    if temperature > 90:
        score -= 30
    elif temperature > 80:
        score -= 20
    elif temperature > 70:
        score -= 10

    if vibration > 7:
        score -= 30
    elif vibration > 6:
        score -= 20
    elif vibration > 4:
        score -= 10

    if pressure > 130:
        score -= 20
    elif pressure > 120:
        score -= 10

    if rpm > 3200:
        score -= 15
    elif rpm > 3000:
        score -= 10

    return max(score, 0)

def get_health_label(score):
    if score >= 80:
        return "safe"
    if score >= 60:
        return "warning"
    return "critical"

def recommend_action(health_score, anomaly_status, failure_risk):
    if anomaly_status == 1 and failure_risk > 70:
        return "Inspect machine immediately"
    if health_score < 60:
        return "Schedule urgent maintenance"
    if health_score < 80 or failure_risk > 50:
        return "Plan maintenance soon"
    return "Machine operating normally"

def create_alert(machine_id, alert_type, message):
    execute_query("""
        INSERT INTO alerts (machine_id, alert_type, message)
        VALUES (?, ?, ?)
    """, (machine_id, alert_type, message))

def update_twin_state(machine_id):
    latest = query_one("""
        SELECT *
        FROM sensor_readings
        WHERE machine_id = ?
        ORDER BY recorded_at DESC, id DESC
        LIMIT 1
    """, (machine_id,))

    if not latest:
        return None

    temperature = latest["temperature"]
    vibration = latest["vibration"]
    pressure = latest["pressure"]
    rpm = latest["rpm"]
    runtime_hours = latest["runtime_hours"]

    anomaly_status, failure_risk = predict_anomaly_and_risk(
        temperature, vibration, pressure, rpm, runtime_hours
    )

    health_score = calculate_health_score(temperature, vibration, pressure, rpm)
    health_label = get_health_label(health_score)
    action = recommend_action(health_score, anomaly_status, failure_risk)

    execute_query("""
        INSERT INTO twin_state (
            machine_id, health_score, anomaly_status, failure_risk, recommended_action
        )
        VALUES (?, ?, ?, ?, ?)
    """, (machine_id, health_score, anomaly_status, failure_risk, action))

    if anomaly_status == 1:
        create_alert(machine_id, "anomaly", f"Anomaly detected. {action}")

    if health_label == "warning":
        create_alert(machine_id, "warning", f"Health score warning: {health_score}. {action}")

    if health_label == "critical":
        create_alert(machine_id, "critical", f"Critical health score: {health_score}. {action}")

    if failure_risk > 60:
        create_alert(machine_id, "risk", f"Failure risk is {failure_risk}%. {action}")

    return {
        "machine_id": machine_id,
        "health_score": health_score,
        "health_label": health_label,
        "anomaly_status": anomaly_status,
        "failure_risk": failure_risk,
        "recommended_action": action
    }