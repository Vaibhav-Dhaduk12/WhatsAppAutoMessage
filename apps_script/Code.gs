/**
 * Google Apps Script — Form-to-Sheets handler
 *
 * Deploy this as a Web App (Execute as: Me, Who has access: Anyone).
 * Paste the resulting URL into docs/index.html → GOOGLE_SCRIPT_URL.
 *
 * Sheet columns:
 *   A: Phone Number  |  B: Message  |  C: Scheduled Time  |  D: Status
 *
 * Setup:
 *   1. Open https://script.google.com and create a new project.
 *   2. Paste this file's contents.
 *   3. Update SPREADSHEET_ID with the ID from your Google Sheet URL.
 *   4. Deploy → New deployment → Web app.
 */

// ── Configuration ─────────────────────────────────────────────────────────────
var SPREADSHEET_ID = "REPLACE_WITH_YOUR_SPREADSHEET_ID";
var SHEET_NAME     = "Messages";          // Name of the tab in your sheet
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Handles GET requests (used for browser test & CORS pre-flight).
 */
function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({ status: "ok", message: "Auto-Msg Scheduler is running." }))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Handles POST requests from the frontend form.
 * Expects JSON body: { phone, message, scheduledTime }
 */
function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);

    var phone         = (data.phone         || "").toString().trim();
    var message       = (data.message       || "").toString().trim();
    var scheduledTime = (data.scheduledTime || "").toString().trim();

    if (!phone || !message || !scheduledTime) {
      return jsonResponse({ status: "error", message: "Missing required fields." });
    }

    var sheet = getOrCreateSheet();
    sheet.appendRow([phone, message, scheduledTime, "Pending"]);

    return jsonResponse({ status: "success", message: "Scheduled." });

  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getOrCreateSheet() {
  var ss    = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sheet = ss.getSheetByName(SHEET_NAME);

  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(["Phone Number", "Message", "Scheduled Time", "Status"]);
    sheet.setFrozenRows(1);
  }

  return sheet;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
