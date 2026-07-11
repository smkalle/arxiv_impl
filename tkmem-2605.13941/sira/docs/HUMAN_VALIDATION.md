# Human Validation Steps

Run from `sira/`.

Fast path:

```bash
scripts/manage.sh build
scripts/manage.sh eval
scripts/manage.sh start
scripts/manage.sh smoke
scripts/manage.sh stop
```

1. Build/enrich/index:

```bash
python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl
python3 src/evaluate.py --test-set data/annotated_test_set.jsonl --index data/bm25_index.pkl --report data/eval_report.json
```

2. Validate CLI retrieval:

```bash
python3 scripts/query.py --evolved "My app keeps crashing on login"
python3 scripts/query.py --evolved "subscription keeps renewing" --tau 0.01 --weight 1.5
```

3. Start API and dashboard:

```bash
python3 -m uvicorn src.ticket_api:app --host 127.0.0.1 --port 8001
python3 -m uvicorn src.enrich_ui:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`, submit a query, then inspect `/kb`, `/evolution`, and `/system`.

4. Check service artifacts:

```bash
python3 scripts/ops_status.py
ls ops/systemd/
```
