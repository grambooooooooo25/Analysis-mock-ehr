from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import csv
import io 

app = Flask(__name__)
CORS(app)

WEBSITE_UPLOAD_URL = "https://mock-ehr.onrender.com/upload-session"


def num(x):
    try:
        return float(x)
    except:
        return 0.0


def analyze_csv(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    if not rows:
        raise ValueError("CSV file is empty.")

    rows = [{str(k).strip(): str(v).strip() for k, v in row.items()} for row in rows]

    required_cols = [
        "PatientID", "SessionID", "Time",
        "AccelX", "AccelY", "AccelZ",
        "GyroX", "GyroY", "GyroZ",
        "MagX", "MagY", "MagZ"
    ]

    missing = [col for col in required_cols if col not in rows[0]]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found columns: {list(rows[0].keys())}")

    patient_id = rows[0].get("PatientID", "Patient_Unknown").strip()
    session_id = "Session_" + rows[0].get("SessionID", "Unknown").strip()

    harsh = 0
    rapid = 0
    turns = 0
    swerve = 0
    instability = 0

    for r in rows:
        ax = num(r.get("AccelX", 0))
        gy = abs(num(r.get("GyroY", 0)))
        gz = abs(num(r.get("GyroZ", 0)))

        gx = num(r.get("GyroX", 0))
        gyro_mag = (gx ** 2 + gy ** 2 + gz ** 2) ** 0.5

        if ax < -0.30:
            harsh += 1
        if ax > 0.30:
            rapid += 1
        if gz > 50:
            turns += 1
        if gy > 50:
            swerve += 1
        if gyro_mag > 75:
            instability += 1

    score = min(
        harsh * 2 +
        rapid * 2 +
        turns * 3 +
        swerve * 3 +
        instability * 2,
        100
    )

    if score >= 61:
        risk = "High Risk"
    elif score >= 30:
        risk = "Caution"
    else:
        risk = "Normal"

    issues = []
    if harsh:
        issues.append("harsh braking")
    if rapid:
        issues.append("rapid acceleration")
    if turns:
        issues.append("sharp turns")
    if swerve:
        issues.append("swerving")
    if instability:
        issues.append("instability")

    issues_text = ", ".join(issues) if issues else "No major abnormal patterns detected."

    action = (
        "Clinician or supervisor review recommended."
        if risk == "High Risk"
        else "Continue monitoring."
        if risk == "Caution"
        else "No immediate action required."
    )

    summary = (
        f"{session_id} for {patient_id} was classified as {risk} "
        f"with a risk score of {score}/100. Issues detected: {issues_text}."
    )

    warning_text = f"""DRIVING RISK WARNING

Patient ID: {patient_id}
Session ID: {session_id}
Risk Level: {risk}
Risk Score: {score}

Key Issues:
{issues_text}

Recommended Action:
{action}

Disclaimer:
This system does not diagnose medical conditions. It flags driving behavior patterns that may require human review.
"""

    return {
        "patient_id": patient_id,
        "session_id": session_id,
        "risk_level": risk,
        "risk_score": score,
        "key_issues": issues_text,
        "summary_report": summary,
        "recommended_action": action,
        "warning": "YES" if risk == "High Risk" else "NO",
        "warning_text": warning_text,
        "warning_filename": f"{patient_id}_{session_id}_warning.txt"
    }


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Driving Analysis API is running"})


@app.route("/analyze-drive", methods=["POST"])
def analyze_drive():
    data = request.get_json(force=True)

    csv_text = data.get("csv_text")

    if not csv_text:
        return jsonify({"error": "Missing csv_text"}), 400

    try:
        result = analyze_csv(csv_text)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    website_payload = {
        "patient_id": result["patient_id"],
        "session_id": result["session_id"],
        "risk_level": result["risk_level"],
        "risk_score": result["risk_score"],
        "key_issues": result["key_issues"],
        "summary_report": result["summary_report"],
        "recommended_action": result["recommended_action"],
        "warning": "YES" if result["risk_score"] > 30 else "NO",
        "create_alert": True if result["risk_score"] > 30 else False,
        "alert_message": result["warning_text"] if result["risk_score"] > 30 else "",
        "warning_filename": result["warning_filename"],
        "raw_content": csv_text,
        "raw_filename": f'{result["patient_id"]}_{result["session_id"]}_raw.csv'
    }

    try:
        website_response = requests.post(
            WEBSITE_UPLOAD_URL,
            json=website_payload,
            timeout=10
        )

        result["website_status_code"] = website_response.status_code
        result["website_upload_success"] = website_response.status_code in [200, 201]

    except Exception as e:
        result["website_upload_success"] = False
        result["website_error"] = str(e)

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)