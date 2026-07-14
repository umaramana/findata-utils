# F05-S07 — run this file directly instead of pasting the deploy command inline
# (long single-line pastes were getting silently truncated in the terminal,
# dropping flags one at a time — service name, then region, then --image).
#
# Usage:
#   cd path\to\insight_core\report_service
#   .\deploy_report_service.ps1

gcloud run deploy report-service `
  --image gcr.io/insight-fitness-assessments/report-service `
  --platform managed `
  --region us-central1 `
  --service-account insight-report-service@insight-fitness-assessments.iam.gserviceaccount.com `
  --no-allow-unauthenticated `
  --timeout 180 `
  --memory 1Gi `
  --set-secrets "/secrets/oauth_token.json=report-oauth-token:latest,REPORT_SHARED_SECRET=report-shared-secret:latest" `
  --set-env-vars "REPORT_OAUTH_TOKEN_PATH=/secrets/oauth_token.json"
