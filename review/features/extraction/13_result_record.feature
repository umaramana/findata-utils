# PROPOSED (13 Nov 2026) - pins CURRENT behaviour of review/extract.py (local path), added from the mutation run.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = known, left as is for now (PARKING_LOT.md)
# Ollama is a fake and the clock is a fake; names are invented (ACME, KLMN).

Feature: What the result records about the run
  Every result names the file it came from, the path that read it, and how long it took.
  run.py writes these into the JSON record; the Step 5 harness reports seconds per document.

  @keep
  Scenario: The result records the file, the path and the time taken
    # why: added 13 Nov 2026 (mutation run) - a wrong time misleads the model choice; a missing name breaks run.py
    Given a text page reading "1 Wages 75,000.00"
    And the model answers box_1_wages = "75,000.00"
    And the model call takes 2.5 seconds
    When "acme_w2.pdf" is extracted locally
    Then the extraction time is 2500 ms
    And the result names the source file "acme_w2.pdf" and the mode "local"
