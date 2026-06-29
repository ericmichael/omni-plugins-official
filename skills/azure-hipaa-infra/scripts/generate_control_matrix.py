#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

CONTROL_BY_FINDING = {
    "https_only": "Transmission Security",
    "public_network_disabled": "Transmission Security",
    "private_endpoint": "Transmission Security",
    "private_dns": "Transmission Security",
    "key_vault": "Access Control",
    "purge_protection": "Integrity",
    "managed_identity": "Person or Entity Authentication",
    "diagnostics": "Audit Controls",
    "cmk": "Encryption/Decryption",
    "postgres_private": "Transmission Security",
    "storage_no_public_blob": "Access Control",
    "waf": "Transmission Security",
    "defender": "Audit Controls",
    "immutability": "Audit Controls",
}

RECOMMENDATIONS = {
    "https_only": "Set App Service `httpsOnly: true` and redirect HTTP at any edge layer.",
    "public_network_disabled": "Disable public network access on PHI-bearing services where Azure supports it.",
    "private_endpoint": "Add private endpoints and private DNS zones for data-plane services.",
    "private_dns": "Link required private DNS zones to VNets that host app runtimes.",
    "key_vault": "Store secrets and CMKs in RBAC-enabled Key Vault.",
    "purge_protection": "Enable Key Vault soft delete and purge protection.",
    "managed_identity": "Use user-assigned managed identities for Azure resource access.",
    "diagnostics": "Add diagnostic settings for resources and data-plane services.",
    "cmk": "Use customer-managed keys for durable PHI stores where supported.",
    "postgres_private": "Deploy PostgreSQL Flexible Server with private networking and private DNS.",
    "storage_no_public_blob": "Disable anonymous blob access and public network access for storage accounts.",
    "waf": "Add Front Door or Application Gateway WAF for public ingress exceptions.",
    "defender": "Enable Defender for Cloud plans relevant to the workload.",
    "immutability": "Archive audit logs to immutable Blob Storage with retention policy.",
}


def load_findings(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [data]
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Markdown HIPAA control matrix from static checker JSON.")
    parser.add_argument("findings_json", help="JSON emitted by check_bicep_hipaa_controls.py --json")
    args = parser.parse_args()

    documents = load_findings(Path(args.findings_json))
    rows = []
    for document in documents:
        source = document.get("file", "unknown")
        for finding in document.get("findings", []):
            if finding.get("passed"):
                gap = "None identified by static heuristic"
                risk = "Low"
            else:
                gap = f"Missing or not detected: {finding['label']}"
                risk = finding.get("severity", "Medium")
            rows.append({
                "control": CONTROL_BY_FINDING.get(finding.get("id"), "General Safeguard"),
                "evidence": f"{source}: {finding.get('evidence', '')}",
                "gap": gap,
                "risk": risk,
                "owner": finding.get("owner", "Bicep"),
                "recommendation": RECOMMENDATIONS.get(finding.get("id"), "Review and remediate as appropriate."),
                "verification": "Re-run static checker and verify deployed state with Azure CLI.",
            })

    print("| Control Area | Azure Evidence | Gap | Risk | Owner | Recommendation | Verification |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print("| {control} | {evidence} | {gap} | {risk} | {owner} | {recommendation} | {verification} |".format(**row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
