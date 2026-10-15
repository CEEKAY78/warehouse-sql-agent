# Business glossary

Definitions the agent retrieves before writing SQL. The gold SQL of the evaluation set uses
exactly these definitions.

## Net revenue
Net revenue = `sum(line_amount)` over all rows of `fact_sales`, cancellation lines included
(their amounts are negative, so cancellations are already subtracted). Amounts are in GBP.
Round money to 2 decimals: `round(sum(line_amount), 2)`.

## Gross sales
Gross sales = `sum(line_amount)` over lines with `NOT is_cancelled` (before cancellations).

## Order
An order is one invoice: `count(DISTINCT invoice_no)` over lines with `NOT is_cancelled`.
Cancellation invoices start with "C" and are not orders.

## Average order value
Average order value (AOV) = gross sales / number of orders, both over `NOT is_cancelled` lines,
rounded to 2 decimals.

## Units sold
Units sold = `sum(quantity)` over lines with `NOT is_cancelled`.

## Cancellations
A cancellation is an invoice whose number starts with "C" (`is_cancelled = true`). The value of
cancellations is `sum(line_amount)` over those lines and is negative. The cancellation rate is
the number of cancellation invoices divided by the number of orders.

## Registered and guest customers
Registered customers have a customer id. Guest checkouts have no id and all point to one row
of `dim_customer` with `customer_id = 'UNKNOWN'`, `is_guest = true`, `customer_key = 0`.
"Customers" means registered customers unless the question says otherwise: filter
`NOT is_guest` (or `customer_key <> 0`).

## New customer
A new customer in a period is a registered customer whose first order (first `NOT is_cancelled`
line) falls in that period.

## Product
A product is a stock code (`dim_product.stock_code`). Some descriptions are shared by more than
one stock code; when the question names a product by its description, include every stock code
with that description.

## Country
The country is the customer's country recorded on the invoice (`dim_country.country_name`).
"United Kingdom" is the home market; "EIRE" is Ireland.

## Today and relative periods
The data covers 2009-12-01 to 2011-12-09. "Today" means the last invoice date in the data,
`(SELECT max(date) FROM fact_sales JOIN dim_date USING (date_key))` = 2011-12-09. "The last 30
days" are the 30 calendar days ending on that date, both ends included. December 2011 is a
partial month.

## Calendar
Use `dim_date` for year, quarter, month (1-12), month_name, iso_week, day_name and is_weekend.
Join it with `fact_sales.date_key`. The shop is closed on Saturdays (almost no orders).

## Growth and percentages
Growth from A to B in percent = `round(100 * (B / A - 1), 1)`. Shares in percent =
`round(100 * part / total, 1)`. Unless the question says otherwise, report percentages with one
decimal.

## Data that does not exist
The warehouse has no costs, margins, profit, stock levels, suppliers, marketing spend, web
traffic, delivery times, salespeople, return reasons, customer demographics (age, gender) or
ratings, and no data outside 2009-12-01 - 2011-12-09. Questions that need any of these cannot
be answered and must be refused.
