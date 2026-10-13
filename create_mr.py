import os
import json
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests

# GitLab configuration from GitHub Actions secrets
token = os.environ["GITLAB_TOKEN"]
project_id = quote(os.environ["GITLAB_PROJECT_ID"], safe="")
base_url = f"https://gitlab.com/api/v4/projects/{project_id}"
headers = {"PRIVATE-TOKEN": token}

target_branch = "main"
source_branch = (
    f"ai-fix/{os.environ['GITHUB_RUN_ID']}-"
    f"{os.environ['GITHUB_RUN_ATTEMPT']}"
)

file_path = ".github/workflows/ci.yml"

# Read Gemini's analysis and the locally modified file
analysis = json.loads(Path("analysis.md").read_text())
fixed_code = Path(file_path).read_text()

# Recover the original file from the GitHub checkout
original_code = subprocess.check_output(
    ["git", "show", f"HEAD:{file_path}"],
    text=True
)

# Verify the change matches Gemini's proposed replacement
old = analysis["old_text"]
new = analysis["new_text"]

if (
    analysis.get("safe_to_apply") is not True
    or not isinstance(old, str)
    or not isinstance(new, str)
    or not old
    or old == new
    or original_code.count(old) != 1
    or original_code.replace(old, new, 1) != fixed_code
):
    raise RuntimeError("Proposed fix failed validation")

def gitlab_request(method, endpoint, **kwargs):
    response = requests.request(
        method,
        f"{base_url}{endpoint}",
        headers=headers,
        timeout=30,
        **kwargs
    )
    response.raise_for_status()
    return response

# Ensure GitLab main contains the source we analyzed
encoded_path = quote(file_path, safe="")
gitlab_original = gitlab_request(
    "GET",
    f"/repository/files/{encoded_path}/raw",
    params={"ref": target_branch}
).text

if gitlab_original != original_code:
    raise RuntimeError(
        "GitLab source differs from GitHub. "
        "Synchronize the repositories before creating an MR."
    )

# Create a new branch and commit the fix in one API request
gitlab_request(
    "POST",
    "/repository/commits",
    json={
        "branch": source_branch,
        "start_branch": target_branch,
        "commit_message": "fix(ci): AI-suggested pipeline fix",
        "actions": [
            {
                "action": "update",
                "file_path": file_path,
                "content": fixed_code
            }
        ]
    }
)

# Create the MR for human review
description = f"""## Root cause
{analysis['root_cause']}

## Suggested fix
{analysis['suggested_fix']}

## Review requirements
- AI-generated change
- Human review required
- No automatic merge
"""

mr = gitlab_request(
    "POST",
    "/merge_requests",
    json={
        "source_branch": source_branch,
        "target_branch": target_branch,
        "title": "fix(ci): AI-suggested pipeline repair",
        "description": description,
        "remove_source_branch": True
    }
).json()

print("Merge Request created:", mr["web_url"])
print("Merge Request state:", mr["state"])
Path("mr_url.txt").write_text(mr["web_url"], encoding="utf-8")