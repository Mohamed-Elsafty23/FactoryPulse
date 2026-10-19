#!/usr/bin/env bash
# Download the Gold Parquet snapshot the dashboard reads.
#
# Run notebooks/98_export_for_dashboard.py in Databricks first; this pulls the
# result into ./exports/ so `streamlit run app/Home.py` works with no Azure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STORAGE=$(terraform -chdir=infra/terraform output -raw storage_account_name)
CONTAINER=$(terraform -chdir=infra/terraform output -raw lake_filesystem)

# A short-lived, read-only, user-delegation SAS: no account key is minted and
# it expires on its own.
EXPIRY=$(date -u -d "4 hours" '+%Y-%m-%dT%H:%MZ')
SAS=$(az storage container generate-sas \
        --account-name "$STORAGE" --name "$CONTAINER" \
        --permissions rl --expiry "$EXPIRY" \
        --auth-mode login --as-user -o tsv)

mkdir -p exports
azcopy copy \
  "https://${STORAGE}.blob.core.windows.net/${CONTAINER}/exports?${SAS}" \
  "./" --recursive

# azcopy nests the source folder name; flatten it.
if [[ -d exports/exports ]]; then
  mv exports/exports/* exports/
  rmdir exports/exports
fi

du -sh exports/
ls exports/
