# APPROVED 19 Nov 2026 (user) - new obligations. Marks: @new = new obligation, red until built.
# Ollama is a fake (each scenario says what the model answers); names are invented (ACME, KLMN).

Feature: The record keeps what the model said for a rejected value, and names fields not returned
  run.py writes each document's record to extractions/<mode>/<file>.json. A rejected value is
  still null in fields, but what the model said is kept under model_said. A field the form
  asks for that the model did not return is named under not_returned.

  @new
  Scenario Outline: A rejected value keeps what the model said
    # why: user 19 Nov 2026 - a rejected value must be visible, e.g. a value from the wrong box
    Given a text page reading "1 Wages 75,000.00 2 Federal income tax withheld 9,850.00"
    And the model answers box_1_wages = "75,000.00"
    And the model answers box_2_federal_withheld = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_2_federal_withheld is <value>
    And model_said is <model_said>

    Examples:
      | answer      | value  | model_said                                  |
      | "9,850.00"  | 9850.0 | {}                                          |
      | "9,999.00"  | null   | {"box_2_federal_withheld": "9,999.00"}      |
      | "N/A"       | null   | {"box_2_federal_withheld": "N/A"}           |

  @new
  Scenario: A box 17 item that is rejected is kept under model_said; the item that passed is not
    Given a text page reading "15 NC 17 State income tax 3,100.00"
    And the model answers box_17_state_income_tax = [{"state": "NC", "amount": "3,100.00"}, {"state": "VA", "amount": "999.00"}]
    When "acme_w2.pdf" is extracted locally
    Then field box_17_state_income_tax is [{"state": "NC", "amount": 3100.0}]
    And model_said is {"box_17_state_income_tax": [{"state": "VA", "amount": "999.00"}]}

  @new
  Scenario Outline: A field the form asks for that the model did not return is named
    Given a text page reading "1 Wages 75,000.00 2 Federal income tax withheld 9,850.00"
    And the model answers <answers>
    When "acme_w2.pdf" is extracted locally
    Then not_returned is "<not_returned>"

    Examples:
      | answers                                                                              | not_returned                                    |
      | box_1_wages = "75,000.00", box_2_federal_withheld = "9,850.00", box_17_state_income_tax = [] | (none)                                   |
      | box_1_wages = "75,000.00", box_2_federal_withheld = null, box_17_state_income_tax = []       | (none)                                   |
      | box_1_wages = "75,000.00"                                                            | box_2_federal_withheld, box_17_state_income_tax |
      | box_1_wages = "75,000.00", a name-only item for box_2_federal_withheld, box_17_state_income_tax = [] | box_2_federal_withheld          |

  @new
  Scenario: A document with no known form type has nothing under not_returned
    Given a text page reading "Mortgage interest received 12,000.00"
    And the model answers form type "UNKNOWN" and mortgage_interest = "12,000.00"
    When "acme_statement.pdf" is extracted locally
    Then not_returned is "(none)"

  @new
  Scenario: The written record carries model_said and not_returned, even when empty
    # why: run.py writes to_dict(); an absent key would read as "not checked"
    Given a text page reading "1 Wages 75,000.00 2 Federal income tax withheld 9,850.00"
    And the model answers box_1_wages = "75,000.00", box_2_federal_withheld = "9,850.00", box_17_state_income_tax = []
    When "acme_w2.pdf" is extracted locally
    Then the record has model_said {} and not_returned []

  @new
  Scenario: A document with no text on any page has nothing under not_returned
    # why: user 19 Nov 2026 - the model was never asked; the UNREAD pages already say why nothing was read
    Given the pages "(image) / (image)"
    When "acme_w2.pdf" is extracted locally
    Then the model was not called
    And not_returned is "(none)"
    And the unread pages are "acme_w2.pdf page 1: no text layer; acme_w2.pdf page 2: no text layer"
