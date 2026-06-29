# HIPAA Control Map for Azure Infrastructure

Use this as a practical mapping aid for HIPAA Security Rule technical safeguards and adjacent administrative safeguards. It is not legal advice and does not replace a formal risk analysis.

## Technical Safeguards

| HIPAA Area | Azure Evidence To Look For | Common Gaps | Typical Owner |
| --- | --- | --- | --- |
| Access Control — 45 CFR 164.312(a) | Entra ID/EasyAuth, managed identities, Azure RBAC, least-privilege custom roles, app tenant isolation, database RLS | Shared credentials, broad Contributor, local admin paths, public admin endpoints, app role can bypass RLS | Bicep, App Code, Entra |
| Unique User Identification — 164.312(a)(2)(i) | Entra users/groups, app logs include user/tenant IDs, no shared human accounts | Shared service accounts for users, missing principal in audit trails | Entra, App Code |
| Emergency Access — 164.312(a)(2)(ii) | Break-glass accounts, documented access path, monitored use | No break-glass process, unmonitored emergency role | Policy/Process, Entra |
| Automatic Logoff — 164.312(a)(2)(iii) | Auth/session timeout policy, refresh-token lifetime, app session expiry, WebSocket token TTL | Long-lived app sessions, no timeout enforcement | App Code, Entra |
| Encryption/Decryption — 164.312(a)(2)(iv) | CMK where supported, Key Vault keys, app-level encryption for sensitive fields, TLS | Microsoft-managed keys only for PHI stores without rationale, secrets in plaintext settings | Bicep, App Code |
| Audit Controls — 164.312(b) | Diagnostic settings, Log Analytics, immutable archive, Azure Files/Blob data-plane logs, Key Vault audit logs, alerts | Logs missing for data-plane access, short retention, mutable logs, no alerting | Bicep, SecOps |
| Integrity — 164.312(c) | RBAC boundaries, private networking, database constraints/RLS, backup restore tests, deployment approvals | App superuser access, broad write roles, no restore evidence, unreviewed production changes | Bicep, App Code, CI/CD |
| Person or Entity Authentication — 164.312(d) | Entra auth, workload managed identity, no static Azure credentials, MFA/Conditional Access | Client secrets in app settings, local passwords, no MFA policy evidence | Entra, Bicep |
| Transmission Security — 164.312(e) | HTTPS-only, TLS minimums, private endpoints, private DNS, WAF, no public data endpoints | Public Storage/Postgres/Key Vault, HTTP allowed, direct public origin | Bicep |

## Administrative/Operational Requirements To Surface

These are usually not solved by Bicep alone:

- Business Associate Agreements for Azure and any subprocessors.
- Formal security risk analysis and risk management plan.
- Workforce access policies, onboarding/offboarding, and training.
- Access reviews for Entra groups, Azure RBAC, database roles, and app admin roles.
- Incident response, breach notification, sanctions, and audit evidence procedures.
- Backup restore drills with documented RTO/RPO evidence.
- Change management and production deployment approval records.

## Risk Rating Guidance

- Critical: public ePHI data store, unauthenticated PHI access path, plaintext committed secrets, or missing audit trail for PHI access.
- High: public network exposure without justification, broad Contributor/Owner for runtime identity, no Key Vault for secrets, no backup/restore posture.
- Medium: missing WAF/Defender/alerts, short log retention, CMK absent where required by internal standard, incomplete diagnostic coverage.
- Low: documentation drift, missing verification commands, naming/tagging gaps, non-PHI service lacking optional hardening.
