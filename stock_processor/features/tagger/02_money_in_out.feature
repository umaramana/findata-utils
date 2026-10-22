# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.

Feature: Money in or money out
  Each row is a debit (money out) or a credit (money in). Tags, rules and the summary use it.

  @keep
  Scenario Outline: Direction from the amount
    Given an amount column holding <amounts>
    When the directions are read
    Then the directions are <directions>

    Examples:
      | amounts       | directions                 |
      | -10, 20, x    | debit, credit, (none)      |
      | 10, 20        | debit, debit               |
    # why row 2: a column with no negative numbers (e.g. "Subtracted") is debit-only

  @keep
  Scenario: Separate Debit and Credit columns become one signed amount
    Given a row with Debit 25.00 and a blank Credit
    And a row with a blank Debit and Credit 40.00
    When the files are combined
    Then the signed amounts are -25.00 and 40.00

  @keep
  Scenario: A credit card file is sign-flipped to match checking
    # why: on a card statement a charge is positive; in checking money out is negative
    Given a file marked as a credit card statement with a charge of 30.00
    When the files are combined
    Then that charge is -30.00

  @keep
  Scenario: A row with no readable amount is not tagged
    Given a row whose amount is "n/a"
    When tags are applied
    Then its source is "skipped"
    And the summary shows it only as a count on "Not Tagged (no amount)"

  @keep
  Scenario: A file without a Filename column gets its upload name
    # why: contra pairing uses Filename to tell the accounts apart
    Given an uploaded file "checking.xlsx" with no Filename column
    When the files are combined
    Then every row from it has Filename "checking.xlsx"

  @keep
  Scenario: The Reconciliation block of a collated Master sheet is dropped
    Given a Master sheet whose first column has a "Reconciliation" line after the transactions
    When the file is loaded
    Then only the rows above that line are kept
