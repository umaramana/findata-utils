# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.

Feature: Transfers between the client's own accounts (contras)
  A contra must have its other side in another of the client's accounts.

  @keep
  Scenario: Pairing by amount, sign, file and date
    # rows tagged "Contra / Transfer", oldest first, each paired at most once
    Given these contra rows
      | date       | amount  | file |
      | 2026-01-02 | -100.00 | chk  |
      | 2026-01-03 |  100.00 | card |
      | 2026-01-02 |  -50.00 | chk  |
      | 2026-01-10 |   50.00 | sav  |
    When contras are paired
    Then the two 100.00 rows share pair number 1
    And the two 50.00 rows are "Review with Client" with reason "Contra with no matching other side"
    # why: 8 days apart is more than 3 (3 covers a weekend)

  @keep
  Scenario: Both sides in the same file do not pair
    Given a -20.00 and a 20.00 contra on the same day in the same file
    When contras are paired
    Then neither is paired

  @keep
  Scenario: Unpaired contras are flagged, never chased
    # user scope rule, 15 Oct: missing accounts, Dec rows on Jan statements and split
    # transfers are not investigated; the accounts given are the scope
    Given a contra with no other side
    When contras are paired
    Then it goes to Review with Client and nothing else is tried

  # Not built: pairing by a shared reference number. See README.md "Ref no for contras".
