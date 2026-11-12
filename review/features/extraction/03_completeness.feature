# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Completeness check
  Each form has required fields. A required field that is null after the gate is
  named in the missing list and the document status is "partial".

  @keep
  Scenario Outline: Missing required W-2 fields are named, never summed as zero
    # why: the preparer must see exactly which box is missing, per spec §4.0.7
    Given a text page reading "1 Wages 75,000.00 2 Federal 12,000.00"
    And the model answers box_1_wages = <box 1>
    And the model answers box_2_federal_withheld = <box 2>
    When "acme_w2.pdf" is extracted locally
    Then the missing required fields are "<missing>"
    And the status is "<status>"

    Examples:
      | box 1       | box 2       | missing                              | status    |
      | "75,000.00" | "12,000.00" | (none)                               | extracted |
      | "75,000.00" | null        | box_2_federal_withheld               | partial   |
      | null        | null        | box_1_wages, box_2_federal_withheld  | partial   |
      | "75,000.00" | "13,000.00" | box_2_federal_withheld               | partial   |

  @keep
  Scenario Outline: Each form type has its own required field; optional ones may be null
    # why: one required box per 1099 form; an empty optional box is normal, not a gap
    Given a text page reading "<page>"
    And the model answers <required> = <answer>
    And the model answers <optional> = null
    When "<file>" is extracted locally
    Then the missing required fields are "<missing>"
    And the status is "<status>"

    Examples:
      | file              | page                         | required                  | answer     | optional                    | missing                   | status    |
      | klmn_1099-int.pdf | 1 Interest income 1,200.00   | box_1_interest_income     | "1,200.00" | box_4_federal_withheld      | (none)                    | extracted |
      | klmn_1099-int.pdf | 1 Interest income 1,200.00   | box_1_interest_income     | null       | box_4_federal_withheld      | box_1_interest_income     | partial   |
      | klmn_1099div.pdf  | 1a Ordinary dividends 800.00 | box_1a_ordinary_dividends | "800.00"   | box_1b_qualified_dividends  | (none)                    | extracted |
      | klmn_1099div.pdf  | 1a Ordinary dividends 800.00 | box_1a_ordinary_dividends | null       | box_1b_qualified_dividends  | box_1a_ordinary_dividends | partial   |

  @keep
  Scenario: A required field the model leaves out entirely is missing too
    # why: an absent key is the same gap as a null value
    Given a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    When "acme_w2.pdf" is extracted locally
    Then the missing required fields are "box_2_federal_withheld"
    And the status is "partial"
