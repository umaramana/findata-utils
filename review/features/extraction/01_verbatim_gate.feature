# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: The verbatim gate
  A value the model returns counts only if it appears in the page's own text tokens.
  Spaces, thousands commas and $ are ignored when comparing. A value that is not on
  the page is rejected (null) and named in the verification failures.

  @keep
  Scenario Outline: A value is kept only if it appears in the page text
    # why: a small local model invents numbers; the page's text layer is the ground truth
    Given a text page reading "<page>"
    And the model answers box_1_wages = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is <value>
    And field box_1_wages has confidence "<confidence>"
    And the verification failures are "<failures>"

    Examples:
      | page               | answer       | value   | confidence | failures    |
      | 1 Wages 75,000.00  | "75000.00"   | 75000.0 | verified   | (none)      |
      | 1 Wages 75000.00   | "$75,000.00" | 75000.0 | verified   | (none)      |
      | 1 Wages 75,000.00  | 75000        | 75000.0 | verified   | (none)      |
      | 1 Wages 75,000.00  | "76,000.00"  | null    | rejected   | box_1_wages |
