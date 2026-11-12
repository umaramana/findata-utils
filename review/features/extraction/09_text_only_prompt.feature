# PROPOSED (12 Nov 2026) - NEW obligations (Step 2). Red until Step 3 builds them.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Expected results are the agreed behaviour, not yet the code's. Ollama is a fake; names are invented.

Feature: Text-only prompt
  A page with a text layer is sent to the local model as its words, grouped into lines by
  height on the page, each line with its position. No page image is sent. Every word on the
  page is sent: there is no word cap.

  @keep
  Scenario Outline: Words are grouped into lines by height, each line with its position
    # why: the spike (12 Nov 2026) showed lines cost 4.4x fewer model tokens than word@(x,y) and ran 8x faster
    Given the page tokens "<tokens>"
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then the prompt shows the line "<line>"

    Examples:
      | tokens                                                   | line                                 |
      | Wages@40,100 1@20,100 75,000.00@90,100                   | y=100 x=20: 1 Wages 75,000.00        |
      | 1@20,100 Wages@40,102 75,000.00@90,103                   | y=100 x=20: 1 Wages 75,000.00        |
      | 1@20,100 Wages@40,100 2@20,104 Federal@40,104            | y=104 x=20: 2 Federal                |
      | Federal@40,140 2@20,140 Wages@40,100 1@20,100            | y=100 x=20: 1 Wages                  |

  @keep
  Scenario: A page with a text layer sends no page image
    # why: the model reads the text layer; rendering images made a page take about 7 minutes
    Given the pages "Form W-2 Copy B / Instructions for employee"
    And the model answers box_1_wages = null
    When "acme_w2.pdf" is extracted locally
    Then no page image is sent

  @keep
  Scenario Outline: A box value after word 150 is still sent and extracted
    # why: defect fix - real IRS form pages have 180 to 480 words and the old 150-word cap cut every one
    Given a text page of <words> words with "75,000.00" as word <position>
    And the model reads box_1_wages "75,000.00" from the prompt
    When "acme_w2.pdf" is extracted locally
    Then field box_1_wages is 75000.0
    And field box_1_wages has confidence "verified"
    And the prompt does not contain "truncated"

    Examples:
      | words | position |
      | 200   | 180      |
      | 480   | 470      |
