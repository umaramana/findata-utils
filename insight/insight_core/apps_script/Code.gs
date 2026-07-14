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
var COMPONENT_MASTER_TAB = "component_master";
var METRIC_MASTER_TAB    = "metric_master";
var TZ = "Asia/Kolkata";

// Components with zero metrics — excluded from report config UI.
var EMPTY_COMPONENTS = ["anthropometric", "apley_scratch"];

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

// F05-S01_S02 — Report Config: component list + reading counts
// Returns all active components (excludes EMPTY_COMPONENTS) with a live reading count
// for the given client + date range. Single call — avoids N round-trips for N components.
// [{component_id, display_name, count}] in component_master row order.
function getComponentsWithCounts(clientId, dateFrom, dateTo) {
  var compSheet = SS.getSheetByName(COMPONENT_MASTER_TAB);
  var compData  = compSheet.getDataRange().getValues();
  var components = [];
  for (var ci = 1; ci < compData.length; ci++) {
    var cid = String(compData[ci][0]);
    if (EMPTY_COMPONENTS.indexOf(cid) !== -1) continue;
    components.push({ component_id: cid, display_name: String(compData[ci][1]) });
  }

  var readSheet = SS.getSheetByName(READINGS_TAB);
  var readData  = readSheet.getDataRange().getValues();

  var counts = {};
  components.forEach(function(c) { counts[c.component_id] = 0; });

  for (var ri = 1; ri < readData.length; ri++) {
    var row = readData[ri];
    if (String(row[IDX.CLIENT_ID]) !== clientId) continue;
    var rowDate = _dateStr(row[IDX.DATE]);
    if (rowDate < dateFrom || rowDate > dateTo) continue;
    var comp = String(row[IDX.COMPONENT]);
    if (counts.hasOwnProperty(comp)) counts[comp]++;
  }

  return components.map(function(c) {
    return { component_id: c.component_id, display_name: c.display_name, count: counts[c.component_id] };
  });
}

