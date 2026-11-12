# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Files that cannot be read, and the form type from the filename
  A file that will not open is never returned as an empty result. The filename gives
  a form-type hint; no hint means the model must name the form.

  @keep
  Scenario: A file that will not open is raised as unreadable
    # why: an empty result would look like a form with nothing on it (spec §3.1)
    Given "acme_w2.pdf" is not a PDF
    When "acme_w2.pdf" is extracted locally
    Then extraction stops with a UnreadableDocument error saying "acme_w2.pdf: file will not open"

  @keep
  Scenario Outline: The form type is guessed from the filename
    # why: the hint limits the model to that form's field list, which keeps runs stable
    When the form type is guessed from "<filename>"
    Then the guess is "<form type>"

    Examples:
      | filename                | form type |
      | acme_w2_2025.pdf        | W-2       |
      | ACME W-2.pdf            | W-2       |
      | KLMN-1099-INT.pdf       | 1099-INT  |
      | klmn 1099div.pdf        | 1099-DIV  |
      | acme_statement.pdf      | (none)    |
      | acmew2.pdf              | (none)    |
