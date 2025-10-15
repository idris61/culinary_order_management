# Culinary Order Management – Agreement → Price List Sync

This document describes how Agreements are converted into customer price lists and how item prices are maintained.

## Key Behaviour

- Each Agreement is a separate document; all prices end up in a single customer price list.
  - Price List name: `<Customer Name>` (e.g. `A Müşterisi`).
- Agreement Item columns in use:
  - Item, Item Name, Item Group, Kitchen Item, Default UOM, Standard Selling Rate, Agreement Price, Currency
- Writing prices (upsert):
  - If Agreement Price is set, it is used.
  - Otherwise, Agreement Discount Rate is applied over Standard Selling Rate.
  - Natural unique key: (Price List, Item, Currency, Valid From, Valid Upto)
  - Before insert/update, any rows that overlap the new date range for the same item in the same price list are removed (overlap‑clean).
- Deleting/cleanup:
  - When an Agreement is deleted, all Item Price rows in the customer’s price list that overlap that Agreement’s date range are removed.
- Duplicate prevention:
  - Changing dates and saving keeps a single row per item; older overlapping rows are auto‑cleaned.
- Reference field:
  - Item Price `reference` is NOT used (left empty).
- Supplier filter:
  - Agreement Item → Item query is filtered by the selected Supplier.

## Developer Notes

- Helpers
  - `_find_existing_item_price(price_list, item_code, currency, valid_from, valid_upto)` – finds an existing Item Price using natural key, handling NULL dates.
  - `_delete_overlapping_item_prices(price_list, item_code, new_from, new_upto)` – deletes overlapping rows for the same item/key.
- Hooks
  - `create_price_list_for_agreement` – ensures customer price list exists and triggers sync.
  - `sync_item_prices` – writes item prices (upsert + overlap clean).
  - `cleanup_item_prices` – removes prices on Agreement delete.

## i18n

- Labels are in English; Turkish translations live in `translations/tr.csv`.

## How to test

1. Create Agreement with items and save → one Item Price per row in `<Customer>` list.
2. Change dates and save → still one row per item; earlier overlapping rows removed.
3. Delete Agreement → related rows in `<Customer>` list removed.

## Notes

- Price List name is based solely on Customer name to keep a single list per customer.
- No writes are made to Item Price `reference` to avoid ambiguous reporting.