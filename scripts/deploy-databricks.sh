#!/usr/bin/env bash
# Build the wheel, publish it and the notebooks to the workspace, and sync the
# job definition.
#
# Auth is the Azure CLI identity, exchanged for a Databricks AAD token against
# the fixed first-party "AzureDatabricks" application id. That keeps this
# script working with no PAT on disk and no databricks CLI installed.
#
#   usage: scripts/deploy-databricks.sh [--run]
#          --run   trigger the medallion job afterwards and wait for it
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DBX_APP_ID=2ff814a6-3304-4ab8-85cb-cd0e6f879c1d
TF=infra/terraform

tfout() { terraform -chdir="$TF" output -raw "$1"; }

VERSION=$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)
WHEEL="factorypulse-${VERSION}-py3-none-any.whl"
TF_VERSION=$(grep -A3 'variable "wheel_version"' "$TF/variables.tf" | grep default | cut -d'"' -f2)

if [[ "$VERSION" != "$TF_VERSION" ]]; then
  echo "ERROR: pyproject version ($VERSION) != terraform wheel_version ($TF_VERSION)." >&2
  echo "       The job would install a different wheel than the one built here." >&2
  exit 1
fi

DBW=$(tfout databricks_workspace_url)
VOL=$(tfout wheel_volume_path)
TOKEN=$(az account get-access-token --resource "$DBX_APP_ID" --query accessToken -o tsv)
USER=$(curl -sf -H "Authorization: Bearer $TOKEN" "$DBW/api/2.0/preview/scim/v2/Me" \
       | python3 -c 'import json,sys; print(json.load(sys.stdin)["userName"])')

echo "==> workspace $DBW (as $USER), wheel $VERSION"

echo "==> building wheel"
rm -f dist/*.whl
python -m build --wheel >/dev/null
test -f "dist/$WHEEL"

echo "==> uploading $WHEEL to $VOL"
curl -sf -X PUT -H "Authorization: Bearer $TOKEN" --data-binary "@dist/$WHEEL" \
  "$DBW/api/2.0/fs/files${VOL}/${WHEEL}?overwrite=true"

echo "==> importing notebooks to /Users/$USER/factorypulse"
curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"path\":\"/Users/$USER/factorypulse\"}" "$DBW/api/2.0/workspace/mkdirs" >/dev/null
for file in notebooks/*.py; do
  name=$(basename "$file" .py)
  python3 -c "
import base64, json, sys
body = {
    'path': f'/Users/$USER/factorypulse/$name',
    'format': 'SOURCE', 'language': 'PYTHON', 'overwrite': True,
    'content': base64.b64encode(open('$file','rb').read()).decode(),
}
json.dump(body, sys.stdout)" \
  | curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d @- "$DBW/api/2.0/workspace/import" >/dev/null
  echo "    $name"
done

echo "==> syncing terraform (job points at $WHEEL)"
terraform -chdir="$TF" apply -auto-approve >/dev/null
echo "==> deployed"

[[ "${1:-}" == "--run" ]] || exit 0

JOB_ID=$(tfout databricks_job_id)
RUN_ID=$(curl -sf -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"job_id\": $JOB_ID}" "$DBW/api/2.1/jobs/run-now" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_id"])')
echo "==> run $RUN_ID: $DBW/jobs/$JOB_ID/runs/$RUN_ID"

while true; do
  # Refresh each poll: AAD tokens expire well inside a long medallion run.
  TOKEN=$(az account get-access-token --resource "$DBX_APP_ID" --query accessToken -o tsv)
  STATE=$(curl -sf -H "Authorization: Bearer $TOKEN" \
            "$DBW/api/2.1/jobs/runs/get?run_id=$RUN_ID" \
          | python3 "$ROOT/scripts/_run_status.py")
  echo "    [$(date +%H:%M:%S)] $STATE"
  case "$STATE" in TERMINATED*|INTERNAL_ERROR*|SKIPPED*) break ;; esac
  sleep 45
done

echo "$STATE" | grep -q SUCCESS || { echo "run did not succeed"; exit 1; }
