const express = require('express');
const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const app = express();
const PORT = 3000;

// ── Config ────────────────────────────────────────────────────────────────────
const SHEET_ID       = '1gOS2Icl48Y427XTT1SBGx7_xXenRIzCLuOx01UheHCM';
const SHEET_TAB      = 'Client Details';
const RECEIPTS_TAB   = 'receipts';
// Scope now includes write access for Sheets append
const SCOPES         = ['https://www.googleapis.com/auth/spreadsheets'];

const CREDS_FILE = path.join(__dirname, 'credentials.json');
const TOKEN_FILE = path.join(__dirname, 'token.json');

app.use(express.json());

// ── OAuth helpers ─────────────────────────────────────────────────────────────

function buildOAuthClient() {
  if (!fs.existsSync(CREDS_FILE)) {
    console.error('\n[ERROR] credentials.json not found. See SETUP.md.\n');
    process.exit(1);
  }
  const raw = JSON.parse(fs.readFileSync(CREDS_FILE));
  const c = raw.installed || raw.web;
  return new google.auth.OAuth2(
    c.client_id,
    c.client_secret,
    `http://localhost:${PORT}/auth/callback`
  );
}

function loadToken() {
  if (!fs.existsSync(TOKEN_FILE)) return null;
  return JSON.parse(fs.readFileSync(TOKEN_FILE));
}

function saveToken(tokens) {
  fs.writeFileSync(TOKEN_FILE, JSON.stringify(tokens, null, 2));
}

function getAuthenticatedClient() {
  const token = loadToken();
  if (!token) return null;
  const client = buildOAuthClient();
  client.setCredentials(token);
  client.on('tokens', updated => saveToken({ ...token, ...updated }));
  return client;
}

// ── Sheets helpers ────────────────────────────────────────────────────────────

async function getNextReceiptNo(authClient) {
  const sheets = google.sheets({ version: 'v4', auth: authClient });
  try {
    const res = await sheets.spreadsheets.values.get({
      spreadsheetId: SHEET_ID,
      range: `${RECEIPTS_TAB}!A:A`,
    });
    const rows = res.data.values || [];
    // Find the last RCP-NNN value (skip header row)
    for (let i = rows.length - 1; i >= 1; i--) {
      const match = (rows[i][0] || '').match(/RCP-(\d+)/i);
      if (match) {
        const next = parseInt(match[1]) + 1;
        return `RCP-${String(next).padStart(3, '0')}`;
      }
    }
    return 'RCP-001';
  } catch {
    return 'RCP-001';
  }
}

async function appendReceiptRow(authClient, data) {
  const sheets = google.sheets({ version: 'v4', auth: authClient });
  const { receiptNo, dateIssued, client, month, year, amount, paymentMethod, transactionId, client2, amount2 } = data;

  // Auto-create header row if the tab is empty
  const check = await sheets.spreadsheets.values.get({
    spreadsheetId: SHEET_ID,
    range: `${RECEIPTS_TAB}!A1:H1`,
  });
  const firstRow = ((check.data.values || [[]])[0] || []);
  if (firstRow.length === 0) {
    await sheets.spreadsheets.values.update({
      spreadsheetId: SHEET_ID,
      range: `${RECEIPTS_TAB}!A1:H1`,
      valueInputOption: 'RAW',
      resource: {
        values: [['receipt_no','date_issued','client_id','client_name','month_year','amount','payment_method','transaction_id']],
      },
    });
  }

  const sharedCols = [receiptNo, dateIssued, `${month} ${year}`, paymentMethod, transactionId || ''];
  const rows = [
    [receiptNo, dateIssued, client.client_id || '', client.name || '', `${month} ${year}`, amount, paymentMethod, transactionId || ''],
  ];
  if (client2 && amount2) {
    rows.push([receiptNo, dateIssued, client2.client_id || '', client2.name || '', `${month} ${year}`, amount2, paymentMethod, transactionId || '']);
  }

  await sheets.spreadsheets.values.append({
    spreadsheetId: SHEET_ID,
    range: `${RECEIPTS_TAB}!A:H`,
    valueInputOption: 'USER_ENTERED',
    resource: { values: rows },
  });
}

// ── PDF generation ────────────────────────────────────────────────────────────

