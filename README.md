# payments-api

A small payments API: create a payment with an idempotency key, read it back, answer health and metrics. Standard library only; no card data is ever accepted at this layer.

- `POST /payments` with `{"idempotency_key", "customer_id", "amount_minor", "currency"}` → `201` and the payment; the same key again → `200` and the same payment.
- `GET /payments/{id}`, `GET /healthz`, `GET /readyz`, `GET /metrics`.

## Delivery

Every push to `main` runs `.github/workflows/deploy.yaml`: unit tests, a Trivy scan gated on fixable criticals, a source tarball to Artifact Registry, a Docker build pushed to Artifact Registry, an image scan, then a deploy from a runner inside the GKE cluster and a wait for the rollout. The pipeline is the same shape as the `oopsapi` service's and is mirrored by Orbitward's "Payments API delivery" template.

Local run: `python3 app.py`, then `curl -X POST localhost:8080/payments -d '{"idempotency_key":"order-1001-a","customer_id":"c_1","amount_minor":1999,"currency":"USD"}'`.
