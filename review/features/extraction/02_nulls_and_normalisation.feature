# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Nulls and normalisation
  Amounts come back as numbers with $, commas and spaces removed. A box the model
  leaves empty stays null; it never becomes 0.

  @keep
  Scenario Outline: The model's answer becomes a number or null
    # why: null means "not found" and must not be added into totals as 0
    Given a text page reading "<page>"
    And the model answers box_2_federal_withheld = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_2_federal_withheld is <value>
    And field box_2_federal_withheld has confidence "verified"

    Examples:
      | page                    | answer       | value   |
      | 2 Federal 12,000.00     | null         | null    |
      | 2 Federal 12,000.00     | ""           | null    |
      | 2 Federal 0.00          | "0.00"       | 0.0     |
      | 2 Federal $12,000.00    | "$12,000.00" | 12000.0 |


