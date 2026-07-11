# Data Engineering Guide

## Data Warehouse Overview

We use BigQuery as our primary analytical data warehouse. Data flows in from three sources:
1. PostgreSQL (operational data via CDC with Debezium)
2. Kafka events (user behavior, clickstream)
3. Third-party APIs (Salesforce, Stripe, Mixpanel)

## Table Conventions

All tables follow these naming conventions:
- `raw_*`: Unprocessed source data, never modified
- `stg_*`: Cleaned and typed staging tables
- `fct_*`: Fact tables (transactional data)
- `dim_*`: Dimension tables (entities)
- `rpt_*`: Reporting-ready aggregations

## dbt Usage

We use dbt for all transformations. Never write raw SQL directly in BigQuery.

```bash
# Run all models
dbt run

# Run specific model and dependencies
dbt run --select +my_model+

# Run tests
dbt test

# Generate documentation
dbt docs generate && dbt docs serve
```

## Data Quality

Every model has tests defined in `schema.yml`:
- `not_null` on primary keys
- `unique` on primary keys
- `accepted_values` on status fields
- Custom `row_count` tests for critical tables

Data quality failures in production trigger PagerDuty alerts.

## Accessing Data

Use Looker for ad-hoc analysis and dashboards. For Python access:

```python
from google.cloud import bigquery

client = bigquery.Client(project="company-data")
query = """
    SELECT user_id, COUNT(*) as events
    FROM `company-data.prod.fct_events`
    WHERE date >= '2026-01-01'
    GROUP BY user_id
"""
df = client.query(query).to_dataframe()
```

## Incident Runbook for Data Pipelines

- **Pipeline delayed > 2 hours**: Check Airflow DAG status, Kafka consumer lag
- **Data quality test failure**: Check dbt logs, quarantine table, alert data-on-call
- **BigQuery cost spike**: Check INFORMATION_SCHEMA.JOBS for expensive queries, add LIMIT or partition pruning
