# Architecture Service Microservice

This repository houses the Architecture Service microservice. CI/CD builds, quality gates, and automated GitOps deployments are handled via a centralized reusable pipeline.

---

## CI/CD Pipeline Flow

The workflow defined in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) triggers on pushes or pull requests to the `master`/`main` branches. It calls the reusable workflow in the `Main` repository with the following parameters:
- **Service Name**: `architecture-service`
- **Helm Directory**: `architecture-service`
- **Dev Registry Repository**: `acrarchgen.azurecr.io/architecture-service`
- **Prod Registry Repository**: `acrarchgen.azurecr.io/architecture-service`
- **Local Smoke Test Port**: `8003`
- **Local Smoke Test Endpoint**: `/healthz`
- **Lint Command**: `pip install flake8 && flake8 . --exclude=venv,env,.dist,__pycache__ --ignore=E501`

### Execution Stages:
1. **Lint Check**: Checks python syntax and standards using `flake8`.
2. **SonarQube Cloud Scan**: Analyzes code quality.
3. **Snyk Vulnerability Scan**: Checks python packages for vulnerabilities.
4. **Docker Image Build**: Compiles the image using the local `Dockerfile`.
5. **Local Smoke Test**: Spins up the container on port `8003`, curls `/healthz` to verify startup success, and tears it down.
6. **Trivy Scan**: Checks image CVE vulnerabilities.
7. **Deploy to Dev**: Pushes image to the ACR and updates `values-dev.yaml` on the `dev` branch of the `Main` repo.
8. **Slack Alerts**: Notifies your Slack channel of dev build success or failure.
9. **Production Promotion**: Automatically triggered by creating a GitHub Release / Tag (`v*`). Finds the pre-built image, tags it with the release tag, pushes it to ACR, and updates `values-prod.yaml` on the `master` branch.

---

## Required Secrets Setup

Add these secrets to your GitHub repository under `Settings` -> `Secrets and variables` -> `Actions`:

1. **`PAT_TOKEN`**: Personal Access Token (classic) with `repo` scope to modify the `Main` repo.
2. **`AZURE_CREDENTIALS`**: Service Principal JSON generated via:
   ```bash
   az ad sp create-for-rbac --name "github-actions-sp" --role contributor --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP_NAME> --sdk-auth
   ```
3. **`SLACK_WEBHOOK`**: Slack Incoming Webhook URL.
4. **`SONAR_TOKEN`**: (Optional) SonarCloud token.
5. **`SNYK_TOKEN`**: (Optional) Snyk API Token.

---

## Production Promotion & GitOps Release Flow

This pipeline uses an automated, Git-driven release flow rather than manual environments:
1. **Develop Deployment**: Merges to the `master` branch automatically deploy code changes to the Dev cluster (updating `values-dev.yaml` on the `dev` branch of the `Main` repo with the commit SHA tag).
2. **Production Release**: When ready for a production release, create and publish a GitHub Release with a tag matching `v*` (e.g. `v1.0.0`) in this repository.
3. The promotion pipeline will automatically find the pre-built image corresponding to that commit SHA, tag it with the release tag (e.g., `v1.0.0`), and push the new tag. It will then update `values-prod.yaml` on the `master` branch of the `Main` repository with the release tag.
