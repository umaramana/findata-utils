# PROPOSED (12 Nov 2026) - NEW obligations (Step 2). Red until Step 3 builds them.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Expected results are the agreed behaviour, not yet the code's. Ollama is a fake; names are invented.

Feature: Context size and cut-short replies
  num_ctx is set on every call, sized from the prompt: half the prompt's characters (rounded
  up) plus an output budget of 1024 tokens, which is also num_predict. A page too long for the
  model is not sent. A reply the model cut short is a failure, never a result.

  @keep
  Scenario Outline: num_ctx is sized from the prompt
    # why: Ollama's default context silently cut real pages; the spike found about 2.3 characters per token
    Given a text page of <words> words with "75,000.00" as word 1
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then num_ctx is half the prompt's characters rounded up plus 1024
    And num_predict is 1024

    Examples:
      | words |
      | 20    |
      | 480   |

  @keep
  Scenario: A page too long for the model's context is not sent
    # why: Ollama answered "stop" with valid JSON even when the prompt overflowed num_ctx (spike, 12 Nov 2026)
    Given the model's context length is 1100 tokens
    And a text page of 480 words with "75,000.00" as word 1
    When "acme_w2.pdf" is extracted locally
    Then extraction stops with a ExtractionFailed error saying "too long for the model's context"
    And the model was not called

  @keep
  Scenario Outline: A reply cut short or overflowing the context is a failure
    # why: a cut-short reply can still parse as JSON with fields missing; that must not look like a blank box
    # added 13 Nov 2026 (mutation run): the last row fills the context only when prompt and output are added
    Given a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    And the model reply ends with done_reason "<done reason>" after <prompt> prompt tokens and <output> output tokens
    When "acme_w2.pdf" is extracted locally
    Then extraction stops with a ExtractionFailed error saying "<message>"

    Examples:
      | done reason | prompt | output | message                 |
      | length      | 300    | 1024   | cut short               |
      | stop        | 50000  | 90     | filled the context      |
      | stop        | 1000   | 900    | filled the context      |

  @keep
  Scenario: A normal reply within the context is a result
    # why: the checks above must not reject a good reply
    Given a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    And the model reply ends with done_reason "stop" after 300 prompt tokens and 90 output tokens
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is 75000.0

  @keep
  Scenario Outline: A model that does not report its context length is still used
    # why: added 13 Nov 2026 (mutation run) - older Ollama builds and some models leave it out; the size
    # check is skipped then, it must not crash
    Given Ollama reports <what> for the model
    And a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is 75000.0

    Examples:
      | what                                    |
      | no model_info                           |
      | model_info without a context length     |

  @keep
  Scenario: The model is asked for one JSON reply, not a stream
    # why: added 13 Nov 2026 (mutation run) - a streamed or prose reply cannot be parsed as one JSON object
    Given a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    When "acme_w2.pdf" is extracted locally
    Then the request asks for one JSON reply, not a stream
