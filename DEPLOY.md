# Deploying to Google Cloud Run

The app is one stateless container (FastAPI API + the frontend), deployed to
Cloud Run in London (`europe-west2`). It scales to zero when idle.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
export MAPTILER_KEY=...       # optional; terrain + satellite imagery (preferred)
export CESIUM_ION_TOKEN=...   # optional; used if MAPTILER_KEY isn't set
# with neither, the map is flat
.venv/bin/uvicorn backend.app:app --reload
```

## One-time Google Cloud setup

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com secretmanager.googleapis.com
```

Store the Cesium Ion token in Secret Manager and let Cloud Run read it:

```bash
printf %s "YOUR_ION_TOKEN" | gcloud secrets create cesium-ion-token --data-file=-

PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding cesium-ion-token \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role=roles/secretmanager.secretAccessor
```

### MapTiler key (terrain and imagery, preferred over Cesium ion)

1. Create a free account at https://cloud.maptiler.com and copy the default key from
   **Account → API keys** (https://cloud.maptiler.com/account/keys/).
2. Edit the key and add your site under **Allowed HTTP origins**, e.g.
   `paragliding-analysis-544952614531.europe-west2.run.app` (plus `localhost` for local
   development). The key is visible in the browser; this stops other sites using your quota.
3. Store it in Secret Manager and let Cloud Run read it:

```bash
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
    --set-secrets CESIUM_ION_TOKEN=cesium-ion-token:latest,MAPTILER_KEY=maptiler-key:latest \
    --memory 512Mi
```

This builds the `Dockerfile` with Cloud Build, stores the image in Artifact
Registry and prints the service URL. Health check: `GET /health`.

Options worth knowing:
- `--min-instances 1` avoids 1–2 s cold starts after idle periods, at a small monthly cost.
- To update the token later: `printf %s "NEW_TOKEN" | gcloud secrets versions add cesium-ion-token --data-file=-`, then redeploy.
  Same for the MapTiler key with `maptiler-key`.
- Without a MapTiler key, drop `,MAPTILER_KEY=maptiler-key:latest` from `--set-secrets` (a missing secret fails the deploy).

## After the first deploy

- In the Cesium Ion dashboard, restrict the token to your Cloud Run URL / custom domain
  (the token is visible in the browser).
- Custom domain: easiest is Firebase Hosting with a rewrite to the Cloud Run service
  (also gives a CDN for the page).

## Before making it public

- **Map tiles:** the no-token fallback uses `tile.openstreetmap.org`, whose usage policy
  forbids heavy production use. Rely on Ion imagery or switch to a tile provider.
- **Place names:** the Overpass results cache is in memory per instance and is lost when
  Cloud Run scales down. Persist it (Cloud Storage or Firestore) to keep load on the public
  Overpass servers low.
- **Cesium Ion licensing:** the free tier is for personal/non-commercial use; a public or
  commercial app needs a paid plan or self-hosted terrain.
