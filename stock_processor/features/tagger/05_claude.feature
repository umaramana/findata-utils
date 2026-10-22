# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.

Feature: Claude tags the vendors nobody else did

  @keep
  Scenario: Only untagged vendors go to Claude, 30 per call
    Given 65 vendors with no tag after the lookup, the rules and the preparer
    When Claude is run
    Then 3 calls are made with 30, 30 and 5 vendors

  @keep
  Scenario: What Claude is sent about each vendor
    # why: no raw description, no account numbers, no client name
    When a vendor is sent to Claude
    Then its item holds only: id, vendor, amount_total, txn_count, amount_sample, date_span, and similar_history when there is one
    And amount_total is negative for money out and positive for money in

  @keep
  Scenario Outline: The amount sample and date span Claude sees
    # NEW 22 Oct - for review
    Given vendor "ACME FUEL" has money-out rows of <amounts> dated <dates>
    When a vendor is sent to Claude
    Then its amount_sample is "<sample>" and its date_span is "<span>"

    Examples:
      | amounts      | dates                  | sample        | span              |
      | 5.00         | 01/15/2026             | -5.0          | Jan 2026          |
      | 5.00, 80.00  | 01/15/2026, 03/02/2026 | -80.0 to -5.0 | Jan 2026-Mar 2026 |
      | 80.00, 5.00  | 02/03/2026, 12/20/2025 | -80.0 to -5.0 | Dec 2025-Feb 2026 |

  @keep
  Scenario: What Claude is told about the client
    Given the client is an "S-Corp" whose primary activity is "liquor store"
    When the prompt is built
    Then it names the entity type and the activity
    And it lists every tag, the file's Lookup-tab tags first
    And Claude must pick "tag" from that list only

  @keep
  Scenario Outline: Claude's answer becomes a source
    Given the confidence threshold is 75%
    When Claude answers with confidence <confidence><extra>
    Then the row's source is "<source>"

    Examples:
      | confidence | extra                                   | source  |
      | 0.90       |                                         | claude  |
      | 0.60       |                                         | flagged |
      | 0.90       | and a Wave category not in the mapping  | flagged |
      | 0.90       | for a vendor with a lookup conflict     | flagged |

  @keep
  Scenario: A failed call sends its whole batch to review
    When a Claude call fails
    Then every vendor in that batch is "Review with Client" with confidence 0
    And the reason starts with "API error"

  @keep
  Scenario: A vendor Claude left out of its answer
    When Claude's answer has no item for "ACME FUEL"
    Then "ACME FUEL" is "Review with Client", confidence 0, source "flagged"

  @generic
  Scenario: The prompt talks about Wave categories
    # current: "subcategory" is described as the Wave category and Claude may propose new
    # Wave names. For tax clients with no accounting software this should not be the frame.
    When the prompt is built with a Wave category list
    Then it asks for a Wave category in "subcategory"

  @keep
  Scenario: Two run modes
    # Review-first: the preparer tags first, Claude does the rest in Step 4.
    # Pre-tag: Claude tags every non-lookup vendor in Step 2; the preparer reviews in Step 3,
    # where new-Wave-category and lookup-conflict vendors count as still needing attention.
    Given pre-tag mode
    When the file is uploaded
    Then Claude is asked about every vendor the lookup does not know
