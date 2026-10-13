import os
import json
import base64
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests

# 1. GitHub configuration
token = os.environ["GEMINI_API_KEY"]
repo = os.environ["GITHUB_REPOSITORY"]

base_url = f"https://api.github.com/repos/{repo}"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

target_branch = "main"
source_branch = (
    f"ai-fix/{os.environ['GITHUB_RUN_ID']}-"
    f"{os.environ['GITHUB_RUN_ATTEMPT']}"
)

file_path = ".github/workflows/ci.yml"


# 2. GitHub API helper
def github_request(method, endpoint, **kwargs):
    response = requests.request(
        method,
        f"{base_url}{endpoint}",
        headers=headers,
        timeout=30,
        **kwargs
    )

    if not response.ok:
        raise RuntimeError(
            f"GitHub API failed ({response.status_code}): "
            f"{response.text[:1000]}"
        )

    return response.json()


# 3. Read Gemini's analysis and generated fix
analysis = json.loads(
    Path("analysis.md").read_text(encoding="utf-8")
)

fixed_code = Path(file_path).read_text(encoding="utf-8")

original_code = subprocess.check_output(
    ["git", "show", f"HEAD:{file_path}"],
    text=True
)

old = analysis["old_text"]
new = analysis["new_text"]

# 4. Validate the generated change
if (
    analysis.get("safe_to_apply") is not True
    or not isinstance(old, str)
    or not isinstance(new, str)
    or not old.strip()
    or not new.strip()
    or old == new
    or original_code.count(old) != 1
    or original_code.replace(old, new, 1) != fixed_code
):
    raise RuntimeError("Proposed fix failed validation")


# 5. Get the current main branch
main_ref = github_request(
    "GET",
    f"/git/ref/heads/{target_branch}"
)

main_sha = main_ref["object"]["sha"]


# 6. Get the original file from GitHub
encoded_path = quote(file_path, safe="")

github_file = github_request(
    "GET",
    f"/contents/{encoded_path}",
    params={"ref": target_branch}
)

github_original = base64.b64decode(
    github_file["content"]
).decode("utf-8")

if github_original != original_code:
    raise RuntimeError(
        "GitHub main differs from the analyzed source."
    )


# 7. Create a new branch from main
github_request(
    "POST",
    "/git/refs",
    json={
        "ref": f"refs/heads/{source_branch}",
        "sha": main_sha
    }
)

print("Created branch:", source_branch)


# 8. Commit Gemini's fix to the new branch
github_request(
    "PUT",
    f"/contents/{encoded_path}",
    json={
        "message": "fix(ci): AI-suggested pipeline repair",
        "content": base64.b64encode(
            fixed_code.encode("utf-8")
        ).decode("ascii"),
        "sha": github_file["sha"],
        "branch": source_branch
    }
)

print("Fix committed to:", source_branch)


# 9. Create a Pull Request
description = f"""## Root cause
{analysis['root_cause']}

## Suggested fix
{analysis['suggested_fix']}

## Review requirements
- AI-generated code change
- Human review required
- No automatic merge
"""

pr = github_request(
    "POST",
    "/pulls",
    json={
        "title": "fix(ci): AI-suggested pipeline repair",
        "head": source_branch,
        "base": target_branch,
        "body": description,
        "draft": True
    }
)

print("Pull Request created:", pr["html_url"])
print("PR state:", pr["state"])

# 10. Save PR URL for email notification
Path("pr_url.txt").write_text(
    pr["html_url"],
    encoding="utf-8"
)