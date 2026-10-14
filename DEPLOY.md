# Deploying to Google Cloud Run

The app is one stateless container (FastAPI API + the frontend), deployed to
Cloud Run in London (`europe-west2`). It scales to zero when idle.

## Local development

See the quick start in [README.md](README.md): put your key in `.env` and run
`python run.py`.

## One-time Google Cloud setup

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com
```

### MapTiler key (terrain and imagery)

The deployed app uses MapTiler only. Cesium ion's free tier is for personal,
non-commercial use, so keep ion for running locally and don't give it to a public server.

1. Create a free account at https://cloud.maptiler.com and copy the default key from
   **Account → API keys** (https://cloud.maptiler.com/account/keys/).
2. Edit the key and add your site under **Allowed HTTP origins**, e.g.
   `paragliding-analysis-544952614531.europe-west2.run.app` (plus `localhost` for local
   development). The key is visible in the browser; this stops other sites using your quota.
3. Store it in Secret Manager and let Cloud Run read it:

```bash
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')

printf %s "YOUR_MAPTILER_KEY" | gcloud secrets create maptiler-key --data-file=-

gcloud secrets add-iam-policy-binding maptiler-key \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
```

Free plan: 100k requests a month (each terrain/imagery tile is one), personal or
non-commercial use, MapTiler logo and credits shown (the app adds them). Over the limit the
service pauses until next month rather than billing.

## Deploy (and redeploy after changes)

From the project folder:

```bash
gcloud run deploy paragliding-analysis \
    --source . \
    --region europe-west2 \
    --allow-unauthenticated \
    --set-secrets MAPTILER_KEY=maptiler-key:latest \
    --memory 512Mi
```

This builds the `Dockerfile` with Cloud Build, stores the image in Artifact
Registry and prints the service URL. Health check: `GET /health`.

Options worth knowing:
- `--min-instances 1` avoids 1–2 s cold starts after idle periods, at a small monthly cost.
- To update the key later: `printf %s "NEW_KEY" | gcloud secrets versions add maptiler-key --data-file=-`, then redeploy.
- `--set-secrets` replaces the service's whole secret list, so redeploying with this command
  also removes a `CESIUM_ION_TOKEN` left over from an earlier deploy. The old
  `cesium-ion-token` secret can then be deleted: `gcloud secrets delete cesium-ion-token`.

## After the first deploy

- In the MapTiler dashboard, restrict the key to your Cloud Run URL / custom domain
  (the key is visible in the browser).
- Custom domain: easiest is Firebase Hosting with a rewrite to the Cloud Run service
  (also gives a CDN for the page).