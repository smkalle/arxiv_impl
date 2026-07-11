# Deployment Runbook

## Pre-deployment Checklist

Before every production deployment:
- [ ] All CI checks passing (GitHub Actions green)
- [ ] PR reviewed and approved by 2+ engineers
- [ ] Database migrations reviewed by DBA
- [ ] Feature flags set correctly
- [ ] Rollback plan documented in PR

## Deployment Steps

### Step 1: Prepare the release
```bash
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

### Step 2: Deploy to staging
The GitHub Actions workflow auto-deploys tagged commits to staging. Monitor the #deployments Slack channel for status.

### Step 3: Run smoke tests
```bash
./scripts/smoke_test.sh --env staging
```
All tests must pass before proceeding.

### Step 4: Deploy to production
Use the deploy-prod GitHub Actions workflow. Requires admin approval in the GitHub UI.

Deployment takes 5–8 minutes. Zero-downtime via rolling update strategy.

### Step 5: Verify
- Check Grafana dashboard for error rate spike (should stay < 0.1%)
- Check p99 latency (should stay < 500ms)
- Verify key user journeys in production

## Rollback Procedure

If error rate exceeds 1% within 10 minutes of deployment:
```bash
# Roll back to previous deployment
kubectl rollout undo deployment/api-server -n production
```

Alert the on-call engineer and create a P1 incident ticket.

## Database Migrations

Migrations run automatically during deployment. For breaking changes (column drops, renames), use a 3-phase migration:
1. Deploy backward-compatible migration
2. Deploy code using new schema
3. Deploy cleanup migration (remove old column)
