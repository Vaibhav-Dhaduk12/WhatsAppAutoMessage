# WhatsApp Auto Message Scheduler 📲

A **serverless, 24/7 WhatsApp message scheduler** that runs entirely on free cloud infrastructure — no laptop required.

| Component | Technology | Cost |
|---|---|---|
| Frontend form | GitHub Pages (HTML/CSS/JS) | Free |
| Database / queue | Google Sheets | Free |
| Automation engine | GitHub Actions (cron) | Free |
| WhatsApp gateway | Twilio API | Free (trial) |

---

## 🏗️ Architecture

```
Browser (GitHub Pages)
       │  POST JSON
       ▼
Google Apps Script Web App
       │  appendRow()
       ▼
Google Sheets  ◄──────────────────────┐
(Phone | Message | Time | Status)      │ update_cell("Sent")
                                       │
              GitHub Actions (every 10 min)
                       │
                  main.py runs
                       │  Twilio API
                       ▼
               WhatsApp message delivered ✅
```

---

## 🚀 Setup Guide

Follow these four steps to get everything running.

---

### Step 1 — Google Sheet (Database)

1. Go to [sheets.google.com](https://sheets.google.com) and create a new spreadsheet.
2. Rename the first sheet tab to **`Messages`**.
3. The script will auto-create headers on first run, but you can add them manually:

   | A | B | C | D |
   |---|---|---|---|
   | Phone Number | Message | Scheduled Time | Status |

4. Note the **Spreadsheet ID** from the URL:
   `https://docs.google.com/spreadsheets/d/`**`<SPREADSHEET_ID>`**`/edit`

---

### Step 2 — Google Apps Script (Form → Sheet)

This script receives form submissions from the GitHub Pages site and appends them to your sheet.

1. Open [script.google.com](https://script.google.com) → **New project**.
2. Delete any existing code, then paste the contents of [`apps_script/Code.gs`](apps_script/Code.gs).
3. Replace `REPLACE_WITH_YOUR_SPREADSHEET_ID` with your actual Spreadsheet ID.
4. **Deploy → New deployment**:
   - Type: **Web app**
   - Execute as: **Me**
   - Who has access: **Anyone**
5. Copy the **Web App URL** — you'll need it in Step 3.

---

### Step 3 — Frontend (GitHub Pages)

1. Open [`docs/index.html`](docs/index.html).
2. Find this line near the bottom of the `<script>` block:
   ```js
   const GOOGLE_SCRIPT_URL = "REPLACE_WITH_YOUR_GOOGLE_APPS_SCRIPT_URL";
   ```
3. Replace the placeholder with the Web App URL from Step 2.
4. Commit and push.
5. In your repo, go to **Settings → Pages**, set Source to **Deploy from a branch**, Branch: **main**, Folder: **`/docs`**.
6. Your form will be live at `https://<your-username>.github.io/WhatsAppAutoMessage/`.

---

### Step 4 — Google Service Account (Python → Sheets)

The Python script (`main.py`) needs its own credentials to read/write the sheet.

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Create a new project (or reuse an existing one).
3. Enable the **Google Sheets API** and **Google Drive API**.
4. Go to **IAM & Admin → Service Accounts → Create Service Account**.
5. Download the JSON key file.
6. **Share** your Google Sheet with the service account's email address (give it **Editor** access).

---

### Step 5 — Twilio (WhatsApp Gateway)

1. Sign up at [twilio.com](https://www.twilio.com) (free trial available).
2. Go to **Messaging → Try it out → Send a WhatsApp message**.
3. Follow the sandbox activation instructions (send the join code from your phone).
4. Note your:
   - **Account SID** (starts with `AC…`)
   - **Auth Token**
   - **WhatsApp sandbox number** (e.g. `whatsapp:+14155238886`)

---

### Step 6 — GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_WHATSAPP_NUMBER` | e.g. `whatsapp:+14155238886` |
| `GOOGLE_CREDENTIALS_JSON` | The entire contents of the service-account JSON key file |
| `SPREADSHEET_ID` | Your Google Sheet ID |

---

## ⚙️ How It Works (at runtime)

1. Every **10 minutes**, GitHub Actions runs `main.py`.
2. The script reads all rows where **Status = "Pending"**.
3. For each pending row where **Scheduled Time ≤ now (UTC)**, it:
   - Sends the WhatsApp message via Twilio.
   - Updates the row's Status to **"Sent"** (or **"Failed"** on error).
4. All activity is logged to the GitHub Actions run log.

You can also trigger the workflow manually at any time from **Actions → WhatsApp Message Scheduler → Run workflow**.

---

## 📁 Project Structure

```
WhatsAppAutoMessage/
├── docs/
│   └── index.html          # Frontend form (GitHub Pages)
├── apps_script/
│   └── Code.gs             # Google Apps Script (form → sheet)
├── .github/
│   └── workflows/
│       └── scheduler.yml   # GitHub Actions cron workflow
├── main.py                 # Python scheduler (reads sheet, sends via Twilio)
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🧪 Local Testing

> **Python ≥ 3.10** is required (uses the `X | Y` union type syntax). The GitHub Actions workflow uses Python 3.12.

```bash
# Install dependencies
pip install -r requirements.txt

# Export secrets as environment variables
export TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxx"
export TWILIO_AUTH_TOKEN="your_auth_token"
export TWILIO_WHATSAPP_NUMBER="whatsapp:+14155238886"
export GOOGLE_CREDENTIALS_JSON="$(cat service_account.json)"
export SPREADSHEET_ID="your_spreadsheet_id"

# Run
python main.py
```

---

## ⚠️ Notes & Limitations

- **Twilio Sandbox**: The free sandbox requires recipients to first send a join code. For production use, apply for a Twilio WhatsApp Business number.
- **Scheduling precision**: The cron runs every 10 minutes, so messages may be delivered up to 10 minutes late.
- **Timezone**: Scheduled times entered in the form are stored as-is. `main.py` treats times without a timezone as UTC. Make sure your inputs match.
- **GitHub Actions free tier**: Public repos get unlimited free Actions minutes. Private repos have a monthly limit.

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss larger changes.

---

## 📄 License

MIT