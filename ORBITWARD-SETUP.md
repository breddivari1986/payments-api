# Payments governed delivery

CI runs on GitHub-hosted runners. It checks out the assessed source SHA, executes the Docker
`test` target without network access, scans source/configuration and the release image, then
publishes the tested image to the dedicated Google Artifact Registry repository by digest.
The publisher uses GitHub OIDC federation, restricted to this repository's main CI workflow;
no GCP service-account key is used by these workflows.

Orbitward starts CI using the Payments-only GitHub App, collects `release.json`, and waits for
an authorized person other than the requester to approve the exact image and target. After that
approval the platform dispatches CD on `orbitward-payments-cd`. This runner can patch only
`payment/payments-api` on `gke-private-prod`. The CD helper verifies the image, rollout and HTTPS
health, then uploads `verification.json`. Recovery uses the same target and an approved previous
digest; it never rolls back application data.

The legacy push deployment has been archived under `.orbitward/legacy/` and is not an active
workflow. These new workflows are manual-dispatch only; source pushes do not deploy automatically.
Review and repin the platform's workflow SHA whenever the delivery ref changes. Do not dispatch
CD by hand or enable untrusted PR jobs on the private runner. Operators with repository write or
Actions dispatch permissions remain trusted; the workflow does not independently contact Orbitward
to validate an approval token.

The workload is a demonstration API with in-memory storage, not a real payment processor.
