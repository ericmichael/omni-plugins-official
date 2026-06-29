# Internal Azure HIPAA Reference Architecture

This is the target architecture for internal Azure apps that may handle PHI/ePHI. The Omni Desktop infrastructure is a useful pattern source, especially for managed identity, private data plane, CMK, diagnostics, custom roles, and cleanup automation. For new systems, prefer an even stricter private-first ingress posture.

## Target Shape

- Ingress uses approved corporate/private access where possible: private endpoint-backed App Service, Application Gateway private frontend, VPN/ExpressRoute, or another approved internal entry path.
- If public ingress is required, place Azure Front Door Premium or Application Gateway WAF in front, require Entra authentication, enforce HTTPS, and log all access.
- App runtimes use VNet integration and reach dependencies through private endpoints, private DNS, delegated subnets, or Private Link.
- Data stores are private: PostgreSQL Flexible Server private networking, Storage private endpoints for Blob/File/Queue/Table as used, Key Vault private endpoint, and private endpoints for additional Azure services.
- Workloads authenticate to Azure resources with user-assigned managed identities and least-privilege roles.
- Runtime secrets live in Key Vault; app settings contain Key Vault references or non-secret resource identifiers.
- Durable PHI stores use platform encryption and customer-managed keys when supported and operationally sustainable.
- Logs go to Log Analytics for operational search and to immutable Storage for long-term audit retention.
- Azure Policy and Defender for Cloud monitor drift and insecure configuration.

## Omni Desktop Pattern Matches

The current Omni Desktop Bicep demonstrates several reusable patterns:

- User-assigned managed identity shared by App Service, Function, Storage encryption, Postgres CMK, Key Vault access, ACR pulls, and ACI management.
- Private PostgreSQL Flexible Server on a delegated subnet with private DNS.
- Private Key Vault, Storage File, and Storage Blob endpoints linked to private DNS zones.
- Customer-managed key in Key Vault used for Storage and Postgres encryption.
- Key Vault references for database URLs, runtime token secret, app encryption key, AAD secret, and storage account key.
- Custom ACI manager role rather than resource-group Contributor.
- NSG rules that isolate untrusted sandbox compute from database, launcher, and peer sandboxes.
- Diagnostic settings for App Service, Postgres, ACR, Key Vault, Azure Files, and cleanup Function.
- Separate Timer-triggered cleanup Function for orphaned compute independent of launcher health.

## Intentional Differences For New Apps

- Do not treat public App Service as the preferred baseline. Classify it as `Public With Justification` if needed.
- Add WAF and edge/origin restrictions for public web apps.
- Add immutable long-term audit archive, not only Log Analytics retention.
- Add Defender for Cloud pricing resources and Azure Policy assignments for continuous posture checks.
- Add Action Groups and alerts for security and availability signals.
- Increase backup/HA posture where app criticality requires it.

## Resource Classification

For every resource in a review, classify network posture:

| Status | Meaning |
| --- | --- |
| Private | Uses private endpoint, VNet injection, delegated subnet, Private Link, private DNS, or equivalent private-only access. |
| Public With Justification | Public ingress is required and protected by compensating controls. Document why. |
| Public Gap | Public network access exists without a clear requirement or adequate controls. |
| Not Applicable | Resource has no network surface or cannot be privately networked. |

## Common App Variants

- Queue/event workloads: use Service Bus or Event Grid with private endpoints, managed identity, diagnostic logs, and dead-letter monitoring.
- Cache: use Azure Cache for Redis private endpoint, TLS-only, Entra/RBAC where available, and no public network access.
- Search/AI: use private endpoints for Azure AI Search and Azure OpenAI/Azure AI services where supported; disable local key auth when feasible.
- Containers: prefer private Container Apps environments or AKS private clusters for service backends; avoid public container app ingress unless justified.
