#!/usr/bin/env bash
set -euo pipefail

RG="${1:?usage: check_azure_live_controls.sh <resource-group>}"

echo "== Private endpoints =="
az network private-endpoint list -g "$RG" --query "[].{name:name,subnet:subnet.id,connections:privateLinkServiceConnections[].privateLinkServiceId}" -o table

echo
echo "== Diagnostic settings by resource =="
RESOURCE_IDS=$(az resource list -g "$RG" --query "[].id" -o tsv)
while IFS= read -r RESOURCE_ID; do
  [[ -n "$RESOURCE_ID" ]] || continue
  COUNT=$(az monitor diagnostic-settings list --resource "$RESOURCE_ID" --query "length(value)" -o tsv 2>/dev/null || echo 0)
  if [[ "$COUNT" != "0" ]]; then
    echo "$COUNT diagnostics: $RESOURCE_ID"
  fi
done <<< "$RESOURCE_IDS"

echo
echo "== Key Vault purge protection and RBAC =="
az keyvault list -g "$RG" --query "[].{name:name,publicNetworkAccess:properties.publicNetworkAccess,enableRbacAuthorization:properties.enableRbacAuthorization,enablePurgeProtection:properties.enablePurgeProtection}" -o table

echo
echo "== Storage encryption and immutability signals =="
az storage account list -g "$RG" --query "[].{name:name,publicNetworkAccess:publicNetworkAccess,httpsOnly:supportsHttpsTrafficOnly,keySource:encryption.keySource,allowBlobPublicAccess:allowBlobPublicAccess}" -o table

echo
echo "== App Service auth and HTTPS =="
for APP in $(az webapp list -g "$RG" --query "[].name" -o tsv); do
  echo "-- $APP"
  az webapp show -g "$RG" -n "$APP" --query "{httpsOnly:httpsOnly,publicNetworkAccess:publicNetworkAccess,clientAffinityEnabled:clientAffinityEnabled}" -o table
  az webapp auth show -g "$RG" -n "$APP" --query "{platformEnabled:platform.enabled,requireAuthentication:globalValidation.requireAuthentication,unauthenticatedClientAction:globalValidation.unauthenticatedClientAction}" -o table 2>/dev/null || true
done

echo
echo "== Role assignments for managed identities in resource group =="
az role assignment list --resource-group "$RG" --query "[].{principalName:principalName,principalType:principalType,role:roleDefinitionName,scope:scope}" -o table
