# Azure Bicep Patterns

Use these patterns as building blocks. Prefer current Azure API versions from the target repo or `az provider show` when implementing.

## Example Index

| Example | Use When |
| --- | --- |
| `examples/app-service-private-easyauth.bicep` | Web app needs private ingress, managed identity, VNet integration, EasyAuth notes, and Key Vault references. |
| `examples/postgres-private-cmk.bicep` | PostgreSQL Flexible Server should be private, encrypted with a Key Vault CMK, and backed up. |
| `examples/storage-private-immutable-logs.bicep` | Storage needs private endpoints, CMK, diagnostic logs, and immutable audit archive. |
| `examples/keyvault-private-rbac-cmk.bicep` | Key Vault should be private, RBAC-enabled, purge-protected, and hold CMKs/secrets. |
| `examples/diagnostics-log-analytics.bicep` | Any resource should send logs and metrics to Log Analytics. |
| `examples/frontdoor-waf.bicep` | Public web ingress requires WAF and edge controls. |
| `examples/defender-policy-alerts.bicep` | Subscription/resource group needs Defender, Azure Policy, and alert scaffolding. |
| `examples/managed-identity-least-privilege.bicep` | Runtime identity needs narrow custom roles instead of Contributor. |

## Private Networking Checklist

For each service, look for:

- `publicNetworkAccess: 'Disabled'` when supported.
- Private endpoint resource for each required subresource: Blob/File/Queue/Table, vault, sites, database, namespace, account, etc.
- Private DNS zone and VNet link for each private endpoint family.
- VNet integration or delegated subnet for compute that calls private endpoints.
- NSG rules that deny lateral movement and protect management/data subnets.
- No broad public IP allowlists unless explicitly justified.

## Diagnostics Checklist

For each PHI-bearing or security-sensitive resource, add `Microsoft.Insights/diagnosticSettings` with:

- `workspaceId` for Log Analytics.
- Relevant `logs` categories or `categoryGroup: 'allLogs'` where supported.
- `metrics` enabled where supported.
- Optional `storageAccountId` pointing to immutable archive storage for long-term retention.

## Secret Handling Checklist

- Key Vault has RBAC authorization, purge protection, soft delete, diagnostics, and private endpoint.
- App settings use Key Vault references for secrets.
- Managed identities receive only required data-plane roles.
- Deployment parameters marked `@secure()` for secrets.
- Gitignored env files are allowed for local/deploy orchestration but must not be committed.

## Backup And Resilience Checklist

- PostgreSQL `backupRetentionDays` matches app criticality and policy.
- `geoRedundantBackup` and HA are enabled when RTO/RPO requires them and the region/SKU supports it.
- Storage soft delete/versioning/immutability are enabled for audit archive and critical Blob data.
- Alerts cover backup failures, storage capacity, database CPU/storage, app health, and Key Vault access anomalies.
