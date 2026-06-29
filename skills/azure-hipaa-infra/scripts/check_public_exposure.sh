#!/usr/bin/env bash
set -euo pipefail

RG="${1:?usage: check_public_exposure.sh <resource-group>}"

echo "== Public IP addresses =="
az network public-ip list -g "$RG" --query "[].{name:name,ip:ipAddress,sku:sku.name,allocation:publicIPAllocationMethod}" -o table

echo
echo "== Storage accounts with public network access or blob public access =="
az storage account list -g "$RG" --query "[?publicNetworkAccess!='Disabled' || allowBlobPublicAccess==\`true\`].{name:name,publicNetworkAccess:publicNetworkAccess,allowBlobPublicAccess:allowBlobPublicAccess,defaultAction:networkRuleSet.defaultAction}" -o table

echo
echo "== Key Vaults with public network access =="
az keyvault list -g "$RG" --query "[?properties.publicNetworkAccess!='Disabled'].{name:name,publicNetworkAccess:properties.publicNetworkAccess,defaultAction:properties.networkAcls.defaultAction}" -o table

echo
echo "== App Services with public network access =="
az webapp list -g "$RG" --query "[?publicNetworkAccess!='Disabled'].{name:name,host:defaultHostName,httpsOnly:httpsOnly,publicNetworkAccess:publicNetworkAccess}" -o table

echo
echo "== PostgreSQL Flexible Servers and network mode =="
az postgres flexible-server list -g "$RG" --query "[].{name:name,publicNetworkAccess:network.publicNetworkAccess,delegatedSubnet:network.delegatedSubnetResourceId,privateDns:network.privateDnsZoneArmResourceId}" -o table
