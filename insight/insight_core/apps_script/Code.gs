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
    .setTitle("Insight Core")
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

// Returns up to 10 distinct dates (most recent first) that already have at least
// one reading for this client, across all components. Used by both tabs to show
// "logged dates" chips so the trainer doesn't have to guess/remember a date to edit.
function getClientDates(clientId) {
  var sheet = SS.getSheetByName(READINGS_TAB);
  var data = sheet.getDataRange().getValues();
  var seen = {};
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][IDX.CLIENT_ID]) === clientId) {
      seen[_dateStr(data[i][IDX.DATE])] = true;
    }
  }
  var dates = Object.keys(seen);
  dates.sort(function(a, b) { return b.localeCompare(a); }); // ISO strings sort lexically = chronologically
  return dates.slice(0, 10);
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

// F02-S02 — Full Assessment Form
// metric_id -> {component, unit}, mirrors metric_master (8 active components + ankle_assessment).
// anthropometric (0 metrics) and apley_scratch (0 metrics) are excluded — nothing maps to them.
var METRIC_MAP = {
  weight_kg:   { component: "body_vitals", unit: "kg" },
  fat_pct:     { component: "body_vitals", unit: "%" },
  muscle_pct:  { component: "body_vitals", unit: "%" },
  bp_systol:   { component: "body_vitals", unit: "mmHg" },
  bp_diastol:  { component: "body_vitals", unit: "mmHg" },
  bpm:         { component: "body_vitals", unit: "bpm" },
  height_cm:   { component: "body_vitals", unit: "cm" },

  neck:     { component: "body_measurements", unit: "inches" },
  waist:    { component: "body_measurements", unit: "inches" },
  abdomen:  { component: "body_measurements", unit: "inches" },
  hips:     { component: "body_measurements", unit: "inches" },
  thighs:   { component: "body_measurements", unit: "inches" },
  calves:   { component: "body_measurements", unit: "inches" },
  arms:     { component: "body_measurements", unit: "inches" },
  forearms: { component: "body_measurements", unit: "inches" },
  chest:    { component: "body_measurements", unit: "inches" },

  pushups:        { component: "physio_1", unit: "reps" },
  squats:         { component: "physio_1", unit: "reps" },
  crunches:       { component: "physio_1", unit: "reps" },
  pullups_reps:   { component: "physio_1", unit: "reps" },
  pullups_weight: { component: "physio_1", unit: "lbs" },

  plank:            { component: "physio_2", unit: "seconds" },
  right_side_plank: { component: "physio_2", unit: "seconds" },
  left_side_plank:  { component: "physio_2", unit: "seconds" },
  hold_40deg:       { component: "physio_2", unit: "seconds" },
  sorenson_hold:    { component: "physio_2", unit: "seconds" },

  cooper_test: { component: "physio_3", unit: "km" },
  flexibility: { component: "physio_3", unit: "cm" },

  balance_normal_open:       { component: "balance_open", unit: "seconds" },
  balance_tandem_right_open: { component: "balance_open", unit: "seconds" },
  balance_tandem_left_open:  { component: "balance_open", unit: "seconds" },
  balance_right_up_open:     { component: "balance_open", unit: "seconds" },
  balance_left_up_open:      { component: "balance_open", unit: "seconds" },

  balance_normal_closed:       { component: "balance_closed", unit: "seconds" },
  balance_tandem_right_closed: { component: "balance_closed", unit: "seconds" },
  balance_tandem_left_closed:  { component: "balance_closed", unit: "seconds" },
  balance_right_up_closed:     { component: "balance_closed", unit: "seconds" },
  balance_left_up_closed:      { component: "balance_closed", unit: "seconds" },

  bench_press_reps:   { component: "strength", unit: "reps" },
  bench_press_weight: { component: "strength", unit: "lbs" },
  leg_press_reps:     { component: "strength", unit: "reps" },
  leg_press_weight:   { component: "strength", unit: "lbs" },
  deadlift_reps:      { component: "strength", unit: "reps" },
  deadlift_weight:    { component: "strength", unit: "lbs" },
  squat_reps:         { component: "strength", unit: "reps" },
  squat_weight:       { component: "strength", unit: "lbs" },

  ankle_right_mobility: { component: "ankle_assessment", unit: "pass/fail" },
  ankle_left_mobility:  { component: "ankle_assessment", unit: "pass/fail" },
  ankle_pronation:      { component: "ankle_assessment", unit: "yes/no" },

  // Added post-launch, per Arun's feedback (mile_test stored as total seconds — same
  // "duration in seconds" convention as plank/balance/hold metrics, not hh:mm:ss).
  mile_test:    { component: "physio_3", unit: "seconds" },
  coordination: { component: "physio_3", unit: "cm" },

  stork_stand_left_open:  { component: "balance_open", unit: "seconds" },
  stork_stand_right_open: { component: "balance_open", unit: "seconds" },
  stork_toes_left_open:   { component: "balance_open", unit: "seconds" },
  stork_toes_right_open:  { component: "balance_open", unit: "seconds" },

  stork_stand_left_closed:  { component: "balance_closed", unit: "seconds" },
  stork_stand_right_closed: { component: "balance_closed", unit: "seconds" },
  stork_toes_left_closed:   { component: "balance_closed", unit: "seconds" },
  stork_toes_right_closed:  { component: "balance_closed", unit: "seconds" },

  // Confirmed with Arun (2026-06-24): skinfold caliper readings are mm.
  skinfold_chest:   { component: "skinfold_measurements", unit: "mm" },
  skinfold_abdomen: { component: "skinfold_measurements", unit: "mm" },
  skinfold_thighs:  { component: "skinfold_measurements", unit: "mm" }
};

