# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.
# Rules live in docs/auto_rules.csv (pattern, direction, wave_category, tag).

Feature: Who decides a vendor's tag, and the shared rules

  @keep
  Scenario: Order of deciders
    # lookup history > shared rule > Claude's pre-tag > blank (preparer or Claude in Step 4)
    Given vendor "ACME FUEL" is in the client lookup as "Fuel"
    And a shared rule would tag "ACME FUEL" as "Supplies"
    When the vendor table is built
    Then "ACME FUEL" is "Fuel" with source "Lookup"

  @keep
  Scenario: A preparer's change wins over any suggestion
    Given vendor "ACME FUEL" was suggested as "Fuel"
    When the preparer picks "Supplies"
    Then the tag is "Supplies" with source "preparer" and confidence 1.0

  @keep
  Scenario Outline: Shared rules on the vendor name
    Given the vendor "<vendor>" with direction <direction>
    When the shared rules are checked
    Then the tag is "<tag>"

    Examples:
      | vendor              | direction | tag                |
      | Online Transfer     | debit     | Contra / Transfer  |
      | PAYMENT - THANK YOU | credit    | Contra / Transfer  |
      | Returned Item       | credit    | Review with Client |
      | Wire Transfer       | debit     | (no rule)          |
      | ACME TRANSFER FEE   | debit     | (no rule)          |
    # why "Wire Transfer": a wire usually pays an outside party, so it is not a transfer
    # between the client's own accounts. A "transfer fee" is a fee, not a transfer.

  @generic
  Scenario: A bank fee rule names a Wave category, not a tax tag
    # current: the tax tag comes from the Wave mapping (Bank Service Charges -> Bank Service
    # Charges). For tax clients the rule should name the tax tag itself.
    Given the vendor "Monthly Fee" with direction debit
    When the shared rules are checked
    Then the Wave category is "Bank Service Charges" and the rule's own tag is blank

  @client-data
  Scenario: An ATM withdrawal is personal
    # current shared rule. For a tax client cash can be petty cash or owner draw; whether
    # ATM cash is personal is a per-client call (fits item (c), owner names / draws).
    Given the vendor "ATM Withdrawal" with direction debit
    When the shared rules are checked
    Then the tag is "Personal - Not Deductible"
    And an ATM credit gets no rule

  @client-data
  Scenario: Client rules in plain English go to Claude
    # already client data: lookups/{client_id}_rules.txt, one rule per line, # = comment
    Given the client has a rules file with the line "ACME cards are cost of goods"
    When Claude is asked about vendors not in the lookup
    Then the prompt lists that rule
    And tells Claude never to compute a split amount, but to use "Review with Client"
    And with no rules file the prompt is unchanged

  @keep
  Scenario Outline: The source shows who decided the tag
    # NEW 22 Oct - for review
    Given vendor "<vendor>" was suggested as "<suggested>" by <suggested_by>
    When the preparer leaves the tag as "<final>"
    Then the source is "<source>" with confidence <confidence>

    Examples:
      | vendor          | suggested         | suggested_by        | final             | source   | confidence |
      | ACME FUEL       | Fuel              | the lookup          | Fuel              | lookup   | 1.0        |
      | Online Transfer | Contra / Transfer | a shared rule       | Contra / Transfer | rule     | 1.0        |
      | ACME FUEL       | Fuel              | Claude at 0.80      | Fuel              | claude   | 0.80       |
      | ACME FUEL       | Fuel              | Claude at 0.80      | Supplies          | preparer | 1.0        |
    # why row 3: Claude's own confidence stays, so a low-confidence row the preparer only glanced at stays visible
