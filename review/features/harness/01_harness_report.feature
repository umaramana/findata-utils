# APPROVED 13 Nov 2026 (user), plus the header scenario the user asked for. Step 5.
# 19 Nov 2026 (user): one truth.json per docs folder, entries keyed by file name (case-insensitive).
# Marks: @keep = stays as is | @new = new obligation, red until built
# Each run of the harness calls extract.extract_local; in the Contract that call is a fake that
# returns what the scenario says. Names are invented (ACME, KLMN).

Feature: Harness report per form type, with no values in it
  The harness runs each document N times and reports, for each form type, whether every field
  came back the same each run (STABLE / VARIED), whether it matched the truth file for that form
  type (CORRECT / WRONG), and how long a document took. The report never prints a value, so the
  same report is safe on a real document. It is written to a file; the console shows the verdict
  and the file path.

  @new
  Scenario: Each document is scored against its own entry in the folder's truth.json
    # why: user 19 Nov 2026 - a folder can mix clients and hold several documents of one form type
    # (replaces "Each form type gets its own section, scored against its own truth file")
    Given the documents "acme_w2.pdf, klmn_w2.pdf, klmn_1099-int.pdf"
    And a truth.json in the docs folder with an entry for each document
    And every run returns that document's truth values
    When the harness runs 3 times per document
    Then the report has the sections "W-2, 1099-INT"
    And every truth field is "CORRECT 3/3"

  @new
  Scenario Outline: The truth entry is found by file name, ignoring case
    # why: user 19 Nov 2026 - "W2.PDF" matches a "w2.pdf" entry
    Given the documents "<document>"
    And a truth.json in the docs folder with an entry for "<entry>"
    When the harness runs 3 times per document
    Then document 1 shows "box_1_wages: CORRECT 3/3"

    Examples:
      | document    | entry       |
      | acme_w2.pdf | acme_w2.pdf |
      | ACME_W2.PDF | acme_w2.pdf |
      | acme_w2.pdf | ACME_W2.PDF |

  @new
  Scenario: The truth form type sets the section when the file name has no form word
    Given the documents "acme_wages.pdf"
    And a truth.json in the docs folder giving acme_wages.pdf the form type "W-2"
    When the harness runs 3 times per document
    Then the report has the sections "W-2"
    And document 1 shows "__form_type__: CORRECT 3/3"

  @new
  Scenario: A wrong form type is scored, and the truth fields are still scored, never skipped
    # why: user 19 Nov 2026 - the truth form type is W-2, the model answers 1099-INT on every run
    # (verdict wording as in the existing scenarios: "WRONG on n/n runs"; a field not returned is WRONG)
    Given the documents "acme_w2.pdf"
    And a truth.json in the docs folder with an entry for each document
    And every run answers the form type "1099-INT"
    When the harness runs 3 times per document
    Then the report has the sections "W-2"
    And document 1 shows "__form_type__: WRONG on 3/3 runs"
    And document 1 shows "box_1_wages: WRONG on 3/3 runs"
    And document 1 shows "box_2_federal_withheld: WRONG on 3/3 runs"

  @new
  Scenario: A document with no truth entry runs unscored
    Given the documents "acme_w2.pdf, klmn_w2.pdf"
    And a truth.json in the docs folder with an entry for acme_w2.pdf only
    When the harness runs 3 times per document
    Then document 2 shows "no truth entry"
    And the report shows "documents with no truth entry: 1"

  @new
  Scenario: A truth entry with no document is counted, not named
    Given the documents "acme_w2.pdf"
    And a truth.json in the docs folder with entries for "acme_w2.pdf, klmn_w2.pdf"
    When the harness runs 3 times per document
    Then the report shows "truth entries with no document: 1"
    And "klmn" does not appear in the report

  @new
  Scenario: The set label and the file names never appear in the report
    Given the documents "acme_w2.pdf"
    And a truth.json in the docs folder with the set "Jane Roe 2025"
    When the harness runs 3 times per document
    Then none of "Jane Roe, acme_w2" appears in the report

  @new
  Scenario Outline: A bad truth.json stops before any model call, naming the entry by number
    Given the documents "acme_w2.pdf"
    And a truth.json in the docs folder where <problem>
    When the harness runs 3 times per document
    Then no extraction is called
    And the harness stops with "<message>"
    And "acme_w2" does not appear in the message

    Examples:
      | problem                                   | message                                      |
      | entry 1 has no form_type                  | truth.json entry 1: no form_type             |
      | entry 1 has the form type "1098"          | truth.json entry 1: unknown form type        |
      | there is no "documents" key               | truth.json: no documents                     |

  @new
  Scenario: The report header names the model, the documents run, and the read / partial / UNREAD / failed counts
    # why: user decision 13 Nov 2026 - the header says at a glance what was run and what didn't read
    # changed 16 Nov 2026 (user): three counts, each document in exactly one -
    #   read    = every page extracted
    #   partial = text pages extracted, but one or more pages UNREAD, or a required field missing
    #   UNREAD  = no text layer on any page, or the file won't open
    # a document is counted by its worst run (UNREAD > partial > read). failed is separate: documents where
    # any run raised another error. A document whose every run raised another error is only in failed.
    Given the documents "acme_w2.pdf, klmn_1099-int.pdf, acme_scan_w2.pdf, klmn_w2.pdf, acme_blank_w2.pdf, acme_locked_w2.pdf"
    And the model "acme-model:1b"
    And run 2 of klmn_1099-int.pdf raises ExtractionFailed
    And acme_scan_w2.pdf has a page with no text layer
    And klmn_w2.pdf has a required field missing
    And acme_blank_w2.pdf has no text layer on any page
    And acme_locked_w2.pdf will not open
    When the harness runs 3 times per document
    Then the report header is "model acme-model:1b | documents 6 | read 2 | partial 2 | UNREAD 2 | failed 1"

  @new
  Scenario: A field that varied is counted, not shown
    # why: masked report - a real document's amounts must not reach the report (or Claude)
    Given the documents "acme_w2.pdf"
    And box_1_wages comes back 75000.0, 75000.0, 76000.0 on the 3 runs
    When the harness runs 3 times per document
    Then the report shows "box_1_wages: VARIED, 2 distinct values (2/3, 1/3)"
    And neither 75000.0 nor 76000.0 appears in the report, in any format
    # (was "no digit from ...": impossible as written - the header's counts contain 0)

  @new
  Scenario: Only the form's expected field names are printed; any other field is counted, not named
    # why: added 16 Nov 2026 (user) - a field name the model makes up can carry client text; the 16 Nov run
    #      printed "field_name" and "Mortgage interest received". A form type with no field list (UNKNOWN)
    #      has no expected names, so all of its fields are extra.
    # documents are numbered in sorted file-name order: acme_statement.pdf is 1, acme_w2.pdf is 2
    Given the documents "acme_w2.pdf, acme_statement.pdf"
    And acme_w2.pdf also returns the fields "field_name, Jane Roe ACME Payroll"
    And acme_statement.pdf also returns the fields "Mortgage interest received"
    When the harness runs 3 times per document
    Then document 2 shows "box_1_wages: STABLE"
    And document 2 shows "__form_type__: STABLE"
    And document 2 shows "extra fields: 2"
    And document 1 shows "extra fields: 2"
    And none of "field_name, Jane Roe, Mortgage, acme_box" appears in the report

  @new
  Scenario: A wrong field vs truth is counted, not shown
    Given the documents "acme_w2.pdf"
    And a truth.json in the docs folder with an entry for each document
    And box_1_wages comes back 75000.0, 75000.0, 76000.0 on the 3 runs
    When the harness runs 3 times per document
    Then the report shows "box_1_wages: WRONG on 1/3 runs"

  @new
  Scenario: Seconds per document come from the extraction time
    # why: model choice weighs speed; extract records extraction_time_ms (Contract 13)
    Given the documents "acme_w2.pdf"
    And the 3 runs take 100, 120 and 140 seconds
    When the harness runs 3 times per document
    Then the report shows "seconds per run: mean 120, slowest 140"

  @new
  Scenario: A document with no guessable form type runs without truth, under UNKNOWN
    # why: the synthetic 1098 is the out-of-scope regression case; it must come back UNKNOWN, not crash
    # changed 19 Nov 2026 (truth.json per folder): "no truth file for UNKNOWN" became the document's "no truth entry"
    Given the documents "acme_1098.pdf"
    And a truth.json in the docs folder with entries for "acme_w2.pdf"
    When the harness runs 3 times per document
    Then the report has the sections "UNKNOWN"
    And document 1 shows "no truth entry"

  @new
  Scenario: The report goes to a file; the console shows the verdict and the path
    # why: user rule - diagnostic output goes to a file
    Given the documents "acme_w2.pdf"
    When the harness runs 3 times per document
    Then a report file is written under "diag_output/"
    And the console shows "PASS" and the report file path

  @keep
  Scenario Outline: The exit code fails on a varied value field or a failed run
    # why: spec §4.0.9 - the harness can gate a build; pins current behaviour
    Given the documents "acme_w2.pdf"
    And <what happens>
    When the harness runs 3 times per document
    Then the harness exits with <code>

    Examples:
      | what happens                                                 | code |
      | every run returns the same values                            | 0    |
      | box_1_wages comes back 75000.0, 75000.0, 76000.0 on the 3 runs | 1    |
      | run 2 raises ExtractionFailed                                | 1    |
      | confidence_notes comes back "a", "b", "a" on the 3 runs       | 0    |