// F05-S01_S02 — Report Config: query engine
// Pulls readings in range, groups by component → metric, resolves baselines from full
// client history, computes derived metrics (BMI, WHR) per date where inputs are present.
//
// params: { client_id, date_from, date_to, component_ids[], output_type, layout }
//
// Returns:
//   { client_id, date_from, date_to, output_type, layout,
//     components: {
//       component_id: {
//         display_name,
//         metrics: { metric_id: { display_name, readings: [{date,value}], baseline } },
//         derived: { bmi: [{date,value}], waist_hip_ratio: [{date,value}] }
//       }
//     }
//   }
//   or { error: "..." } on empty/invalid input.
function generateReportPayload(params) {
  var clientId   = params.client_id;
  var dateFrom   = params.date_from;
  var dateTo     = params.date_to;
  var selectedComponents = params.component_ids || [];

  if (selectedComponents.length === 0) {
    return { error: "No components selected." };
  }

  // Load metric_master for display names
  var metricSheet = SS.getSheetByName(METRIC_MASTER_TAB);
  var metricData  = metricSheet.getDataRange().getValues();
  var metricMeta  = {}; // metric_id -> display_name
  for (var mi = 1; mi < metricData.length; mi++) {
    metricMeta[String(metricData[mi][0])] = String(metricData[mi][2]);
  }

  // Load component_master for display names
  var compSheet = SS.getSheetByName(COMPONENT_MASTER_TAB);
  var compData  = compSheet.getDataRange().getValues();
  var compMeta  = {}; // component_id -> display_name
  for (var ci = 1; ci < compData.length; ci++) {
    compMeta[String(compData[ci][0])] = String(compData[ci][1]);
  }

  // Initialise payload skeleton
  var payload = {};
  selectedComponents.forEach(function(cid) {
    payload[cid] = { display_name: compMeta[cid] || cid, metrics: {}, derived: {} };
  });

  // Single pass over all client readings:
  //   - Track baseline (min date) per metric across ALL history
  //   - Collect in-range readings for selected components only
  var baselineDates  = {}; // metric_id -> earliest date string
  var inRange = {};         // component_id -> metric_id -> [{date, value}]
  selectedComponents.forEach(function(cid) { inRange[cid] = {}; });

  var readSheet = SS.getSheetByName(READINGS_TAB);
  var readData  = readSheet.getDataRange().getValues();

  for (var ri = 1; ri < readData.length; ri++) {
    var row = readData[ri];
    if (String(row[IDX.CLIENT_ID]) !== clientId) continue;

    var rowDate   = _dateStr(row[IDX.DATE]);
    var rowComp   = String(row[IDX.COMPONENT]);
    var rowMetric = String(row[IDX.METRIC]);
    var rowValue  = row[IDX.VALUE];

    // Baseline: minimum date across all history for this client+metric
    if (!baselineDates[rowMetric] || rowDate < baselineDates[rowMetric]) {
      baselineDates[rowMetric] = rowDate;
    }

    // In-range: selected components + within date window only
    if (selectedComponents.indexOf(rowComp) === -1) continue;
    if (rowDate < dateFrom || rowDate > dateTo) continue;

    if (!inRange[rowComp][rowMetric]) inRange[rowComp][rowMetric] = [];
    inRange[rowComp][rowMetric].push({ date: rowDate, value: rowValue });
  }

  // Attach sorted readings + baselines to payload
  selectedComponents.forEach(function(cid) {
    Object.keys(inRange[cid]).forEach(function(mid) {
      var readings = inRange[cid][mid];
      readings.sort(function(a, b) { return a.date.localeCompare(b.date); });
      payload[cid].metrics[mid] = {
        display_name: metricMeta[mid] || mid,
        readings: readings,
        baseline: baselineDates[mid] || null
      };
    });
  });

  // Load client profile (gender + dob) for BMR calculation
  var clientGender = null;
  var clientDob    = null;
  var clientSheet  = SS.getSheetByName("client_master");
  if (clientSheet) {
    var clientData = clientSheet.getDataRange().getValues();
    for (var cli = 1; cli < clientData.length; cli++) {
      if (String(clientData[cli][0]) === clientId) {
        clientGender = String(clientData[cli][2]).toLowerCase();  // "male" | "female"
        clientDob    = clientData[cli][3];                        // Date or YYYY-MM-DD string
        break;
      }
    }
  }

  // Derived — BMI + BMR (body_vitals: weight_kg + height_cm, same date)
  if (payload["body_vitals"]) {
    var bvIn = inRange["body_vitals"] || {};
    var weightByDate = {};
    var heightByDate = {};
    (bvIn["weight_kg"] || []).forEach(function(r) { weightByDate[r.date] = r.value; });
    (bvIn["height_cm"] || []).forEach(function(r) { heightByDate[r.date] = r.value; });
    var bmiReadings = [];
    var bmrReadings = [];
    var genderOffset = clientGender === "male" ? 5 : clientGender === "female" ? -161 : null;
    var dobMs = clientDob ? new Date(clientDob).getTime() : null;

    Object.keys(weightByDate).forEach(function(d) {
      var h = heightByDate[d];
      if (!h || h <= 0) return;
      var w = weightByDate[d];
      var hm = h / 100;
      bmiReadings.push({ date: d, value: Math.round(w / (hm * hm) * 10) / 10 });

      if (genderOffset !== null && dobMs) {
        var ageYears = Math.floor((new Date(d).getTime() - dobMs) / (365.25 * 24 * 3600 * 1000));
        var bmr = Math.round(10 * w + 6.25 * h - 5 * ageYears + genderOffset);
        bmrReadings.push({ date: d, value: bmr });
      }
    });
    if (bmiReadings.length > 0) {
      bmiReadings.sort(function(a, b) { return a.date.localeCompare(b.date); });
      payload["body_vitals"].derived["bmi"] = bmiReadings;
    }
    if (bmrReadings.length > 0) {
      bmrReadings.sort(function(a, b) { return a.date.localeCompare(b.date); });
      payload["body_vitals"].derived["bmr"] = bmrReadings;
    }
  }

  // Derived — WHR (body_measurements: waist + hips, same date)
  if (payload["body_measurements"]) {
    var bmIn = inRange["body_measurements"] || {};
    var waistByDate = {};
    var hipsByDate  = {};
    (bmIn["waist"] || []).forEach(function(r) { waistByDate[r.date] = r.value; });
    (bmIn["hips"]  || []).forEach(function(r) { hipsByDate[r.date]  = r.value; });
    var whrReadings = [];
    Object.keys(waistByDate).forEach(function(d) {
      var hips = hipsByDate[d];
      if (hips && hips > 0) {
        whrReadings.push({ date: d, value: Math.round(waistByDate[d] / hips * 1000) / 1000 });
      }
    });
    if (whrReadings.length > 0) {
      whrReadings.sort(function(a, b) { return a.date.localeCompare(b.date); });
      payload["body_measurements"].derived["waist_hip_ratio"] = whrReadings;
    }
  }

  // Empty result guard
  var hasReadings = selectedComponents.some(function(cid) {
    return Object.keys(payload[cid].metrics).length > 0;
  });
  if (!hasReadings) {
    return { error: "No readings found for the selected client, components, and date range." };
  }

  return {
    client_id:   clientId,
    date_from:   dateFrom,
    date_to:     dateTo,
    output_type: params.output_type,
    layout:      params.layout || null,
    components:  payload
  };
}

// F05-S07 — Report Generation Trigger: App-to-Python Bridge.
//
// Calls the Cloud Run report_service endpoint directly (synchronous HTTP,
// no polling/queue — locked decision, see F05-S07 card). Same shape as
// generateReportPayload() above, minus output_type: this card scopes
// full_report only, nudge PNG generation stays out of this bridge entirely.
//
// Endpoint URL + shared secret are read from Script Properties (Project
// Settings > Script Properties in the Apps Script editor), never hardcoded
// here — see report_service/DEPLOY.md for how they're set.
//
// params: { client_id, date_from, date_to, component_ids[], layout }
// Returns: { status: "done", output_url } or { status: "error", error_message }
function generateReport(params) {
  var props = PropertiesService.getScriptProperties();
  var endpointUrl = props.getProperty("REPORT_SERVICE_URL");
  var sharedSecret = props.getProperty("REPORT_SHARED_SECRET");

  if (!endpointUrl || !sharedSecret) {
    return { status: "error", error_message: "Report service is not configured (missing Script Properties)." };
  }

  var payload = {
    client_id:     params.client_id,
    date_from:     params.date_from,
    date_to:       params.date_to,
    component_ids: params.component_ids,
    layout:        params.layout
  };

  var options = {
    method: "post",
    contentType: "application/json",
    headers: { "X-Report-Secret": sharedSecret },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  var response;
  try {
    response = UrlFetchApp.fetch(endpointUrl, options);
  } catch (e) {
    return { status: "error", error_message: "Could not reach report service: " + e.message };
  }

  var body;
  try {
    body = JSON.parse(response.getContentText());
  } catch (e) {
    return { status: "error", error_message: "Report service returned an unreadable response." };
  }

  // Surface the service's own structured error (400/401/422/500/502) as-is —
  // it already distinguishes bad request / auth / no-data / pipeline failure.
  return body;
}
