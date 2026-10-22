# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.
# The lookup is client data already: stock_processor/lookups/{client_id}_lookup.csv
# (vendor_name, tag, subcategory, source, date_tagged).

Feature: Client lookup history
  A vendor the client's lookup knows is tagged without Claude.

  Background:
    Given the client lookup has
      | vendor_name | tag      |
      | Acme        | Supplies |
      | Acme Fuel   | Fuel     |
      | KL          | Rents    |

  @keep
  Scenario Outline: Exact name, or a lookup name found inside the vendor as whole words
    # why: a hand-typed lookup says "Acme"; the bank prints "ACME FUEL 22 CHARLOTTE"
    When the lookup is asked about "<vendor>"
    Then the answer is <answer>

    Examples:
      | vendor                 | answer                                      |
      | Acme                   | Supplies                                    |
      | Acme Store             | Supplies                                    |
      | ACME FUEL 22 CHARLOTTE | Fuel (the longest name found wins)          |
      | ACMEX STORE            | no match (not a whole word)                 |
      | KL STORE               | no match (names under 3 letters are ignored)|

  @keep
  Scenario: Looser names are only hints for Claude, never a lookup tag
    # why: the user rejected loose matches as trusted tags ("overfitting"), 15 Oct
    Given the lookup has "Acme Club" as "Meals"
    When the vendor "ACMECLUB 1234" is tagged
    Then the lookup gives no tag
    And Claude gets "Acme Club = Meals" as similar history

  @keep
  Scenario: A contained name and a looser name disagree
    Given the lookup has "Acme" as "Supplies" and "Acme Supply Company" as "Repairs and Maintenance"
    When the vendor "ACME Supply Comp 77" is tagged
    Then the lookup gives no tag
    And Claude's answer is flagged for the preparer with the note "Lookup conflict"

  @keep
  Scenario: The lookup is written only when the preparer saves
    # why: unconfirmed rows were polluting the lookup (15 Oct)
    When a run finishes without "Save tags to lookup"
    Then the lookup file is unchanged

  @generic
  Scenario: Saving keeps unreviewed Claude tags too
    # current behaviour; item (e) = don't save unreviewed Claude rows
    Given a run where Claude tagged "ACME FUEL" above the confidence threshold
    And the preparer did not touch it
    When the preparer clicks "Save tags to lookup"
    Then "ACME FUEL" is saved with source "claude"
    And each vendor has one row, the newest one winning

  @keep
  Scenario: Unmatched contras are saved with their tag from before pairing
    Given "Online Transfer" was tagged "Contra / Transfer" and found no other side
    When the preparer saves tags to the lookup
    Then the lookup row says "Contra / Transfer", not "Review with Client"
