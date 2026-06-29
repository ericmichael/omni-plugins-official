#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

CHECKS = [
    ("https_only", "HTTPS-only app ingress", r"httpsOnly\s*:\s*true", "High"),
    ("public_network_disabled", "Public network access disabled somewhere", r"publicNetworkAccess\s*:\s*'Disabled'", "High"),
    ("private_endpoint", "Private endpoint resources", r"Microsoft\.Network/privateEndpoints", "High"),
    ("private_dns", "Private DNS zones", r"Microsoft\.Network/privateDnsZones", "Medium"),
    ("key_vault", "Key Vault present", r"Microsoft\.KeyVault/vaults", "High"),
    ("purge_protection", "Key Vault purge protection", r"enablePurgeProtection\s*:\s*true", "High"),
    ("managed_identity", "User-assigned managed identity", r"Microsoft\.ManagedIdentity/userAssignedIdentities", "High"),
    ("diagnostics", "Diagnostic settings", r"Microsoft\.Insights/diagnosticSettings", "High"),
    ("cmk", "Customer-managed key pattern", r"keySource\s*:\s*'Microsoft\.Keyvault'|dataEncryption\s*:\s*{", "Medium"),
    ("postgres_private", "Postgres private networking", r"delegatedSubnetResourceId|privateDnsZoneArmResourceId", "High"),
    ("storage_no_public_blob", "Blob public access disabled", r"allowBlobPublicAccess\s*:\s*false", "High"),
    ("waf", "WAF/front door pattern", r"frontDoorWebApplicationFirewallPolicies|ApplicationGateway.*WAF|Premium_AzureFrontDoor", "Medium"),
    ("defender", "Defender for Cloud pricing", r"Microsoft\.Security/pricings", "Medium"),
    ("immutability", "Immutable audit archive pattern", r"immutabilityPolicies|immutableStorageWithVersioning", "Medium"),
]

PUBLIC_PATTERNS = [
    ("public_network_enabled", r"publicNetworkAccess\s*:\s*'Enabled'"),
    ("allow_all_network", r"defaultAction\s*:\s*'Allow'"),
    ("public_ip", r"Microsoft\.Network/publicIPAddresses"),
]


def scan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    findings = []
    for key, label, pattern, severity in CHECKS:
        matched = bool(re.search(pattern, text, re.IGNORECASE | re.DOTALL))
        findings.append({
            "id": key,
            "label": label,
            "severity": severity,
            "passed": matched,
            "evidence": "pattern found" if matched else "pattern not found",
            "owner": "Bicep",
        })
    exposure = []
    for key, pattern in PUBLIC_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            line = text.count("\n", 0, match.start()) + 1
            exposure.append({"id": key, "line": line, "evidence": match.group(0)})
    return {"file": str(path), "findings": findings, "public_exposure_signals": exposure}


def main() -> int:
    parser = argparse.ArgumentParser(description="Heuristically scan Azure Bicep for HIPAA-aligned infrastructure controls.")
    parser.add_argument("files", nargs="+", help="Bicep files to scan")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    results = [scan(Path(file)) for file in args.files]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for result in results:
        print(f"# {result['file']}")
        for finding in result["findings"]:
            status = "PASS" if finding["passed"] else "REVIEW"
            print(f"{status:6} {finding['severity']:6} {finding['label']}")
        if result["public_exposure_signals"]:
            print("Public exposure signals:")
            for signal in result["public_exposure_signals"]:
                print(f"  line {signal['line']}: {signal['id']} ({signal['evidence']})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