function esc(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function escAddr(str) {
  return esc(str).replace(/\n/g, '<br>');
}

function buildReceiptHTML(data) {
  const { client, month, year, amount, paymentMethod, transactionId, receiptNo, dateIssued, client2, amount2 } = data;
  const monthYear  = `${month} ${year}`;
  const totalPaid  = (client2 && amount2) ? Number(amount) + Number(amount2) : Number(amount);
  const totalFmt   = `Rs. ${totalPaid.toLocaleString('en-IN')}/-`;
  const amtFmt1    = `Rs. ${Number(amount).toLocaleString('en-IN')}/-`;
  const amtFmt2    = (client2 && amount2) ? `Rs. ${Number(amount2).toLocaleString('en-IN')}/-` : null;

  // Embed background as base64 so Puppeteer renders it without file-access issues
  const bgBuffer = fs.readFileSync(path.join(__dirname, 'Insight Receipt BG Only.png'));
  const bgBase64 = bgBuffer.toString('base64');
  const bgUrl    = `data:image/png;base64,${bgBase64}`;

  // Scale: A4 at 96 dpi = 794px wide; canvas = 1410px → scale 794/1410 = 0.5631
  const scale = 0.5631;

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;700&family=Raleway:wght@400;700&display=swap" rel="stylesheet">
  <link href="https://fonts.cdnfonts.com/css/cooper-hewitt" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 794px; height: 1123px;
      overflow: hidden;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    .receipt {
      position: relative;
      width: 1410px; height: 2000px;
      background-image: url('${bgUrl}');
      background-size: 100% 100%;
      background-repeat: no-repeat;
      transform: scale(${scale});
      transform-origin: top left;
    }
    .receipt-meta {
      position: absolute; left: 92px; top: 610px;
      font-family: 'Cooper Hewitt', 'Raleway', sans-serif;
      font-size: 22px; font-weight: 400; color: #880e4f; line-height: 1.78;
    }
    .billed-to   { position: absolute; left: 92px;  top: 787px; }
    .payment-summary { position: absolute; right: 92px; top: 787px; }
    .line-items  { position: absolute; left: 245px; top: 1104px; width: 920px; }
    .section-label {
      font-family: 'Poppins', sans-serif; font-weight: 700;
      font-size: 26px; color: #000; margin-bottom: 14px;
    }
    .field-row {
      display: flex; align-items: baseline;
      font-family: 'Poppins', sans-serif; font-size: 20px; color: #000; line-height: 1.45;
    }
    .field-key  { font-weight: 700; min-width: 168px; flex-shrink: 0; }
    .payment-summary .field-key { min-width: 280px; }
    .line-items table { width: 100%; border-collapse: collapse; font-family: 'Poppins', sans-serif; }
    .line-items th {
      font-weight: 700; font-size: 22px; color: #000;
      text-align: left; padding: 22px 28px; border: 2.5px solid #ba9138;
    }
    .line-items td {
      font-weight: 400; font-size: 20px; color: #000;
      text-align: left; padding: 28px 28px; border: 2.5px solid #ba9138;
    }
    .line-items th.amount-col, .line-items td.amount-col { width: 210px; white-space: nowrap; }
  </style>
</head>
<body>
  <div class="receipt">

    <div class="receipt-meta">
      <div>Receipt No.: ${esc(receiptNo)}</div>
      <div>Date: ${esc(dateIssued)}</div>
    </div>

    <div class="billed-to">
      <div class="section-label">Billed To:</div>
      <div class="field-row"><span class="field-key">Name:</span><span>${esc(client.name)}</span></div>
      <div class="field-row"><span class="field-key">Contact:</span><span>${esc(client.phone)}</span></div>
      <div class="field-row"><span class="field-key">Email:</span><span>${esc(client.email)}</span></div>
      <div class="field-row address-row"><span class="field-key">Address:</span><span style="white-space:pre-line">${escAddr(client.address)}</span></div>
    </div>

    <div class="payment-summary">
      <div class="section-label">Payment Summary:</div>
      <div class="field-row"><span class="field-key">Total Paid</span><span>${esc(totalFmt)}</span></div>
      <div class="field-row"><span class="field-key">Payment Method:</span><span>${esc(paymentMethod)}</span></div>
      <div class="field-row"><span class="field-key">Transaction ID</span><span>${esc(transactionId)}</span></div>
    </div>

    <div class="line-items">
      <table>
        <thead><tr><th>Description</th><th class="amount-col">Amount</th></tr></thead>
        <tbody>
          <tr>
            <td>Personal Trainer services for ${esc(client.name)} — ${esc(monthYear)}</td>
            <td class="amount-col">${esc(amtFmt1)}</td>
          </tr>
          ${amtFmt2 ? `<tr>
            <td>Personal Trainer services for ${esc(client2.name)} — ${esc(monthYear)}</td>
            <td class="amount-col">${esc(amtFmt2)}</td>
          </tr>` : ''}
        </tbody>
      </table>
    </div>

  </div>
</body>
</html>`;
}

// ── Routes ────────────────────────────────────────────────────────────────────

app.get('/', (req, res) => res.redirect('/receipt_preview.html'));

app.get('/auth', (req, res) => {
  const client = buildOAuthClient();
  const url = client.generateAuthUrl({ access_type: 'offline', scope: SCOPES, prompt: 'consent' });
  res.redirect(url);
});

app.get('/auth/callback', async (req, res) => {
  const { code, error } = req.query;
  if (error) return res.status(400).send(`OAuth error: ${error}`);
  try {
    const client = buildOAuthClient();
    const { tokens } = await client.getToken(code);
    saveToken(tokens);
    console.log('[auth] Connected. Token saved.');
    res.redirect('/receipt_preview.html');
  } catch (err) {
    res.status(500).send(`Token exchange failed: ${err.message}`);
  }
});

app.get('/api/auth-status', (req, res) => {
  res.json({ authenticated: !!loadToken() });
});

// Next receipt number
app.get('/api/next-receipt-no', async (req, res) => {
  const client = getAuthenticatedClient();
  if (!client) return res.status(401).json({ error: 'not_authenticated' });
  try {
    const no = await getNextReceiptNo(client);
    res.json({ receipt_no: no });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Client search
app.get('/api/clients', async (req, res) => {
  const client = getAuthenticatedClient();
  if (!client) return res.status(401).json({ error: 'not_authenticated' });

  const q = (req.query.q || '').toLowerCase().trim();
  try {
    const sheets = google.sheets({ version: 'v4', auth: client });
    const response = await sheets.spreadsheets.values.get({
      spreadsheetId: SHEET_ID,
      range: `${SHEET_TAB}!A:E`,
    });
    const rows = response.data.values || [];
    if (rows.length < 2) return res.json([]);

    const headers  = rows[0].map(h => h.toLowerCase().trim());
    const clients  = rows.slice(1)
      .filter(row => row.some(c => c?.trim()))
      .map(row => Object.fromEntries(headers.map((h, i) => [h, (row[i] || '').trim()])));

    const result = q ? clients.filter(c => c.name?.toLowerCase().includes(q)) : clients;
    res.json(result);
  } catch (err) {
    if (err.code === 401 || err.status === 401) {
      fs.existsSync(TOKEN_FILE) && fs.unlinkSync(TOKEN_FILE);
      return res.status(401).json({ error: 'token_expired' });
    }
    res.status(500).json({ error: err.message });
  }
});

// Generate PDF + write to Sheets
app.post('/api/generate-receipt', async (req, res) => {
  const authClient = getAuthenticatedClient();
  if (!authClient) return res.status(401).json({ error: 'not_authenticated' });

  const { client, month, year, amount, paymentMethod, transactionId, receiptNo, client2, amount2 } = req.body;

  if (!client?.name || !month || !year || !amount || !paymentMethod || !receiptNo) {
    return res.status(400).json({ error: 'Missing required fields.' });
  }
  if (client2 && !amount2) {
    return res.status(400).json({ error: 'Amount required for second client.' });
  }

  const dateIssued = new Date().toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric'
  }).replace(/ /g, ' ');

  let browser;
  try {
    // 1. Generate PDF via Puppeteer
    const html = buildReceiptHTML({ client, month, year, amount, paymentMethod, transactionId, receiptNo, dateIssued, client2, amount2 });

    browser = await puppeteer.launch({ headless: 'new' });
    const page = await browser.newPage();
    await page.setViewport({ width: 794, height: 1123 });
    await page.setContent(html, { waitUntil: 'networkidle0' });

    const pdfBuffer = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: 0, right: 0, bottom: 0, left: 0 },
    });

    await browser.close();
    browser = null;

    // 2. Append row to receipts tab
    let sheetsWarning = null;
    try {
      await appendReceiptRow(authClient, { receiptNo, dateIssued, client, month, year, amount, paymentMethod, transactionId, client2, amount2 });
      console.log(`[receipt] ${receiptNo} logged to Sheets.`);
    } catch (sheetsErr) {
      sheetsWarning = sheetsErr.message;
      console.error('[sheets write error]', sheetsErr.message);
    }

    // 3. Send PDF (with warning header if Sheets write failed)
    const safeName  = (client.name  || 'Client').replace(/[^a-zA-Z0-9]/g, '_');
    const safeName2 = client2 ? (client2.name || '').replace(/[^a-zA-Z0-9]/g, '_') : null;
    const filename  = safeName2
      ? `Receipt_${safeName}_${safeName2}_${month}${year}.pdf`
      : `Receipt_${safeName}_${month}${year}.pdf`;
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Access-Control-Expose-Headers', 'X-Sheets-Warning');
    if (sheetsWarning) res.setHeader('X-Sheets-Warning', sheetsWarning);
    res.send(Buffer.from(pdfBuffer));

  } catch (err) {
    if (browser) await browser.close().catch(() => {});
    console.error('[pdf error]', err.message);
    res.status(500).json({ error: err.message });
  }
});

// Static files (HTML, PNG, etc.)
app.use(express.static(__dirname));

// ── Start ─────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  const connected = !!loadToken();
  console.log('\n─────────────────────────────────────');
  console.log('  Insight Fitness — Receipt Generator');
  console.log('─────────────────────────────────────');
  console.log(`  http://localhost:${PORT}`);
  if (!connected) {
    console.log(`\n  First run → http://localhost:${PORT}/auth\n`);
  } else {
    console.log('  Google account: connected ✓\n');
    console.log('  NOTE: If Sheets write fails with 403,');
    console.log('  delete token.json and re-auth at /auth\n');
  }
});
