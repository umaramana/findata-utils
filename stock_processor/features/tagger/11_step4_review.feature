# NEW 22 Oct 2026 - for review. Pins CURRENT behaviour. Marks: see 01_vendor_name.feature.

Feature: Step 4 - the preparer reviews what Claude flagged

  @keep
  Scenario: One review line per flagged vendor
    Given Claude flagged two "ACME FUEL" rows at confidence 0.40 and 0.60 and one "KLMN DELI" row
    And Claude tagged a "ZED MART" row without a flag
    When the review list is built
    Then it has one line for "ACME FUEL" and one for "KLMN DELI", and none for "ZED MART"
    And each line's preparer tag starts as Claude's suggestion
    And "ACME FUEL" shows confidence 0.50, the average of its rows

  @keep
  Scenario Outline: The preparer's answer goes on every row of that vendor
    Given Claude flagged two "ACME FUEL" rows
    When the preparer answers <answer> for "ACME FUEL"
    Then both rows are "<tag>" with source "<source>"
    And their confidence and reason are cleared

    Examples:
      | answer                    | tag                | source   |
      | "Meals"                   | Meals              | preparer |
      | "Review with Client"      | Review with Client | rwc      |
      | nothing (cell cleared)    | Review with Client | rwc      |
      | an empty text ""          | Review with Client | rwc      |
    # row 4: agreed 22 Oct - an empty text is the same as a cleared cell. Today the code leaves
    # the tag blank with source "preparer" - a defect, fixed under Rule 28 (fail first, then fix:).

  @keep
  Scenario: Rows Claude did not flag are left alone
    Given Claude tagged "ZED MART" as "Supplies" with confidence 0.90
    When the preparer finishes the review
    Then "ZED MART" is still "Supplies", source "claude", confidence 0.90

  @parked
  Scenario: A Wave category picked in review sets the tax tag
    Given the Wave mapping maps "Meals & Entertainment" to "Meals"
    When the preparer picks the Wave category "Meals & Entertainment" for flagged "ACME FUEL"
    Then its tag is "Meals"
