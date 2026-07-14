# Deploying report_service (F05-S07)

One-time setup + the deploy command for the Cloud Run bridge. Run these yourself — none of this touches your GCP account without your say-so.

Project (as given 2026-07-06): **insight-fitness-assessments** (number `1006394982571`). If this project doesn't actually exist yet, create it first at https://console.cloud.google.com/projectcreate, then substitute its ID below.

## Prerequisites

- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Billing enabled on the project (Cloud Run has a free tier, but billing must be attached)

```powershell
gcloud config set project insight-fitness-assessments
gcloud services enable run.googleapis.com artifactregistry.googleapis.com sheets.googleapis.com drive.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
```

(If you already ran the old version of this command and hit a "Secret Manager API has not been used" or similar error later, just run the line above again — enabling an already-enabled API is a harmless no-op.)

## 1. Service account (runs the container; does NOT hold Sheets/Drive access)

**Run this from somewhere outside the repo** (e.g. your Downloads folder) — the key file lands in whatever directory you're `cd`'d into, and it must never end up inside a git-tracked folder.

```powershell
gcloud iam service-accounts create insight-report-service `
  --display-name "Insight Report Service"

gcloud iam service-accounts keys create service_account_key.json `
  --iam-account insight-report-service@insight-fitness-assessments.iam.gserviceaccount.com
```

This service account is only Cloud Run's *runtime identity* (needed to read Secret Manager secrets at startup) — it is **not** used for Sheets or Drive. Google blocks service accounts from creating Drive files at all (they have zero storage quota — "Service Accounts do not have storage quota... use OAuth delegation instead" is the literal error you'll hit if you try). Sheets/Drive access instead comes from a real Google account's OAuth token — see step 1b.

This downloads a real credential file, `service_account_key.json`, to your **current local folder**. It's only needed transiently, to prove ownership when creating the service account — delete it once the account exists (`Remove-Item service_account_key.json`); nothing in this deployment reads it later.

### 1b. Mint an OAuth token for Sheets/Drive access

Run once locally — opens a browser for you to log in and consent **as whichever real account should own the uploaded report PDFs** (e.g. `uma.nat.raj@gmail.com`):

```powershell
cd report_service
python mint_oauth_token.py
```

This needs full `drive` scope (not `drive.file`), because the service reads metadata on a file it didn't create (`insight_pilot`, to find its parent folder) — broader than the scope in the existing local `token.json`, so it can't reuse that file and needs its own consent grant. Writes `oauth_token_for_secret.json` locally — temporary, same discipline as the service account key above.

## 2. Store the OAuth token as a Cloud Run secret (not baked into the image)

```powershell
gcloud secrets create report-oauth-token --data-file=oauth_token_for_secret.json
gcloud secrets add-iam-policy-binding report-oauth-token `
  --member "serviceAccount:insight-report-service@insight-fitness-assessments.iam.gserviceaccount.com" `
  --role "roles/secretmanager.secretAccessor"
```

`--data-file=oauth_token_for_secret.json` must point at the actual file from step 1b — either run this from the same folder, or give its full path.

**Now delete the local file** — `Remove-Item oauth_token_for_secret.json` (or full path). Once it's in Secret Manager, the local copy is a live credential sitting around for no reason.

**Windows/PowerShell gotcha — never pipe a secret string directly into `--data-file=-`.** PowerShell's default stdin encoding adds a UTF-8 BOM, which becomes an invisible extra byte in the stored secret — it will look identical in the console but fail every exact-string comparison (this cost a full debugging cycle on 2026-07-06 with `report-shared-secret`). Always write the secret to a plain file first (e.g. via Python `open(...).write(...)`, not PowerShell `Out-File`/piping) and pass that file to `--data-file`.

## 3. Pick a shared secret (Apps Script <-> Cloud Run auth)

Generate one random string in PowerShell (no `openssl` needed):

```powershell
$secret = -join ((48..57 + 97..102) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
$secret
```

Copy what it prints — you'll need it again for Script Properties in step 5, so save it somewhere (password manager, or just keep this PowerShell window open).

`<<<` from the original version of this doc is bash-only syntax and doesn't work in PowerShell — pipe the string into `gcloud` instead:

```powershell
$secret | gcloud secrets create report-shared-secret --data-file=-

gcloud secrets add-iam-policy-binding report-shared-secret `
  --member "serviceAccount:insight-report-service@insight-fitness-assessments.iam.gserviceaccount.com" `
  --role "roles/secretmanager.secretAccessor"
```

Both secrets (`report-service-account-key` from step 2, and this one) need this IAM binding — the runtime service account can't read either one at deploy time otherwise. Grant access to both before running step 4's deploy command.

## 4. Build and deploy

From `insight_core/` (the parent of this `report_service/` folder — the Dockerfile's build context):

```powershell
gcloud builds submit --config report_service/cloudbuild.yaml .
```

`--config` here points at `report_service/cloudbuild.yaml` (a small Cloud Build recipe already in the repo) — **not** the Dockerfile directly. `--tag` and `--config` are mutually exclusive on `gcloud builds submit`, and gcloud's Dockerfile auto-detection only looks in the root of the submitted source (`.` = `insight_core/`), not in `report_service/` where ours actually lives — `cloudbuild.yaml` tells Cloud Build the real path (`docker build -f report_service/Dockerfile ...`) and bakes in the same image tag the deploy step below expects.

```powershell
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
```

Notes:
- `--no-allow-unauthenticated`: the shared-secret header is the app-level check, but Cloud Run's own IAM layer is a second gate — Apps Script's `UrlFetchApp` call will need an identity token if you keep this. **If that turns out to be more friction than value at pilot scale (2 users), switch to `--allow-unauthenticated`** and rely on the shared secret alone — flag that tradeoff before deciding, don't silently pick one.
- `--timeout 180`: a placeholder based on the existing 60s Puppeteer subprocess timeout (`report_pdf.py`) plus Sheets fetch + cold start (~5-15s per the card). **Confirm against real observed render times after the first few live runs** — the F05-S07 card explicitly says not to guess this number; treat 180 as a starting point, not a locked value.
- `--memory 1Gi`: Puppeteer/Chromium is memory-hungry; bump if you see OOM kills in Cloud Run logs.

## 5. Wire Apps Script to the deployed URL

`gcloud run deploy` prints a Service URL, e.g. `https://report-service-xxxxx-uc.a.run.app`. In the Apps Script editor (Extensions > Apps Script from the Sheet) -> Project Settings -> Script Properties, add:

| Property | Value |
|---|---|
| `REPORT_SERVICE_URL` | `https://report-service-xxxxx-uc.a.run.app/generate-report` |
| `REPORT_SHARED_SECRET` | the same random string from step 3 |

No code redeploy needed for this — `Code.gs`'s `generateReport()` reads both from Script Properties at call time.

## 6. Smoke test

```powershell
curl -X POST https://report-service-xxxxx-uc.a.run.app/generate-report `
  -H "X-Report-Secret: PASTE_YOUR_RANDOM_SECRET_HERE" `
  -H "Content-Type: application/json" `
  -d '{"client_id":"champion_mr_abhay_singh","date_from":"2026-06-22","date_to":"2026-06-22","component_ids":["body_measurements","body_vitals"],"layout":"1x1"}'
```

Expect `{"status":"done","output_url":"..."}`. Then confirm the PDF actually landed in "Client Reports" next to `insight_pilot`, shared to Arun's account only (check its Share dialog — should show exactly one person, not "Anyone with the link").
