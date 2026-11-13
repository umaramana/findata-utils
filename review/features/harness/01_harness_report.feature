# APPROVED 13 Nov 2026 (user), plus the header scenario the user asked for. Step 5.
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
  Scenario: Each form type gets its own section, scored against its own truth file
    # why: today --truth only works with one --doc, so a --docs run is never scored
    Given the documents "acme_w2.pdf, klmn_1099-int.pdf"
    And the truth files for "W-2, 1099-INT"
    And every run returns the truth values
    When the harness runs 3 times per document
    Then the report has the sections "W-2, 1099-INT"
    And every truth field is "CORRECT 3/3"

  @new
  Scenario: The report header names the model, the documents run, and the UNREAD and failed counts
    # why: user decision 13 Nov 2026 - the header says at a glance what was run and what didn't read
    # UNREAD = a document with a page that has no text layer, or that would not open at all.
    # failed = a document where any run raised another error. Each document is counted once.
    Given the documents "acme_w2.pdf, klmn_1099-int.pdf, acme_scan_w2.pdf"
    And the model "acme-model:1b"
    And acme_scan_w2.pdf has a page with no text layer
    And run 2 of klmn_1099-int.pdf raises ExtractionFailed
    When the harness runs 3 times per document
    Then the report header is "model acme-model:1b | documents 3 | UNREAD 1 | failed 1"

  @new
  Scenario: A field that varied is counted, not shown
    # why: masked report - a real document's amounts must not reach the report (or Claude)
    Given the documents "acme_w2.pdf"
    And box_1_wages comes back 75000.0, 75000.0, 76000.0 on the 3 runs
    When the harness runs 3 times per document
    Then the report shows "box_1_wages: VARIED, 2 distinct values (2/3, 1/3)"
    And no digit from 75000.0 or 76000.0 appears in the report

  @new
  Scenario: A wrong field vs truth is counted, not shown
    Given the documents "acme_w2.pdf"
    And the truth files for "W-2"
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
    Given the documents "acme_1098.pdf"
    And the truth files for "W-2"
    When the harness runs 3 times per document
    Then the report has the sections "UNKNOWN"
    And the report says "no truth file for UNKNOWN"

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
