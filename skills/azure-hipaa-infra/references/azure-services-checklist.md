# Azure Services Checklist

Use this when reviewing apps that include services beyond the core App Service/Postgres/Storage/Key Vault shape.

| Service | Private Networking | Identity | Logging | Encryption/Backup Notes |
| --- | --- | --- | --- | --- |
| App Service | Private endpoint for inbound when possible; VNet integration for outbound; access restrictions for public exceptions | Managed identity; EasyAuth/Entra for user auth | AppServiceHTTPLogs, ConsoleLogs, AuditLogs, metrics | HTTPS-only; Key Vault refs; health checks |
| Azure Front Door Premium | Private Link origin when possible; WAF policy | Managed identity for Key Vault certs if used | Access logs, WAF logs, health probes | TLS policy; origin host restrictions |
| Application Gateway | Private frontend for internal apps; WAF_v2 for public/internal ingress | Managed identity for Key Vault certs | Access, performance, firewall logs | TLS policy; cert rotation |
| PostgreSQL Flexible Server | Private access with delegated subnet and private DNS | App role should not be superuser; Entra auth if adopted | PostgreSQL logs, metrics | CMK where required; backups/HA/geo-redundancy |
| Storage Account | Private endpoints for Blob/File/Queue/Table as used | Managed identity/RBAC preferred; account keys only with documented need | StorageRead/Write/Delete logs; metrics | CMK; soft delete; versioning; immutable containers for audit |
| Key Vault | Private endpoint and private DNS | RBAC mode; managed identities | AuditEvent logs, metrics | Purge protection; soft delete; key rotation plan |
| Service Bus | Private endpoint; public network disabled | Managed identity/RBAC | Operational logs, metrics | DLQ monitoring; duplicate detection where needed |
| Event Grid | Private endpoints for topics/domains where supported | Managed identity/RBAC | Delivery failures, publish failures | Dead-letter destination private and monitored |
| Azure Cache for Redis | Private endpoint; public disabled where supported | Entra auth/RBAC where available | Connection and server load metrics | TLS-only; persistence if required |
| Cosmos DB | Private endpoint; public disabled; disable local auth when feasible | Managed identity/RBAC | DataPlaneRequests, QueryRuntimeStatistics, metrics | CMK if required; backup mode/retention |
| Azure AI Search | Private endpoint; public disabled | Managed identity/RBAC where feasible | Operation logs, metrics | CMK if required; disable admin keys if possible |
| Azure OpenAI / AI Services | Private endpoint where supported; public disabled | Managed identity/RBAC | Audit/resource logs, metrics | Data handling policy review required |
| Container Apps | Internal environment for private apps; private endpoints for dependencies | Managed identity | System/application logs | Secrets from Key Vault; image scanning |
| Azure Functions | Private endpoint for inbound if HTTP; VNet integration for outbound | Managed identity | Function logs, AppService logs, metrics | Key Vault refs; storage account private/locked down |
| ACR | Public may be acceptable for images only if admin disabled; private endpoint preferred when runtime supports it | Managed identity AcrPull | Repository events, login events | Defender scanning; content trust/signing if adopted |

## Review Questions

- Does this service store, process, transmit, or log ePHI?
- Can public network access be disabled without breaking the app?
- Which private DNS zone is required and is it VNet-linked?
- Which identity performs data-plane actions, and is its role scoped narrowly?
- Are diagnostic logs enabled for both management-plane and data-plane activity?
- Does backup/retention match the app's RTO/RPO and audit needs?
