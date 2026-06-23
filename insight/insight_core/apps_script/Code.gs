// Insight Core — Check-in Form (S1.2)
// Bound script for insight_pilot spreadsheet.
//
// Deploy:
//   1. Open insight_pilot in Google Sheets
//   2. Extensions → Apps Script
//   3. Paste this file as Code.gs and index.html as a separate HTML file named "index"
//   4. Deploy → New deployment → Web app
//      Execute as: Me (uma.nat.raj@gmail.com)
//      Who has access: Anyone with the link
//   5. Copy the deployment URL and save it (this is Arun's check-in link)

var SS = SpreadsheetApp.getActiveSpreadsheet();
var CLIENT_TAB  = "client_info";
var READINGS_TAB = "readings";
var TZ = "Asia/Kolkata";

// Readings column layout (1-based for getRange, 0-based for getValues index):
// A=client_id, B=date, C=component, D=metric, E=value, F=unit, G=source, H=notes, I=recorded_at
var COL = { CLIENT_ID: 1, DATE: 2, COMPONENT: 3, METRIC: 4, VALUE: 5, UNIT: 6, SOURCE: 7, NOTES: 8, RECORDED_AT: 9 };
var IDX = { CLIENT_ID: 0, DATE: 1, COMPONENT: 2, METRIC: 3, VALUE: 4, UNIT: 5, SOURCE: 6, NOTES: 7, RECORDED_AT: 8 };

function doGet() {
  return HtmlService.createHtmlOutputFromFile("index")
    .setTitle("Insight Check-In")
    .addMetaTag("viewport", "width=device-width, initial-scale=1.0, maximum-scale=1.0");
}

// Normalises a sheet cell value (Date object or string) to "YYYY-MM-DD".
function _dateStr(d) {
  if (d instanceof Date) {
    return Utilities.formatDate(d, TZ, "yyyy-MM-dd");
  }
  return String(d).trim();
}

// Returns [{id, name}] from client_info, sorted by name.
function getClients() {
  var sheet = SS.getSheetByName(CLIENT_TAB);
  var data = sheet.getDataRange().getValues();
  if (data.length <= 1) return [];
  return data.slice(1)
    .filter(function(r) { return r[0] && r[1]; })
    .map(function(r) { return { id: String(r[0]), name: String(r[1]) }; })
    .sort(function(a, b) { return a.name.localeCompare(b.name); });
}

// Returns existing body_vitals readings for a client+date as {metric_id: value}.
// Used by the form to pre-fill inputs.
function getReadings(clientId, date) {
  var sheet = SS.getSheetByName(READINGS_TAB);
  var data = sheet.getDataRange().getValues();
  var result = {};
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][IDX.CLIENT_ID]) === clientId &&
        _dateStr(data[i][IDX.DATE])    === date &&
        String(data[i][IDX.COMPONENT]) === "body_vitals") {
      result[String(data[i][IDX.METRIC])] = data[i][IDX.VALUE];
    }
  }
  return result;
}

// Creates a new client row in client_info. Returns {id, name}.
function addClient(data) {
  var sheet = SS.getSheetByName(CLIENT_TAB);
  var existing = sheet.getDataRange().getValues().slice(1).map(function(r) { return String(r[0]); });

  var base = data.full_name.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  var client_id = base;
  var suffix = 1;
  while (existing.indexOf(client_id) !== -1) {
    client_id = base + "_" + suffix++;
  }

  sheet.appendRow([
    client_id,
    data.full_name,
    data.gender,
    data.dob,
    data.height_cm ? Number(data.height_cm) : "",
    "adult",
    "TRUE"
  ]);

  return { id: client_id, name: data.full_name };
}

// Upserts/deletes reading rows for a given client + date.
// Has value + existing row  → update value + recorded_at
// Has value + no row        → append
// Empty    + existing row   → delete row
// Empty    + no row         → skip
// Returns {name, date} for confirmation.
function submitReadings(data) {
  var sheet = SS.getSheetByName(READINGS_TAB);
  var existing = sheet.getDataRange().getValues();
  var now = Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd HH:mm:ss");

  var metrics = [
    { metric: "weight_kg",  unit: "kg", value: data.weight_kg },
    { metric: "fat_pct",    unit: "%",  value: data.fat_pct },
    { metric: "muscle_pct", unit: "%",  value: data.muscle_pct }
  ];

  var rowsToDelete = [];

  metrics.forEach(function(m) {
    var hasValue = m.value !== "" && m.value !== null && m.value !== undefined;

    var existingRow = -1;
    for (var i = 1; i < existing.length; i++) {
      if (String(existing[i][IDX.CLIENT_ID]) === data.client_id &&
          _dateStr(existing[i][IDX.DATE])    === data.date &&
          String(existing[i][IDX.COMPONENT]) === "body_vitals" &&
          String(existing[i][IDX.METRIC])    === m.metric) {
        existingRow = i + 1;
        break;
      }
    }

    if (hasValue) {
      if (existingRow !== -1) {
        sheet.getRange(existingRow, COL.VALUE).setValue(Number(m.value));
        sheet.getRange(existingRow, COL.RECORDED_AT).setValue(now);
      } else {
        sheet.appendRow([data.client_id, data.date, "body_vitals", m.metric, Number(m.value), m.unit, "form", "", now]);
      }
    } else if (existingRow !== -1) {
      rowsToDelete.push(existingRow);
    }
  });

  // Delete bottom-to-top to avoid index shift between deletions
  rowsToDelete.sort(function(a, b) { return b - a; });
  rowsToDelete.forEach(function(r) { sheet.deleteRow(r); });

  var clientSheet = SS.getSheetByName(CLIENT_TAB);
  var clients = clientSheet.getDataRange().getValues().slice(1);
  var match = clients.filter(function(r) { return String(r[0]) === data.client_id; });
  var full_name = match.length > 0 ? String(match[0][1]) : data.client_id;

  return { name: full_name, date: data.date };
}
