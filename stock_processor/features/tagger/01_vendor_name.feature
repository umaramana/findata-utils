# PROPOSED (22 Oct 2026) - pins CURRENT behaviour of stock_processor/tagger_page.py.
# Marks: @keep = stays as is | @generic = make generic before tax-client use |
#        @client-data = move out of code into a per-client file | @parked = bookkeeping (Wave) only
# Every example below was run through the real code on 22 Oct and gave the result shown.

Feature: Vendor name from a bank description
  The tagger groups transactions by a vendor name cut out of the bank description.
  Only the vendor name (never the raw description) is sent to Claude.

  @keep
  Scenario Outline: Payment-method words, dates, phone numbers and refs are cut; location stays
    # why: the vendor + city is what the preparer and Claude need; the rest is noise or PII
    Given the bank description "<description>"
    When the vendor name is extracted
    Then the vendor is "<vendor>"

    Examples:
      | description                                                  | vendor                     |
      | Card Purchase 03/02 ACME HARDWARE CHARLOTTE NC 800-555-1234  | ACME HARDWARE CHARLOTTE NC |
      | ACME WIDGETS 12345678                                        | ACME WIDGETS               |
      | SQ *ACME COFFEE                                              | ACME COFFEE                |
      | TST* ACME DINER #054                                         | ACME DINER                 |

  @keep
  Scenario Outline: Payment rails keep the party, not the rail
    # why: ACH / Zelle / Amazon lines carry the real payee after a fixed prefix
    Given the bank description "<description>"
    When the vendor name is extracted
    Then the vendor is "<vendor>"

    Examples:
      | description                                    | vendor                  |
      | ACH: Klmn Insurance \| 123                     | Klmn Insurance          |
      | ORIG CO NAME:KLMN POWER ORIG ID:999 CO ENTRY   | KLMN POWER              |
      | AMAZON MKTPL*AB12CD Amzn.com/bill WA           | Amazon Amzn.com/bill WA |

  @generic
  Scenario: A Zelle line keeps short ref words in the vendor
    # current behaviour: only a trailing 8+ character code is cut, so "Ref 123 Conf" stays
    # and the same payee splits into one vendor per payment
    Given the bank description "Zelle Payment To ACME Supply Ref 123 Conf KLMN7788AB"
    When the vendor name is extracted
    Then the vendor is "Zelle: ACME Supply Ref 123 Conf"

  @keep
  Scenario Outline: Cash and transfer lines get one fixed name
    Given the bank description "<description>"
    When the vendor name is extracted
    Then the vendor is "<vendor>"

    Examples:
      | description                  | vendor          |
      | ATM WITHDRAWAL 123 MAIN ST   | ATM Withdrawal  |
      | Cash Withdrawal Branch       | ATM Withdrawal  |
      | Online Transfer to CHK 1234  | Online Transfer |
      | PAYMENT - THANK YOU          | PAYMENT         |

  @generic
  Scenario: Every check becomes the one vendor "Check"
    # current behaviour; item (b) = payee per check. The extractor's check register
    # (bankdetails_dataextraction/scripts/check_register.py) can already fill the payee.
    Given the bank descriptions "CHECK #1043" and "Check #1044"
    When the vendor names are extracted
    Then both vendors are "Check"

  @generic
  Scenario: Bank-specific card layouts are parsed inside the tagger
    # Capital One "- MERCHANT CITY, ST" and Citibank "#card | MERCHANT" layouts, and the
    # Citibank OCR code "OT Crpj" in front of a merchant, are hard-coded here. They came from
    # sample statements. For tax clients (any bank) this belongs in the extractor.
    Given the bank description "Card Purchase - ACME HARDWARE CHARLOTTE, NC"
    When the vendor name is extracted
    Then the vendor is "ACME HARDWARE CHARLOTTE NC"
    And the bank description "OT Crpj ACME FUEL" gives the vendor "ACME FUEL"

  @keep
  Scenario: A vendor name is at most 80 characters
    Given a bank description of 120 letters with no noise
    When the vendor name is extracted
    Then the vendor is its first 80 characters
