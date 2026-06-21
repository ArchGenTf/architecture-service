# Architecture Service Microservice

This repository houses the Architecture Service microservice. CI/CD builds, quality checks, and GitOps promotions are handled via the centralized modular pipeline.

---

## CI/CD Pipeline Triggers

The calling workflow [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) triggers on two events:
1. **Pull Request to `master`**: Runs the `pr-checks` job inside the reusable `backend.yml` pipeline.
2. **Merge/Push to `master`**: Runs the `build` job inside the reusable `backend.yml` pipeline.

### Pipeline Stages

#### PR Checks (`pull_request`)
1. **Lint Check**: Checks python code formatting using `flake8`.
2. **SonarQube Scan**: Validates code quality and safety.
3. **Snyk Scan**: Scans python library dependencies for CVEs.
4. **Notifications**: Sends SMTP email and Slack notifications with the results.

#### Build & Deploy (`push`)
1. **Metadata Generation**: Creates a short SHA tag (e.g. `sha-f32a762`).
2. **Docker Build**: Compiles the image using the local `Dockerfile`.
3. **Trivy CVE Scan**: Checks the compiled container image for vulnerabilities.
4. **Registry Push**: Pushes the image to `acrarchgen.azurecr.io/architecture-service` with the short SHA tag and the `latest` tag.
5. **Repository Dispatch**: Fires a `service-image-updated` dispatch event to the `Main` repo to trigger automatic deployment to Dev.
6. **Notifications**: Sends email and Slack notifications.

---

## Required Secrets Setup

Add these secrets to this GitHub repository under `Settings` -> `Secrets and variables` -> `Actions`:

1. **`GH_PAT`**: Personal Access Token (classic) with `repo` scope to modify the `Main` repo and trigger repository dispatch.
2. **`AZURE_CREDENTIALS`**: Service Principal JSON generated via:
   ```bash
   az ad sp create-for-rbac --name "github-actions-sp" --role contributor --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP_NAME> --sdk-auth
   ```
3. **SMTP Email Secrets** (Optional):
   - `SMTP_HOST`: The SMTP server host.
   - `SMTP_PORT`: SMTP server port.
   - `SMTP_USER`: SMTP username / sender email.
   - `SMTP_PASS`: SMTP App Password.
   - `NOTIFY_EMAIL`: Destination email address.
4. **`SLACK_WEBHOOK`** (Optional): Slack Webhook URL for build notifications.
5. **`SONAR_TOKEN`** & **`SNYK_TOKEN`** (Optional): SonarCloud and Snyk API tokens.

---

## Production Release Flow

To deploy a verified image to production:
1. Go to the `Main` (`Infra`) repository on GitHub.
2. Publish a **GitHub Release** with a tag formatted as: `architecture-service-v<version>` (e.g. `architecture-service-v1.0.0`).
3. This triggers the production release workflow, which retags the dev image to `v1.0.0` and updates `k8s/architecture-service/values-prod.yaml` on the `master` branch.
