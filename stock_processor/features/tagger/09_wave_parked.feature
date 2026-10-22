# PROPOSED (22 Oct 2026) - pins CURRENT behaviour. Marks: see 01_vendor_name.feature.
# Bookkeeping is parked (22 Oct). Pinned so a tax-client change does not break it by accident.
# Shared mapping: docs/wave_mapping.csv (wave_category, direction, tax_category).
# Client mapping (client data already): lookups/{client_id}_wave_mapping.csv, overrides shared rows.

Feature: Wave category sets the tax tag (bookkeeping, parked)

  @parked
  Scenario Outline: The Wave category decides the tag, by row direction
    Given the Wave category "<wave>" on a <direction> row
    When tags are applied
    Then the tax tag is "<tag>"

    Examples:
      | wave                        | direction | tag                       |
      | Owner Investment / Drawings | debit     | Personal - Not Deductible |
      | Owner Investment / Drawings | credit    | Contra / Transfer         |
      | Bank Service Charges        | debit     | Bank Service Charges      |

  @parked
  Scenario Outline: A lookup row with a tag but no Wave category
    Given a lookup row tagged "<tag>" with no Wave category
    When the lookup is loaded
    Then <result>

    Examples:
      | tag                     | result                                                     |
      | Interest Expense        | its Wave category is "Interest Expense" (the only one)      |
      | Waste Removal           | its Wave category is "Waste Removal" (none mapped: own name)|
      | Repairs and Maintenance | it is flagged with the choices listed (2 Wave categories)   |
      | Review with Client      | it stays blank and is not flagged                          |

  @parked
  Scenario: New Wave categories are saved to the client mapping at Step 5
    # current: this runs every time Step 5 shows, with no button (unlike the lookup save)
    Given the output uses a Wave category the mapping does not know, tagged "Supplies"
    When Step 5 is shown
    Then it is added to the client's Wave mapping with direction "any" and its most common tag

  # 22 Oct (user: pick the closest tax category): "Payroll – Employee Benefits" now maps to
  # "Employee Benefit Programs" (Line 18), was "Salaries and Wages to Non-Shareholders".
