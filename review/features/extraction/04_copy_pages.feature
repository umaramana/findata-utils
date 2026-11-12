# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: IRS copy pages
  A W-2 or 1099 PDF often repeats the same boxes on Copy B, Copy C, Copy 2 and so on.
  Only the first copy page is sent to the model; the others are dropped and logged.

  @keep
  Scenario Outline: Every copy page after the first is dropped
    # why: reading every copy would repeat the values (box 17 three times, for example)
    Given the pages "<pages>"
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then the dropped page indices are "<dropped>"
    And <kept> pages were kept

    Examples:
      | pages                                                                      | dropped | kept |
      | Form W-2 Copy B For employee / Copy C For employee records / Copy 2 To be filed | 1, 2    | 1    |
      | Form W-2 Copy B For employee / Instructions for employee                   | (none)  | 2    |
      | Form 1099-INT Copy B For recipient / Copy 1 For state tax department       | 1       | 1    |
      | Form W-2 copy b / COPY C                                                   | 1       | 1    |
      | Form W-2 Copyright ACME / Copy B For employee                              | (none)  | 2    |

  @keep
  Scenario: A page with no text layer is never dropped as a copy
    # why: without text the designator cannot be read, so the page is left in (see PARKING_LOT.md)
    Given the pages "Form W-2 Copy B / (image) / Form W-2 Copy C"
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then the dropped page indices are "2"
    And 2 pages were kept
