# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Reading the model's reply
  The reply must be JSON with "form_type" and "fields". The small local model often bends
  the shape; the known variants are accepted. Anything else stops the extraction.

  @keep
  Scenario Outline: Known reply shapes give the same field
    # why: qwen2.5vl:3b was seen returning each of these shapes (15 Sep 2026)
    Given a text page reading "1 Wages 75,000.00"
    And the model replies <reply>
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is 75000.0

    Examples:
      | reply                                                                                    |
      | {"form_type": "W-2", "fields": {"box_1_wages": "75,000.00"}}                             |
      | ```json {"form_type": "W-2", "fields": {"box_1_wages": "75,000.00"}} ```                 |
      | {"form_type": "W-2", "fields": [{"field_name": "box_1_wages", "value": "75,000.00"}]}    |
      | {"form_type": "W-2", "fields": [{"box_1_wages": "75,000.00"}]}                           |

  @keep
  Scenario: A reply item that names a field but gives no value leaves that field missing
    # why: added 16 Nov 2026 (W-2 diagnosis) - qwen2.5vl:3b replied with field names and no values on 3/3 runs,
    # and the item's own key became a field literally called "field_name"
    Given a text page reading "1 Wages 75,000.00 2 Federal income tax withheld 12,000.00"
    And the model replies {"form_type": "W-2", "fields": [{"field_name": "box_1_wages"}, {"field_name": "box_2_federal_withheld"}]}
    When "acme_w2.pdf" is extracted locally
    Then the result has no field named "field_name"
    And the verification failures are "(none)"
    And the missing required fields are "box_1_wages, box_2_federal_withheld"

  @keep
  Scenario Outline: The form type comes from the model if it names a known form, else from the filename
    # why: the model sometimes echoes the whole choice list back instead of picking one
    Given a text page reading "Form 1099-INT"
    And the model replies {"form_type": "<model says>", "fields": {}}
    When "<file>" is extracted locally
    Then the form type is "<form type>"

    Examples:
      | file               | model says                    | form type |
      | acme_w2.pdf        | W-2 \| 1099-INT \| 1099-DIV   | W-2       |
      | acme_statement.pdf | 1099-INT                      | 1099-INT  |
      | acme_statement.pdf | W-2 \| 1099-INT \| 1099-DIV   | UNKNOWN   |
      | acme_w2.pdf        | 1099-DIV                      | 1099-DIV  |

  @keep
  Scenario Outline: A reply that is not usable JSON stops the extraction with an error
    # why: never turn a broken reply into empty fields
    # changed 12 Nov 2026 (Step 2): every unusable reply is an ExtractionFailed, which run.py reports as FAIL
    Given a text page reading "1 Wages 75,000.00"
    And the model replies <reply>
    When "acme_w2.pdf" is extracted locally
    Then extraction stops with a <error> error saying "<message>"

    Examples:
      | reply                                         | error            | message                    |
      | {"fields": {"box_1_wages": "75,000.00"}}      | ExtractionFailed | missing form_type/fields   |
      | {"form_type": "W-2", "fields": {"box_1_wa     | ExtractionFailed | not valid JSON             |
