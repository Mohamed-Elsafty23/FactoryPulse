#!/usr/bin/env bash
# Generate the ignored .azure-env file from live Terraform outputs.
set -euo pipefail
cd "$(dirname "$0")/../infra/terraform"

cat > ../../.azure-env <<VARS
# AUTO-GENERATED from terraform output. Do not edit by hand.
export FP_RG=$(terraform output -raw resource_group_name)
export FP_LOC=$(terraform output -raw location)
export FP_STORAGE=$(terraform output -raw storage_account_name)
export FP_KV=$(terraform output -raw key_vault_name)
export FP_SQL_FQDN=$(terraform output -raw sql_server_fqdn)
export FP_SQL_DB=$(terraform output -raw sql_database_name)
export FP_SQL_USER=$(terraform output -raw sql_admin_user)
export FP_ABFSS=$(terraform output -raw abfss_root)
VARS
echo "wrote .azure-env"
