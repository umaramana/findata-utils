# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.

Feature: The tagged workbook

  @keep
  Scenario: Sheets
    When the output is written
    Then it has sheets "Tagged", "Personal", "Review with Client" and, when there are tags, "Summary"
    And "Review with Client" rows are not on "Tagged"
    And "Personal - ..." rows are on both "Personal" and "Tagged"

  @keep
  Scenario: Summary sections
    When the summary is built
    Then "Contra / Transfer" rows are in "Contra / Transfers"
    And tags starting "Personal -" are in "Personal"
    And other money in is in "Income" and other money out in "Expenses"
    And each section has a TOTAL row
    And a "NET (Income − Expenses)" row adds the signed Income and Expenses amounts

  @keep
  Scenario: Summary rows and month columns
    Given rows dated Dec 2025 to Feb 2026
    When the summary is built
    Then there is one row per tag and subcategory, plus a SUBTOTAL when a tag has 2+ subcategories
    And the month columns are "Dec 2025", "Jan 2026", "Feb 2026" in date order, then Total

  @parked
  Scenario: Column names follow Wave
    # current: Subcategory is shown as "Wave Category", Tag as "Tax Tag"
    When the output is written
    Then "Wave Category" sits just left of "Tax Tag" and Filename is the last column
