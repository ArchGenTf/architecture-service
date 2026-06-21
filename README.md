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
4. **Notifications**: Sends Slack notifications with the results.

#### Build & Deploy (`push`)
1. **Metadata Generation**: Creates a short SHA tag (e.g. `sha-f32a762`).
2. **Docker Build**: Compiles the image using the local `Dockerfile`.
3. **Trivy CVE Scan**: Checks the compiled container image for vulnerabilities.
4. **Registry Push**: Pushes the image to `acrarchgen.azurecr.io/architecture-service` with the short SHA tag and the `latest` tag.
5. **Repository Dispatch**: Fires a `service-image-updated` dispatch event to the `Main` repo to trigger automatic deployment to Dev.
6. **Notifications**: Sends Slack notifications.

---

## Required Secrets Setup & Generation Guide

Add these secrets to your GitHub repository under `Settings` -> `Secrets and variables` -> `Actions` to authorize and run the pipeline:

### 1. `GH_PAT` (GitHub Personal Access Token)
*Required. Needed to check out and push tag updates to the Main repository and trigger dispatches.*
1. Go to your GitHub profile settings: `Settings` -> `Developer settings` -> `Personal access tokens` -> `Tokens (classic)`.
2. Click **Generate new token** -> **Generate new token (classic)**.
3. Set the note (e.g., `gitops-infra-token`) and check the `repo` scope checkbox.
4. Click **Generate token** and copy it immediately.
5. Save this as `GH_PAT` in your service repository secrets.

### 2. `AZURE_CREDENTIALS` (Azure Service Principal)
*Required. Needed to authenticate and push container images to Azure Container Registry (`acrarchgen.azurecr.io`).*
1. Open the Azure CLI or Cloud Shell.
2. Generate a Service Principal JSON payload by running:
   ```bash
   az ad sp create-for-rbac --name "github-actions-sp" --role contributor --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP_NAME> --sdk-auth
   ```
   *(Replace `<SUBSCRIPTION_ID>` and `<RESOURCE_GROUP_NAME>` with your Azure subscription ID and resource group where your ACR resides)*
3. Copy the output JSON block and save it as `AZURE_CREDENTIALS` in your repository secrets.

### 3. `SLACK_WEBHOOK` (Slack Incoming Webhook URL)
*Optional. Needed to send pipeline success/failure alerts to Slack.*
1. Create a Slack App in your workspace via the [Slack API console](https://api.slack.com/apps).
2. Go to **Incoming Webhooks** and toggle it **On**.
3. Click **Add New Webhook to Workspace**, select the target channel, and click **Allow**.
4. Copy the generated Webhook URL (starts with `https://hooks.slack.com/services/`).
5. Save this as `SLACK_WEBHOOK` in your repository secrets.

### 4. SonarQube & Snyk Secrets
*Optional. Configure these to enable static code security analysis and library scanning.*
- `SONAR_TOKEN`: API token generated from SonarCloud (`My Account` -> `Security`).
- `SONAR_URL`: SonarQube host URL (defaults to `https://sonarcloud.io`).
- `SONAR_KEY`: (Optional) Custom Sonar project key (defaults to `ArchGenTf_architecture-service`).
- `SNYK_TOKEN`: Snyk API token generated from Snyk account settings.

---

## Production Release Flow

To deploy a verified image to production:
1. Go to the `Main` (`Infra`) repository on GitHub.
2. Publish a **GitHub Release** with a tag formatted as: `architecture-service-v<version>` (e.g. `architecture-service-v1.0.0`).
3. This triggers the production release workflow, which retags the dev image to `v1.0.0` and updates `k8s/architecture-service/values-prod.yaml` on the `master` branch.
