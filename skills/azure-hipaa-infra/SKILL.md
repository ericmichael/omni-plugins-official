---
name: azure-hipaa-infra
description: Internal Azure HIPAA infrastructure review and hardening playbook. Use this skill whenever the user is designing, reviewing, or modifying Azure infrastructure for apps that may handle PHI/ePHI or require HIPAA-aligned controls. Use it for Azure Bicep, App Service, Entra ID/EasyAuth, managed identities, private networking, PostgreSQL Flexible Server, Storage, Key Vault, customer-managed keys, diagnostics, immutable audit logs, Defender for Cloud, Azure Policy, WAF, alerts, and Azure verification. The skill uses our Omni Desktop Azure infrastructure as a reference pattern, recommends private networking everywhere Azure supports it, produces Azure-specific control mappings and gap analyses, separates Bicep/app/CI/CD/manual/process ownership, and avoids claiming technical controls alone make a system HIPAA compliant.
---

# Azure HIPAA Infrastructure

This skill reviews, designs, and hardens internal Azure application infrastructure for HIPAA-aligned deployments. It is intentionally Azure-only and opinionated for our apps: private networking by default, managed identity over static credentials, Key Vault-backed secrets, customer-managed encryption where practical, auditable operations, and repeatable Bicep.

Technical safeguards support HIPAA compliance; they do not prove compliance alone. Always distinguish infrastructure controls from administrative requirements such as BAA coverage, risk analysis, access reviews, workforce training, incident response, breach procedures, and audit evidence retention.

## Default Standards

Use these standards unless the user explicitly states a documented exception.

- Prefer private networking for every Azure service that supports private endpoint, VNet injection, delegated subnet, Private Link, or private DNS.
- Treat public ingress as an exception. If required, recommend Entra authentication, WAF, strict TLS, diagnostics, rate limits, alerting, and explicit approval.
- Keep data-plane services private: PostgreSQL, Storage, Key Vault, Service Bus, Redis, Cosmos DB, Azure AI services, Search, Container Apps environments, and any service holding or processing ePHI.
- Use user-assigned managed identities and least-privilege custom roles instead of shared credentials or broad Contributor assignments.
- Store runtime secrets in Key Vault and use Key Vault references or managed-identity data-plane access; never recommend plaintext secrets in app settings.
- Encrypt at rest with platform encryption everywhere and customer-managed keys for PHI-bearing durable stores where Azure supports it and operations can manage key lifecycle.
- Send resource, data-plane, and security logs to Log Analytics and long-term immutable archive storage when retention requirements exceed interactive workspace limits.
- Use Azure Policy, Defender for Cloud, alerts, and verification scripts to make the posture continuously checkable.

## Review Workflow

1. Read the infrastructure source of truth first: Bicep modules, parameter files, deployment scripts, environment templates, and deployment docs.
2. Trace data flow: where ePHI enters, where it is stored, which identities can access it, where logs are written, and which services cross network boundaries.
3. Classify every Azure resource by network posture: `Private`, `Public With Justification`, `Public Gap`, or `Not Applicable`.
4. Map current evidence to HIPAA Security Rule technical safeguards and internal Azure standards.
5. Produce risk-ranked gaps with concrete owners: `Bicep`, `App Code`, `CI/CD`, `Azure Portal/Entra`, or `Policy/Process`.
6. Prefer Bicep snippets or exact Azure settings for technical gaps; include live verification commands when possible.

## Output Format

For reviews, use this structure:

```markdown
## Summary
[2-4 sentence posture summary. Say HIPAA-aligned or supports HIPAA compliance, not legally compliant.]

## Control Matrix
| Control Area | Azure Evidence | Gap | Risk | Owner | Recommendation | Verification |
| --- | --- | --- | --- | --- | --- | --- |

## Network Posture
| Resource | Current Exposure | Target Exposure | Status | Notes |
| --- | --- | --- | --- | --- |

## Priority Fixes
- [Critical/High/Medium/Low] [Concrete fix] — Owner: [Bicep/App Code/CI/CD/Azure Portal/Policy]

## Non-IaC Requirements
- [BAA/risk analysis/access review/incident response/training/etc.]
```

For implementation planning, include exact Bicep resources/settings, deployment sequencing, rollback considerations, and verification commands.

## HIPAA Mapping Heuristics

Use `references/control-map.md` for the control matrix. Keep mappings practical:

- Access Control: Entra auth, EasyAuth, RBAC, managed identities, least privilege, app tenant isolation, RLS where applicable.
- Audit Controls: diagnostic settings, data-plane logs, Log Analytics, immutable archive, alerting, retention, evidence collection.
- Integrity: private networking, RBAC boundaries, CMK, deployment immutability, app/schema controls, backup/restore validation.
- Person or Entity Authentication: Entra ID, managed identities, workload identity, no shared admin credentials.
- Transmission Security: HTTPS-only, TLS minimums, private endpoints, private DNS, WAF, no public data-plane endpoints.

## Azure Pattern Library

Load these resources when relevant:

- `references/reference-architecture.md` — our internal target architecture and how Omni Desktop maps to it.
- `references/control-map.md` — HIPAA technical safeguard mapping and non-IaC boundaries.
- `references/bicep-patterns.md` — reusable Azure Bicep patterns and example file index.
- `references/azure-services-checklist.md` — per-service private networking, logging, encryption, and backup checks.
- `references/review-rubric.md` — severity model and review checklist.

Use examples under `examples/` for concrete Bicep snippets. Adapt names and API versions to the target repo rather than copying blindly.

## Bundled Scripts

Use scripts when the user wants repeatable checks or when reviewing a repo with Bicep files:

```bash
python skills/azure-hipaa-infra/scripts/check_bicep_hipaa_controls.py infra/main.bicep
python skills/azure-hipaa-infra/scripts/generate_control_matrix.py findings.json
bash skills/azure-hipaa-infra/scripts/check_public_exposure.sh <resource-group>
bash skills/azure-hipaa-infra/scripts/check_azure_live_controls.sh <resource-group>
```

The static checker is heuristic. Treat findings as prompts for human review, not proof of compliance.

## Guardrails

- Do not say a system is HIPAA compliant solely because infrastructure controls exist.
- Do not recommend public network access for PHI-bearing services unless there is a documented exception and compensating controls.
- Do not recommend storing Azure client secrets, database passwords, or API keys directly in committed files.
- Do not ignore operational controls. Surface BAA, risk analysis, access reviews, incident response, workforce training, backup restore drills, and breach process as non-IaC requirements.
- Do not overfit to Omni Desktop. Use it as a known-good source of patterns while preserving the private-first target standard for new apps.
