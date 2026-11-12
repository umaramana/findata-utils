# PROPOSED (12 Nov 2026) - NEW obligations (Step 2). Red until Step 3 builds them.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Expected results are the agreed behaviour, not yet the code's. Ollama is a fake; names are invented.

Feature: Pages with no text layer are UNREAD
  The local path reads text only. A page with no text layer is not sent to the model; it is
  listed as UNREAD with the file name, page number and reason, and the document is "partial".
  Nothing on it is guessed and nothing is counted as zero.

  @keep
  Scenario: A text page is extracted and the image page is listed as UNREAD
    # why: decision 3 (12 Nov 2026) - extract what can be read, name what cannot
    Given the pages "1 Wages 75,000.00 2 Federal 12,000.00 / (image)"
    And the model answers box_1_wages = "75,000.00"
    And the model answers box_2_federal_withheld = "12,000.00"
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is 75000.0
    And the unread pages are "acme_w2.pdf page 2: no text layer"
    And the status is "partial"
    And the prompt does not contain "image only"

  @keep
  Scenario: A value not on any text page is rejected even when an image page exists
    # why: the model cannot have read the image page, so a value "from it" is a guess
    Given the pages "1 Wages 75,000.00 2 Federal 12,000.00 / (image)"
    And the model answers box_1_wages = "80,000.00"
    And the model answers box_2_federal_withheld = "12,000.00"
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is null
    And field box_1_wages has confidence "rejected"
    And the verification failures are "box_1_wages"
    And the missing required fields are "box_1_wages"

  @keep
  Scenario: A document with no text layer at all is not sent to the model
    # why: there is nothing for a text-only model to read; every required field is named as missing
    Given the pages "(image) / (image)"
    When "acme_w2.pdf" is extracted locally
    Then the model was not called
    And the unread pages are "acme_w2.pdf page 1: no text layer; acme_w2.pdf page 2: no text layer"
    And the missing required fields are "box_1_wages, box_2_federal_withheld"
    And field box_1_wages is null
    And the status is "partial"

  @keep
  Scenario: UNREAD page numbers are the page numbers in the original file
    # why: the preparer opens the PDF and goes to that page; dropped copy pages must not shift it
    Given the pages "Form W-2 Copy B / Copy C / (image)"
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then the dropped page indices are "1"
    And the unread pages are "acme_w2.pdf page 3: no text layer"
