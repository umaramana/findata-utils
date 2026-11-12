# PROPOSED (12 Nov 2026) - NEW obligations (Step 2). Red until Step 3 builds them.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Expected results are the agreed behaviour, not yet the code's. Ollama is a fake; names are invented.

Feature: Tighter verbatim gate
  Decisions of 12 Nov 2026 on the Step 1 weaknesses. A money value is matched against the
  page's grouped line text as a whole number after normalisation, never a fragment. Every gate
  or parse failure is named; nothing is dropped silently. The document is "partial" for a
  problem with a required field, a box 17 item or an UNREAD page; a rejected optional field
  is named but the status stays "extracted".

  @keep
  Scenario Outline: A money value must equal a whole number on the page
    # why: decision 1 - "500.00" inside "1,500.00" is a fragment, not a match
    Given a text page reading "<page>"
    And the model answers box_1_wages = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is <value>
    And field box_1_wages has confidence "<confidence>"

    Examples:
      | page                | answer      | value   | confidence |
      | 1 Wages 1,500.00    | "500.00"    | null    | rejected   |
      | 1 Wages 75,000.00   | "75"        | null    | rejected   |
      | 1 Wages 175,000.00  | "75,000.00" | null    | rejected   |
      | 1 Wages 75,000.00   | "75000"     | 75000.0 | verified   |
      | 1 Wages $75,000.00  | "75,000.00" | 75000.0 | verified   |
      | 1 Wages 75000.00    | "$75,000"   | 75000.0 | verified   |

  @keep
  Scenario Outline: A number pdfplumber splits into two words on one line still matches
    # why: decision of 12 Nov 2026 (#2) - the gate reads the line, so "75," "000.00" is 75,000.00
    Given the page tokens "<tokens>"
    And the model answers box_1_wages = "75,000.00"
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is <value>
    And field box_1_wages has confidence "<confidence>"

    Examples:
      | tokens                                        | value   | confidence |
      | 1@20,100 Wages@40,100 75,@90,100 000.00@110,100 | 75000.0 | verified   |
      | 1@20,100 Wages@40,100 $@90,100 75,000.00@100,100 | 75000.0 | verified   |
      | 1@20,100 Wages@40,100 75,000@90,100 .00@130,100 | 75000.0 | verified   |
      | 1@20,100 Wages@40,100 75,@90,100 000.00@40,140  | null    | rejected   |
      | 1@20,100 Wages@40,100 175,@90,100 000.00@110,100 | null    | rejected   |

  @keep
  Scenario: A box 17 item that fails the gate is named and the document is partial
    # why: decision 2 - never dropped silently
    Given a text page reading "1 Wages 75,000.00 2 Federal 12,000.00 17 NC 3,100.00 SC 420.00"
    And the model answers box_1_wages = "75,000.00"
    And the model answers box_2_federal_withheld = "12,000.00"
    And the model answers box_17_state_income_tax = [{"state": "NC", "amount": "3,100.00"}, {"state": "SC", "amount": "999.00"}]
    When "acme_w2.pdf" is extracted locally
    Then field box_17_state_income_tax is [{"state": "NC", "amount": 3100.0}]
    And the verification failures are "box_17_state_income_tax"
    And the status is "partial"

  @keep
  Scenario: An optional field that fails the gate is named but the document stays extracted
    # why: decision of 12 Nov 2026 (#1) - an invented optional box is logged, not a reason to stop
    Given a text page reading "1 Interest income 1,200.00"
    And the model answers box_1_interest_income = "1,200.00"
    And the model answers box_4_federal_withheld = "999.00"
    When "klmn_1099-int.pdf" is extracted locally
    Then the verification failures are "box_4_federal_withheld"
    And field box_4_federal_withheld is null
    And the missing required fields are "(none)"
    And the status is "extracted"

  @keep
  Scenario Outline: A money field answered with words is a parse failure
    # why: decision 3 - "N/A" is not an amount; it is null and logged, never "verified"
    Given a text page reading "1 Wages 75,000.00 2 Federal N/A"
    And the model answers box_1_wages = "75,000.00"
    And the model answers box_2_federal_withheld = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_2_federal_withheld is null
    And field box_2_federal_withheld has confidence "rejected"
    And the parse failures are "box_2_federal_withheld"
    And the status is "partial"

    Examples:
      | answer         |
      | "N/A"          |
      | "see attached" |

  @keep
  Scenario: An optional money field answered with words is a parse failure, the status stays extracted
    # why: decisions 3 and #1 together - logged and null, but only a required field makes it partial
    Given a text page reading "1 Interest income 1,200.00 4 Federal N/A"
    And the model answers box_1_interest_income = "1,200.00"
    And the model answers box_4_federal_withheld = "N/A"
    When "klmn_1099-int.pdf" is extracted locally
    Then field box_4_federal_withheld is null
    And field box_4_federal_withheld has confidence "rejected"
    And the parse failures are "box_4_federal_withheld"
    And the status is "extracted"
