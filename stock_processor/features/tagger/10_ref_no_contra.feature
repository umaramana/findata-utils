# APPROVED (22 Oct 2026) and built - tests in stock_processor/test_tagger.py ("Contra pairing by ref no").
# Ask from the user: both sides of a transfer between the client's own accounts carry the same
# ref no. The extractor already keeps it in Description; contra pairing reads it from there.
# No new column. Vendor unchanged. Cards are out of scope for now.

Feature: Pair transfers by their ref no

  Scenario Outline: The ref no is read from a TO/FROM description at pairing time
    Given the description "<description>"
    When contras are paired
    Then the ref no used is "<ref>"

    Examples:
      | description                                    | ref                 |
      | EB to Savings # 0321568960 Ref# 000000 0001028 | 000000 0001028      |
      | Transfer From Savings Ref# 000000 0001065      | 000000 0001065      |
      | ACME Supply Ref# 000000 0001099                | (none: no TO/FROM)  |
      | Transfer From Savings                          | (none: no ref)      |

  Scenario: Same ref no pairs first, with no day limit
    Given these contra rows
      | date       | amount  | file | description                          |
      | 2026-01-02 | -500.00 | chk  | EB to Savings Ref# 000000 0001028    |
      | 2026-01-09 |  500.00 | sav  | EB From Checking Ref# 000000 0001028 |
    When contras are paired
    Then the two rows share a pair number

  Scenario: Same ref no in the same file does not pair (different-file rule kept, user 22 Oct)
    Given a -500.00 and a 500.00 row in the same file, both with ref "000000 0001028"
    When contras are paired
    Then they are not paired

  Scenario: A ref no match still needs the same amount, opposite sign and another file
    Given a -500.00 row and a 400.00 row, both with ref "000000 0001028"
    When contras are paired
    Then they are not paired by ref no

  Scenario: Rows with no ref no, or no partner by ref no, pair as today
    Given a contra row with no ref no in its description
    When contras are paired
    Then it uses today's rule: same amount, opposite sign, another file, within 3 days

  Scenario: The vendor name and the output are unchanged
    When the run finishes
    Then Vendor and Description are the same as before this change
    And the only difference is which rows share a Contra Pair number

  Scenario: Card payments are not changed
    Given a contra row from a credit card statement
    When contras are paired
    Then it pairs by today's rule only
