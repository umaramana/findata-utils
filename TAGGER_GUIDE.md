# Transaction Tagger — How to Tag a Bank Statement

## Prerequisites

Start the Rasrich Tools app from the project folder:

```
cd C:\Users\UN\fractals\VibeCoding\ClaudeCode
streamlit run app.py
```

Open the browser tab that appears, then navigate to **Transaction Tagger** in the sidebar.

---

## Step 1 — Setup

Fill in the client details:

| Field | What to enter |
|---|---|
| **Client ID** | Short identifier, e.g. `devlin` — used as the lookup filename |
| **Entity Type** | Sole Prop / SMLLC, S-Corp, or Partnership / MMLLC |
| **Primary Business Activity** | e.g. `Interior design and construction` |
| **Secondary Activity** | Optional, e.g. `Rental property` |
| **Confidence Threshold** | Default 75% — Claude flags anything below this for your review |
| **Tagging Mode** | See below |

### Tagging Mode

- **Review-first** — You tag what you know in Step 3, Claude fills the blanks in Step 4.
- **Pre-tag** — Claude tags everything first after Step 2, you review and correct in Step 3.

Pre-tag is better for new clients with no lookup history. Review-first is better when you know most vendors already.

Click **Next →**.

---

## Step 2 — Upload Transactions

1. Upload the bank statement Excel or CSV (typically the Master sheet output from the Tab Collator).
2. If the file has multiple sheets, select the correct one from the dropdown.
3. Map the columns:
   - **Description column** — the transaction narrative column
   - **Amount format** — choose one:
     - *Single column* — expenses are negative numbers (e.g. Chase: `-250.00`)
     - *Two columns* — separate Debit and Credit columns (both positive)
   - **Date column** — optional; enables monthly pivot in the Summary tab
4. Check the 5-row preview to confirm the mapping looks right.
5. If the file has a **Lookup tab** (sheet name containing "lookup"), specific tags load automatically. A green notice confirms this.

Click **Next →**.

In Pre-tag mode, Claude runs here with a progress bar before moving to Step 3.

---

## Step 3 — Preparer Review

### Review-first mode

A table of unique vendors appears — expenses only, deduped.

- **Quick Tag (Specific)** column — your client-specific tags (from Lookup tab) + personal categories
- **Tax Categories (Generic)** column — full 52-tag IRS list

Tag what you recognise. Leave blank to send to Claude. Click **Apply & Refresh** to update the count, then **Next → Claude Tags the Rest** when ready.

### Pre-tag mode

Two sections appear:

- **Pre-tagged vendors** (collapsed expander) — Claude + lookup suggestions with source labels (📋 Lookup / 🤖 Claude). Expand to review and correct any.
- **Needs your attention** — vendors Claude could not tag. Fill these in.

Click **Apply & Refresh** then **Next → Claude Tags the Rest**.

---

## Step 4 — Claude Tags the Rest

A summary shows how many vendors are being sent to Claude Haiku.

Click **Run Claude →**.

Claude processes vendors in batches of 30. A progress bar tracks the calls.

After Claude runs:
- Rows above the confidence threshold are auto-tagged.
- Rows below the threshold are surfaced in a review table showing Claude's suggestion, confidence score, and reason.
- Correct any low-confidence tags in the **Your Tag** and **Your Subcategory** columns.

Click **Apply Tags & Continue**.

---

## Step 5 — Output

Review the summary metrics (auto-tagged / preparer-tagged / personal / review with client).

A **monthly pivot table** shows spend by Tag → Subcategory across months.

Click **Download Tagged File** to save the Excel output.

### Output file tabs

| Tab | Contents |
|---|---|
| **Tagged** | All transactions with Tag, Subcategory, Tag Source, Confidence, Reason |
| **Personal** | Rows tagged "Personal - *" |
| **Review with Client** | Unresolved rows |
| **Summary** | Monthly pivot — Tag/Subcategory rows, month columns, Grand Total |

The lookup table (`stock_processor/lookups/{client_id}_lookup.csv`) is updated automatically. Next time you run this client, known vendors are pre-filled without calling Claude.

---

## Tips

- **Restart the app** (`Ctrl+C` then `streamlit run app.py`) if you change any broker or tagger Python files — Streamlit hot-reload does not re-import modules.
- **Lookup file location**: `stock_processor/lookups/{client_id}_lookup.csv` — never commit this file, it contains client vendor history.
- **Amount format tip**: If your file has a "Subtracted" column and a "Added" column, use Two columns mode and map them to Debit and Credit respectively.
