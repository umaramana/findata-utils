# Insight Fitness — Receipt Generator Setup

## Step 1 — Install Node.js dependencies

Open a terminal in this folder and run:

```
npm install
```

---

## Step 2 — Create a Google Cloud project

1. Go to https://console.cloud.google.com
2. Click **Select a project → New Project**
3. Name it `insight-receipt` (or anything) → **Create**

---

## Step 3 — Enable the Google Sheets API

1. In your new project, go to **APIs & Services → Library**
2. Search for **Google Sheets API** → click it → **Enable**

---

## Step 4 — Create OAuth 2.0 credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If prompted to configure the consent screen:
   - User Type: **External** → Create
   - App name: `Insight Receipt Generator`
   - User support email: your Gmail
   - Developer contact: your Gmail
   - Save and continue through the remaining screens (no scopes needed here)
   - Under **Test users** → add your Gmail address → Save
4. Back on Credentials → **+ Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Name: `Insight Receipt Desktop`
   - **Create**
5. Click **Download JSON** → save the file as `credentials.json` in this folder

---

## Step 5 — Share your Google Sheet with the OAuth app

No sharing needed — OAuth logs in as your own Google account, so the Sheet only needs to be accessible to you.

---

## Step 6 — Verify the tab name in server.js

Open `server.js` and confirm this constant matches your exact Sheet tab name:

```js
const SHEET_TAB = 'client directory';
```

The tab name is case-sensitive and must include any spaces exactly as they appear in the Sheet.

---

## Step 7 — Run the server

```
node server.js
```

**First run only:** open http://localhost:3000/auth in your browser.
Google will ask you to sign in and grant permission. After approval you'll be
redirected back to the receipt generator automatically.

Subsequent runs: `node server.js` → open http://localhost:3000 — no login needed.

---

## Files NOT to commit to git

Add these to `.gitignore`:

```
credentials.json
token.json
node_modules/
```

`credentials.json` contains your OAuth client secret.
`token.json` contains your live access token.
Neither should ever be committed.

---

## Troubleshooting — "Google not connected or sign-in expired"

While the OAuth consent screen is in **Testing** mode, Google expires the saved
sign-in roughly every 7 days. When that happens the page shows the
"Google not connected or sign-in expired. Sign in →" banner (the server has
already removed the stale `token.json`). Click **Sign in →** — or open
http://localhost:3000/auth — in **Chrome** (Arc blocks the redirect). No restart needed.

To stop the weekly expiry: Google Cloud Console → APIs & Services → OAuth consent
screen → **Publish app**.

If client search says "Couldn't load clients — check the server window", the
error is printed in the terminal running `node server.js` (e.g. a renamed
`Client Details` tab). "No clients found" only ever means no name matched.
