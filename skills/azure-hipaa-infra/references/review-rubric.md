# Review Rubric

Use this rubric to make findings consistent across internal Azure apps.

## Severity

- Critical: likely unauthorized ePHI exposure or inability to audit ePHI access. Examples: public Storage container with PHI, public database, committed secrets, unauthenticated app route exposing PHI.
- High: strong control missing on a PHI path. Examples: public network access on data service, broad runtime Contributor role, no Key Vault, no diagnostic logs for PHI store, no backup strategy.
- Medium: important hardening or continuous assurance missing. Examples: no WAF on public ingress, no immutable archive, no Defender plan, no alerting, no Azure Policy assignment.
- Low: hygiene or documentation issue. Examples: missing tags, incomplete runbook, missing verification command, inconsistent naming.

## Owner Labels

- Bicep: fix is primarily infrastructure-as-code.
- App Code: fix requires application behavior, schema, authz, tenant isolation, or logging changes.
- CI/CD: fix requires build/release workflow, image scanning, signing, approval gates, or deployment checks.
- Azure Portal/Entra: fix is an identity/tenant configuration not fully represented in Bicep.
- Policy/Process: fix is governance, legal, procedure, evidence, or human workflow.

## Review Checklist

1. Data classification: identify ePHI stores, processors, logs, backups, and exports.
2. Ingress: classify each public endpoint and verify auth, WAF, TLS, logs, and justification.
3. Private networking: verify data services and service dependencies are private where supported.
4. Identity: inspect managed identities, role assignments, custom roles, user auth, admin paths, and break-glass assumptions.
5. Secrets: verify Key Vault, secret references, secure parameters, no committed secrets, rotation considerations.
6. Encryption: verify TLS, platform encryption, CMK for durable PHI stores, and app-level encryption for sensitive fields where used.
7. Audit: verify diagnostic settings, data-plane logs, immutable archive, retention, and alerting.
8. Backup and resilience: verify retention, HA/geo-redundancy, restore drills, and operational runbooks.
9. Continuous posture: verify Defender, Azure Policy, CI/CD checks, vulnerability scanning, and deployment approval evidence.
10. Non-IaC: list BAA, risk analysis, access reviews, training, incident response, and breach process dependencies.

## Finding Template

```markdown
- [Severity] [Short finding]
  - Evidence: [file/resource/setting]
  - Risk: [why this matters for ePHI/HIPAA posture]
  - Owner: [Bicep/App Code/CI/CD/Azure Portal/Policy]
  - Recommendation: [specific change]
  - Verification: [command, test, or evidence]
```
