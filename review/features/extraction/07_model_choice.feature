# PROPOSED (12 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path, extract_local).
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Every example below was run through the real code on 12 Nov 2026 and gave the result shown.
# Ollama is a fake (each scenario says what the model answers); the page text layer is faked as
# word tokens. Names are invented (ACME, KLMN).

Feature: Choosing the local model
  The model name is never hardcoded. It is read from what Ollama has installed;
  --local-model overrides that.

  @keep
  Scenario Outline: The installed model is used, or the one named with --local-model
    # why: the model on each machine differs; a hardcoded tag would 404 (decision 4(b), 12 Nov 2026)
    Given Ollama has the models "<installed>"
    And a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    When "acme_w2.pdf" is extracted locally with model "<override>"
    Then the model used is "<used>"

    Examples:
      | installed                    | override       | used           |
      | acme-text:1b                 | (none)         | acme-text:1b   |
      | acme-text:1b, klmn-vision:3b | klmn-vision:3b | klmn-vision:3b |
      | (none)                       | klmn-text:1b   | klmn-text:1b   |

  @keep
  Scenario Outline: No model, several models or no Ollama stops with a clear error
    # why: guessing between models would make results depend on install order
    Given Ollama has the models "<installed>"
    And a text page reading "1 Wages 75,000.00"
    When "acme_w2.pdf" is extracted locally
    Then extraction stops with a RuntimeError error saying "<message>"

    Examples:
      | installed                    | message                 |
      | (none)                       | No models found         |
      | acme-text:1b, klmn-vision:3b | Multiple local models   |
      | (Ollama not running)         | Could not reach Ollama  |
