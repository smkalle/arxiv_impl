# Platform Architecture Overview

## System Components

Our platform is built on a microservices architecture deployed on Kubernetes. The core components are:

### API Gateway
The API gateway (Kong) handles authentication, rate limiting, and request routing. All external traffic enters through the gateway on port 443.

### Auth Service
JWT-based authentication service. Tokens expire after 24 hours. Refresh tokens valid for 30 days. Uses Redis for session storage.

### Search Service
Elasticsearch cluster with 3 nodes. Index aliases enable zero-downtime reindexing. Search queries go through a ranking pipeline that applies BM25 plus ML-based re-ranking.

### Data Pipeline
Apache Kafka for event streaming. Events flow: producers → Kafka → Flink processors → data warehouse (BigQuery). Average latency end-to-end: 8 seconds.

### Storage
- PostgreSQL (primary OLTP): user data, orders, product catalog
- BigQuery (analytics): event data, aggregated metrics
- Redis (cache): sessions, hot product data, rate limit counters
- S3 (object storage): images, documents, model artifacts

## Deployment

All services are containerized with Docker and deployed to GKE. CI/CD via GitHub Actions. Production deployments require two reviewer approvals and passing integration tests.

## Monitoring

- Metrics: Prometheus + Grafana
- Logging: Fluentd → GCS → BigQuery
- Alerting: PagerDuty for P0/P1 incidents
- Tracing: Jaeger for distributed traces

## Network Architecture

Services communicate via gRPC (internal) and REST (external). Service mesh: Istio. All internal traffic is mTLS encrypted.
