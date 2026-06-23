import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "model.pkl")

def train_and_save_model():
    rng = np.random.RandomState(42)

    normal_data = np.column_stack([
        rng.normal(65, 5, 600),
        rng.normal(3.0, 0.7, 600),
        rng.normal(95, 10, 600),
        rng.normal(2200, 250, 600),
        rng.normal(120, 30, 600),
    ])

    model = IsolationForest(
        n_estimators=150,
        contamination=0.08,
        random_state=42
    )
    model.fit(normal_data)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)

def load_model():
    if not os.path.exists(MODEL_PATH):
        train_and_save_model()
    return joblib.load(MODEL_PATH)

model = load_model()

def predict_anomaly_and_risk(temperature, vibration, pressure, rpm, runtime_hours):
    values = np.array([[temperature, vibration, pressure, rpm, runtime_hours]])
    prediction = model.predict(values)[0]
    decision_score = model.decision_function(values)[0]

    anomaly_status = 1 if prediction == -1 else 0

    normalized_risk = (0.5 - decision_score) * 100
    failure_risk = round(max(0.0, min(100.0, normalized_risk)), 2)

    return anomaly_status, failure_risk