# Architecture Service Microservice

This repository houses the Architecture Service microservice. CI/CD builds, quality gates, and automated GitOps deployments are handled via a centralized reusable pipeline.

---

## CI/CD Pipeline Flow

The workflow defined in [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) triggers on pushes or pull requests to the `master`/`main` branches. It calls the reusable workflow in the `Main` repository with the following parameters:
- **Service Name**: `architecture-service`
- **Helm Directory**: `architecture-service`
- **Dev Registry Repository**: `acrarchgendev.azurecr.io/architecture-service`
- **Prod Registry Repository**: `acrarchgenprod.azurecr.io/architecture-service`
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
7. **Deploy to Dev**: Pushes image to Dev ACR and updates `values-dev.yaml` on the `dev` branch of the `Main` repo.
8. **Slack Alerts**: Notifies your Slack channel of dev build success or failure.
9. **Production Promotion (Approval-Gated)**: Pauses for manual approval under the `production` environment. Upon approval, pushes image to Prod ACR and updates `values-prod.yaml` on the `master` branch.

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

## Setup Manual Approval Environment

1. Navigate to your GitHub repository: `Settings` -> `Environments`.
2. Click **New environment** and name it exactly: `production`.
3. Check **Required reviewers** and assign authorized reviewers.
