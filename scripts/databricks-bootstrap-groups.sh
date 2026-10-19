#!/usr/bin/env bash
set -euo pipefail

: "${DATABRICKS_HOST:?Set DATABRICKS_HOST to the Azure Databricks workspace URL}"

dbx="${DATABRICKS_CLI:-$HOME/bin/databricks}"
current_user_id="$($dbx current-user me --output json | jq -r .id)"

ensure_group() {
  local name="$1"
  local id
  id="$($dbx api get /api/2.0/account/scim/v2/Groups \
    | jq -r --arg name "$name" '.Resources[] | select(.displayName == $name) | .id' \
    | head -1)"

  if [[ -z "$id" ]]; then
    id="$($dbx api post /api/2.0/account/scim/v2/Groups \
      --json "{\"displayName\":\"$name\"}" | jq -r .id)"
  fi

  printf '%s\t%s\n' "$id" "$name"
}

engineers_id="$(ensure_group factorypulse_engineers | cut -f1)"
ensure_group factorypulse_analysts
ensure_group factorypulse_plant_managers

$dbx api patch "/api/2.0/account/scim/v2/Groups/${engineers_id}" --json "$(jq -nc \
  --arg user_id "$current_user_id" \
  '{schemas:["urn:ietf:params:scim:api:messages:2.0:PatchOp"],Operations:[{op:"add",path:"members",value:[{value:$user_id}]}]}')" >/dev/null

echo "Current user added to factorypulse_engineers."
