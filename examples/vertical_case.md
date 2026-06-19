# Vertical Example

## Scenario

- Use case: Sales KPI assistant app.
- Gold tables:
  - `sales.gold_orders`
  - `sales.gold_customers`
- Genie:
  - Reuse `sales_assistant`
  - Create `new_sales_genie` if missing

## End-to-end flow

1. `composer intake ...`
2. `composer plan`
3. `composer discover`
4. `composer propose-metadata`
5. `composer apply-metadata --approve --dry-run`
6. `composer generate-app`
7. `composer preflight`
8. `composer tag-report`
