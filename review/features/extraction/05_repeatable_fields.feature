# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Repeatable fields come back as lists
  W-2 box 17 (state income tax) can appear more than once, and 1099 "other_boxes" holds
  every other populated box. Both are lists. Each item is checked on its own.

  @keep
  Scenario Outline: Box 17 items found on the page are kept as a list
    # why: a two-state W-2 has two box 17 amounts; a single value would lose one
    # added 13 Nov 2026 (mutation run): a state code not on the page fails even when its amount is there;
    # an item that is not a state/amount pair is dropped and named as a failure (user decision 13 Nov 2026:
    # never skipped silently); the items after it are still checked
    Given a text page reading "17 NC 3,100.00 SC 420.00"
    And the model answers box_17_state_income_tax = <answer>
    When "acme_w2.pdf" is extracted locally
    Then field box_17_state_income_tax is <value>
    And field box_17_state_income_tax has confidence "<confidence>"
    And the verification failures are "<failures>"

    Examples:
      | answer                                                                   | value                                                                | confidence | failures                |
      | [{"state": "NC", "amount": "3,100.00"}, {"state": "SC", "amount": "420.00"}] | [{"state": "NC", "amount": 3100.0}, {"state": "SC", "amount": 420.0}] | verified   | (none)                  |
      | [{"state": "NC", "amount": "3,100.00"}]                                  | [{"state": "NC", "amount": 3100.0}]                                  | verified   | (none)                  |
      | []                                                                       | []                                                                   | verified   | (none)                  |
      | [{"state": "VA", "amount": "999.00"}]                                    | []                                                                   | rejected   | box_17_state_income_tax |
      | [{"state": "PA", "amount": "3,100.00"}]                                  | []                                                                   | rejected   | box_17_state_income_tax |
      | ["junk", {"state": "NC", "amount": "3,100.00"}]                          | [{"state": "NC", "amount": 3100.0}]                                  | rejected   | box_17_state_income_tax |

  @parked
  Scenario: A 1099 other_boxes item turns every number-like part into a number, the box number too
    # current behaviour: box "5" comes back as 5.0 - parked 12 Nov 2026, see PARKING_LOT.md
    Given a text page reading "5 Investment expenses 40.00"
    And the model answers other_boxes = [{"box": "5", "label": "Investment expenses", "value": "40.00"}]
    When "klmn_1099-int.pdf" is extracted locally
    Then field other_boxes is [{"box": 5.0, "label": "Investment expenses", "value": 40.0}]
    And field other_boxes has confidence "verified"
