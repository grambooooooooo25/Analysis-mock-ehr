from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import csv
import io
import re

app = Flask(__name__)
CORS(app)

WEBSITE_UPLOAD_URL = "https://mock-ehr.onrender.com/upload-session"


def google_drive_direct_link(url):
    match = re.search(r"/d/([^/]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return url


def num(x):
    try:
        return float(x)
    except:
        return 0.0


def analyze_csv(csv_text):
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    if not rows:
        raise ValueError("CSV file is empty.")

    patient_id = rows[0].get("PatientID", "Patient_Unknown").strip()
    session_id = "Session_" + rows[0].get("SessionID", "Unknown").strip()

    harsh = 0
    rapid = 0
    turns = 0
    swerve = 0

    for r in rows:
        ax = num(r.get("AccelX", 0))
        gy = abs(num(r.get("GyroY", 0)))
        gz = abs(num(r.get("GyroZ", 0)))

        if ax < -0.30:
            harsh += 1
        if ax > 0.30:
            rapid += 1
        if gz > 50:
            turns += 1
        if gy > 50:
            swerve += 1

    score = min((harsh * 2) + (rapid * 2) + (turns * 3) + (swerve * 3), 100)

    if score >= 61:
        risk = "High Risk"
    elif score >= 31:
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

    issues_text = ", ".join(issues) if issues else "No major abnormal patterns detected."

    action = (
        "Clinician or supervisor review recommended."
        if risk == "High Risk"
        else "Continue monitoring."
        if risk == "Caution"
        else "No immediate action required."
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
"""

    return {
        "patient_id": patient_id,
        "session_id": session_id,
        "risk_level": risk,
        "risk_score": score,
        "key_issues": issues_text,
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

    file_url = data.get("file_url")
    if not file_url:
        return jsonify({"error": "Missing file_url"}), 400

    direct_url = google_drive_direct_link(file_url)

    response = requests.get(direct_url)
    if response.status_code != 200:
        return jsonify({"error": "Could not download CSV file"}), 400

    csv_text = response.text

    try:
        result = analyze_csv(csv_text)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Send results to website
    website_payload = {
        "patient_id": result["patient_id"],
        "session_id": result["session_id"],
        "risk_level": result["risk_level"],
        "risk_score": result["risk_score"],
        "key_issues": result["key_issues"],
        "recommended_action": result["recommended_action"],
        "warning": result["warning"],
        "warning_text": result["warning_text"],
        "warning_filename": result["warning_filename"],
        "raw_file_url": file_url
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

    # Return results back to Zapier
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)