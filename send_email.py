import os
import json
import smtplib
from pathlib import Path
from email.message import EmailMessage

# Read Gemini's analysis
analysis_file = Path("analysis.md")

if analysis_file.exists():
    analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
    root_cause = analysis.get("root_cause", "Unknown")
    suggested_fix = analysis.get("suggested_fix", "Not available")
else:
    root_cause = "AI analysis did not complete"
    suggested_fix = "Manual investigation required"

# Read MR URL if creation succeeded
mr_file = Path("pr_url.txt")

if mr_file.exists():
    mr_status = "Open - pending human review"
    mr_url = mr_file.read_text(encoding="utf-8").strip()
else:
    mr_status = "Not created - investigation required"
    mr_url = "Unavailable"

# Prepare email
msg = EmailMessage()

msg["Subject"] = "CI Failure - AI Analysis and Suggested Fix"
msg["From"] = os.environ["SMTP_USER"]
msg["To"] = os.environ["EMAIL_TO"]

msg.set_content(f"""
CI FAILURE ANALYSIS

Repository: {os.environ.get("GITHUB_REPOSITORY", "Unknown")}

ROOT CAUSE:
{root_cause}

SUGGESTED FIX:
{suggested_fix}

GITLAB MERGE REQUEST:
{mr_url}

STATUS:
{mr_status}

GITHUB ACTIONS RUN:
{os.environ.get("GITHUB_SERVER_URL", "https://github.com")}/{os.environ.get("GITHUB_REPOSITORY", "")}/actions/runs/{os.environ.get("GITHUB_RUN_ID", "")}

This email was generated automatically by the CI Failure Analyzer.
The AI agent does not merge changes.
""")

# Send email through SMTP over TLS
with smtplib.SMTP_SSL(
    os.environ.get("SMTP_HOST", "smtp.gmail.com"),
    465
) as smtp:
    smtp.login(
        os.environ["SMTP_USER"],
        os.environ["SMTP_PASSWORD"]
    )
    smtp.send_message(msg)

print("Email sent successfully")