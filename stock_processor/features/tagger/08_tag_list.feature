# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.
# Tag list: docs/rasrich_tag_lists.csv (tag, line_reference), 69 tags.

Feature: The tax tag list

  @keep
  Scenario: Three tags the code relies on by name
    Then the tag list holds "Review with Client", "Contra / Transfer" and "Personal - Not Deductible"
    And any tag starting "Personal -" is treated as personal in the output

  @generic
  Scenario: One tag list for every entity type
    # current: the line references are Form 1120-S only (e.g. "Salaries and Wages to
    # Shareholders", income tags "FORM 1120S, PAGE 1"). Sole props file Schedule C and
    # partnerships Form 1065, whose lines differ. Entity type only reaches Claude's prompt.
    Given the entity type "Sole Prop / SMLLC"
    When the tag list is loaded
    Then it is the same list as for "S-Corp"

  @keep
  Scenario: The file's Lookup tab adds tags for this client
    Given the uploaded workbook has a tab named like "Lookup" with a "Category" column
    When the file is loaded
    Then its Category values are added to the tag dropdown and listed first to Claude
    And a Lookup tab without a Category column gives a warning, not an error
