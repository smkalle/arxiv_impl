# Security Policy

## Access Control

All production access requires VPN connection and MFA. Access is granted on a least-privilege basis.

Role definitions:
- **Read-only**: View dashboards, logs, and non-sensitive configs
- **Operator**: Deploy to staging, restart services, view production logs
- **Admin**: Full production access, secret management, IAM changes

Access requests must be approved by your manager and the security team via the AccessBot Slack workflow.

## Secret Management

Never commit secrets to version control. All secrets are stored in HashiCorp Vault.

Accessing secrets in code:
```python
import hvac
client = hvac.Client(url='https://vault.internal')
secret = client.secrets.kv.v2.read_secret_version(path='services/myapp')
```

Rotate secrets every 90 days. Automated rotation is enabled for database credentials.

## Incident Response

Security incidents are classified P0–P3:
- **P0**: Active breach, data exfiltration suspected — page security lead immediately
- **P1**: Unauthorized access detected — respond within 1 hour
- **P2**: Vulnerability discovered — remediate within 7 days
- **P3**: Security improvement — schedule in next sprint

Report incidents in #security-incidents. Do not discuss in public channels.

## Data Classification

- **Restricted**: PII, payment data, credentials — encrypt at rest and in transit
- **Confidential**: Internal roadmaps, financial data — internal access only
- **Internal**: Engineering docs, architecture diagrams — all employees
- **Public**: Marketing content, open-source code

## Vulnerability Management

Run `npm audit` and `safety check` in CI. CVSS score ≥ 7.0 blocks deployment. Dependency updates via Dependabot PRs reviewed weekly.