// Returns ALL existing readings for a client+date across every component, as {metric_id: value}.
// Used by the full assessment form to pre-fill all 9 sections (vs. getReadings, which is
// body_vitals-only and stays as-is for the Check-In tab).
function getFullReadings(clientId, date) {
  var sheet = SS.getSheetByName(READINGS_TAB);
  var data = sheet.getDataRange().getValues();
  var result = {};
  for (var i = 1; i < data.length; i++) {
    if (String(data[i][IDX.CLIENT_ID]) === clientId &&
        _dateStr(data[i][IDX.DATE]) === date) {
      result[String(data[i][IDX.METRIC])] = data[i][IDX.VALUE];
    }
  }
  return result;
}

// Upserts/deletes reading rows for a client+date across all metrics in METRIC_MAP.
// Same per-field logic as submitReadings, generalized: every metric (including pair members)
// is upserted/deleted independently — no pair-completeness block.
// values: {metric_id: stringValueOrEmpty}
// Returns {name, date, saved, removed}.
function submitFullAssessment(data) {
  var sheet = SS.getSheetByName(READINGS_TAB);
  var existing = sheet.getDataRange().getValues();
  var now = Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd HH:mm:ss");

  var rowsToDelete = [];
  var saved = 0;
  var removed = 0;

  Object.keys(data.values).forEach(function(metricId) {
    var meta = METRIC_MAP[metricId];
    if (!meta) return; // unknown metric id — ignore rather than write a malformed row

    var value = data.values[metricId];
    var hasValue = value !== "" && value !== null && value !== undefined;

    var existingRow = -1;
    for (var i = 1; i < existing.length; i++) {
      if (String(existing[i][IDX.CLIENT_ID]) === data.client_id &&
          _dateStr(existing[i][IDX.DATE])    === data.date &&
          String(existing[i][IDX.COMPONENT]) === meta.component &&
          String(existing[i][IDX.METRIC])    === metricId) {
        existingRow = i + 1;
        break;
      }
    }

    if (hasValue) {
      if (existingRow !== -1) {
        sheet.getRange(existingRow, COL.VALUE).setValue(Number(value));
        sheet.getRange(existingRow, COL.RECORDED_AT).setValue(now);
      } else {
        sheet.appendRow([data.client_id, data.date, meta.component, metricId, Number(value), meta.unit, "form", "", now]);
      }
      saved++;
    } else if (existingRow !== -1) {
      rowsToDelete.push(existingRow);
      removed++;
    }
  });

  // Delete bottom-to-top to avoid index shift between deletions
  rowsToDelete.sort(function(a, b) { return b - a; });
  rowsToDelete.forEach(function(r) { sheet.deleteRow(r); });

  var clientSheet = SS.getSheetByName(CLIENT_TAB);
  var clients = clientSheet.getDataRange().getValues().slice(1);
  var match = clients.filter(function(r) { return String(r[0]) === data.client_id; });
  var full_name = match.length > 0 ? String(match[0][1]) : data.client_id;

  return { name: full_name, date: data.date, saved: saved, removed: removed };
}
