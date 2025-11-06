"""
Culinary Order Management - Agreement Integration (price lists & item prices)
"""

import frappe
from frappe import msgprint, _
from frappe.exceptions import ValidationError, DoesNotExistError
from typing import Optional
import traceback


def _handle_agreement_error(
	error: Exception, 
	context: str, 
	doc_name: Optional[str] = None,
	show_user_message: bool = True,
	reraise: bool = True
) -> None:
	"""Handle Agreement operation errors with logging and user messages.
	
	Args:
		error: Exception to handle
		context: Error context (e.g. "Price List Creation")
		doc_name: Agreement document name (optional)
		show_user_message: Show message to user
		reraise: Re-raise exception for rollback
	"""
	error_title = f"Agreement {context} Error"
	error_details = f"Context: {context}\n"
	
	if doc_name:
		error_details += f"Agreement: {doc_name}\n"
	
	error_details += f"Error Type: {type(error).__name__}\n"
	error_details += f"Error Message: {str(error)}\n"
	error_details += f"Traceback:\n{traceback.format_exc()}"
	
	frappe.log_error(message=error_details, title=error_title)
	
	if show_user_message:
		user_msg = _("Error: {0}").format(str(error))
		
		if isinstance(error, frappe.exceptions.LinkValidationError):
			user_msg = _("Invalid reference: {0}").format(str(error))
		elif isinstance(error, frappe.exceptions.MandatoryError):
			user_msg = _("Mandatory field missing: {0}").format(str(error))
		elif isinstance(error, frappe.exceptions.DuplicateEntryError):
			user_msg = _("Record already exists: {0}").format(str(error))
		elif isinstance(error, DoesNotExistError):
			user_msg = _("Record not found: {0}").format(str(error))
		elif isinstance(error, ValidationError):
			user_msg = _("Validation error: {0}").format(str(error))
		
		msgprint(f"❌ {user_msg}", alert=True, indicator="red")
	
	if reraise:
		raise


def _get_standard_selling_rate(item_code: str, currency: str) -> float:
	"""Get unit price from 'Standard Selling' price list or nearest selling price."""
	rate = frappe.db.get_value(
		"Item Price",
		{"price_list": "Standard Selling", "item_code": item_code, "currency": currency},
		"price_list_rate",
	)
	if rate:
		return float(rate)
	
	row = frappe.db.sql(
		"""
		select price_list_rate from `tabItem Price`
		where item_code=%s and selling=1
		  and (currency=%s or %s is null)
		order by (valid_from is null), valid_from desc, modified desc
		limit 1
		""",
		(item_code, currency, currency),
		as_dict=True,
	)
	if row:
		return float(row[0].price_list_rate)
	return 0.0


def _find_existing_item_price(price_list: str, item_code: str, currency: str, valid_from, valid_upto, agreement_name: str = None):
	"""Find existing Item Price by natural unique keys, handling NULL dates properly.
	
	Agreement name kullanarak aynı anlaşmaya ait fiyatı bulur.
	"""
	query = """
		SELECT name 
		FROM `tabItem Price`
		WHERE price_list = %s
		  AND item_code = %s
		  AND currency = %s
		  AND (
		      (valid_from IS NULL AND %s IS NULL) OR (valid_from = %s)
		  )
		  AND (
		      (valid_upto IS NULL AND %s IS NULL) OR (valid_upto = %s)
		  )
	"""
	params = [price_list, item_code, currency, valid_from, valid_from, valid_upto, valid_upto]
	
	# Agreement referansı varsa onu da filtrele
	if agreement_name:
		query += " AND (note = %s OR note LIKE %s)"
		params.extend([agreement_name, f"%{agreement_name}%"])
	
	result = frappe.db.sql(query, tuple(params), as_dict=False)
	return [row[0] for row in result] if result else []


def _delete_overlapping_item_prices(price_list: str, item_code: str, new_from, new_upto, agreement_name: str = None) -> int:
	"""Delete Item Price rows in same price list and item that overlap with given date range.

	If dates are null, treat as open-ended.
	Uses SQL to find overlapping records, then ORM to delete (triggers hooks).
	Agreement name kullanarak sadece aynı anlaşmaya ait fiyatları siler.
	
	Args:
		price_list: Price list name
		item_code: Item code
		new_from: New start date (can be None)
		new_upto: New end date (can be None)
		agreement_name: Agreement name (sadece bu anlaşmaya ait fiyatları sil)
		
	Returns:
		Number of deleted records
		
	Raises:
		ValidationError: Critical deletion error
	"""
	if not price_list or not item_code:
		frappe.log_error(
			message=f"Invalid parameters: price_list={price_list}, item_code={item_code}",
			title="Item Price Cleanup - Invalid Parameters"
		)
		return 0
	
	try:
		# Build SQL query for overlap detection
		conditions = ["price_list = %s", "item_code = %s"]
		values = [price_list, item_code]
		
		# Agreement filtresi - sadece aynı anlaşmaya ait fiyatları sil
		if agreement_name:
			conditions.append("(note = %s OR note LIKE %s)")
			values.extend([agreement_name, f"%{agreement_name}%"])
		
		# Overlap logic
		if new_from and new_upto:
			# New range: [new_from, new_upto]
			# Overlap if: (existing_from <= new_upto) AND (existing_upto >= new_from)
			conditions.append("(IFNULL(valid_from, '0001-01-01') <= %s)")
			values.append(new_upto)
			conditions.append("(IFNULL(valid_upto, '9999-12-31') >= %s)")
			values.append(new_from)
		elif new_from:
			# Only start date (open end)
			conditions.append("(IFNULL(valid_upto, '9999-12-31') >= %s)")
			values.append(new_from)
		elif new_upto:
			# Only end date (open start)
			conditions.append("(IFNULL(valid_from, '0001-01-01') <= %s)")
			values.append(new_upto)
		
		query = f"""
			SELECT name 
			FROM `tabItem Price`
			WHERE {' AND '.join(conditions)}
		"""
		
		overlapping_prices = frappe.db.sql(query, tuple(values), as_dict=False)
		
		if not overlapping_prices:
			return 0
		
		price_names = [row[0] for row in overlapping_prices]
		deleted_count = 0
		failed_deletions = []
		
		for price_name in price_names:
			try:
				frappe.delete_doc("Item Price", price_name, ignore_permissions=True, force=True)
				deleted_count += 1
				
			except frappe.exceptions.LinkExistsError as e:
				failed_deletions.append((price_name, "Link exists", str(e)))
				frappe.log_error(
					message=f"Cannot delete Item Price '{price_name}' (linked): {str(e)}",
					title="Item Price Cleanup - Link Exists"
				)
				
			except frappe.exceptions.PermissionError as e:
				failed_deletions.append((price_name, "Permission denied", str(e)))
				frappe.log_error(
					message=f"No permission to delete Item Price '{price_name}': {str(e)}",
					title="Item Price Cleanup - Permission Error"
				)
				
			except DoesNotExistError as e:
				frappe.log_error(
					message=f"Item Price '{price_name}' already deleted: {str(e)}",
					title="Item Price Cleanup - Already Deleted"
				)
				
			except Exception as e:
				failed_deletions.append((price_name, "Unknown error", str(e)))
				frappe.log_error(
					message=f"Error deleting Item Price '{price_name}': {str(e)}\n{traceback.format_exc()}",
					title="Item Price Cleanup - Unknown Error"
				)
		
		if failed_deletions:
			error_msg = f"{len(failed_deletions)} records could not be deleted:\n"
			for name, reason, details in failed_deletions[:5]:
				error_msg += f"  - {name}: {reason}\n"
			
			if len(failed_deletions) > 5:
				error_msg += f"  ... and {len(failed_deletions) - 5} more\n"
			
			if deleted_count == 0:
				frappe.throw(error_msg, ValidationError)
			
		return deleted_count
		
	except frappe.exceptions.QueryTimeoutError as e:
		error_msg = f"Database query timeout: {str(e)}"
		frappe.log_error(
			message=f"{error_msg}\nQuery conditions: {conditions}",
			title="Item Price Cleanup - Query Timeout"
		)
		frappe.throw(error_msg, ValidationError)
		
	except Exception as e:
		error_msg = f"Item Price cleanup failed: {str(e)}"
		frappe.log_error(
			message=f"{error_msg}\n{traceback.format_exc()}",
			title="Item Price Cleanup - Unexpected Error"
		)
		frappe.throw(error_msg, ValidationError)


@frappe.whitelist()
def get_supplier_items_with_standard_prices(supplier: str, currency: str | None = None):
	"""Get all active items for selected supplier with standard selling prices.

	Returns: [{"item_code", "item_name", "uom", "standard_selling_rate", "price_list_rate", "currency"}]
	price_list_rate is initialized with standard_selling_rate.
	
	Requires: Item and Supplier read permission
	"""
	if not frappe.has_permission("Item", "read"):
		frappe.throw(_("You don't have permission to read Item"), frappe.PermissionError)
	
	if not frappe.has_permission("Supplier", "read"):
		frappe.throw(_("You don't have permission to read Supplier"), frappe.PermissionError)
	
	if not supplier:
		return []

	items = frappe.db.sql(
		"""
		select i.name as item_code, i.item_name, i.item_group,
		       i.is_kitchen_item as kitchen_item,
		       i.stock_uom as uom
		from `tabItem` i
		join `tabItem Supplier` s on s.parent = i.name and s.supplier = %s
		where i.disabled = 0 and i.is_sales_item = 1
		order by i.item_name
		""",
		supplier,
		as_dict=True,
	)

	if not items:
		return []

	if not currency:
		supplier_currency = frappe.db.get_value("Supplier", supplier, "default_currency")
		if not supplier_currency:
			company_currency = frappe.db.get_value("Company", {"is_group": 0}, "default_currency")
			currency = company_currency or "EUR"
		else:
			currency = supplier_currency

	item_codes = [it.item_code for it in items]
	placeholders = ",".join(["%s"] * len(item_codes))
	price_rows = []
	if item_codes:
		price_rows = frappe.db.sql(
			f"""
			select item_code, price_list_rate
			from `tabItem Price`
			where price_list = 'Standard Selling' and selling = 1
			  and currency = %s and item_code in ({placeholders})
			""",
			[currency, *item_codes],
			as_dict=True,
		)

	price_map = {r.item_code: float(r.price_list_rate) for r in price_rows}

	result = []
	for it in items:
		std_rate = price_map.get(it.item_code, 0.0)
		if not std_rate:
			std_rate = _get_standard_selling_rate(it.item_code, currency)
		result.append(
			{
				"item_code": it.item_code,
				"item_name": it.item_name,
				"item_group": it.item_group,
				"kitchen_item": int(it.kitchen_item or 0),
				"uom": it.uom,
				"standard_selling_rate": std_rate,
				"price_list_rate": std_rate,
				"currency": currency,
			}
		)

	return result


def create_price_list_for_agreement(doc, method):
	"""Create/update price list when Agreement is created/updated.
	
	Each agreement item can have its own currency.
	Manual commits removed (uses Frappe's automatic transaction management).
	
	Raises:
		ValidationError: Price list creation failed or invalid data
	"""
	if not doc.customer:
		error_msg = _("Customer field is empty, cannot create price list")
		frappe.log_error(
			message=error_msg,
			title="Agreement Price List - Missing Customer"
		)
		msgprint(f"❌ {error_msg}", indicator="red", alert=True)
		frappe.throw(error_msg, ValidationError)
		
	try:
		price_list_created = False
		currencies_used = set()
		for item in doc.agreement_items:
			if item.currency:
				currencies_used.add(item.currency)
		
		if not currencies_used:
			try:
				company_currency = frappe.db.get_value("Company", {"is_group": 0}, "default_currency")
				if not company_currency:
					frappe.log_error(
						message="No default currency found for company",
						title="Agreement Price List - Missing Currency"
					)
					company_currency = "EUR"
				currencies_used.add(company_currency)
			except DoesNotExistError:
				frappe.throw(_("Company not found, cannot determine default currency"), ValidationError)
		
		for currency in currencies_used:
			price_list_name = f"{doc.customer}"
			
			# Müşterinin herhangi bir aktif anlaşması var mı kontrol et
			active_count = frappe.db.count("Agreement", {
				"customer": doc.customer,
				"docstatus": 1,
				"status": "Active"
			})
			should_enable = 1 if active_count > 0 else 0
			
			try:
				if not frappe.db.exists("Price List", price_list_name):
					price_list = frappe.new_doc("Price List")
					price_list.price_list_name = price_list_name
					price_list.enabled = should_enable
					price_list.selling = 1
					price_list.currency = currency
					price_list.insert(ignore_permissions=True)
					price_list_created = True
					if should_enable:
						msgprint(_("✅ Price List '{0}' created and activated ({1})").format(price_list_name, currency), indicator="green")
					else:
						msgprint(_("✅ Price List '{0}' created (will be activated when agreement becomes active)").format(price_list_name), indicator="blue")
				else:
					price_list = frappe.get_doc("Price List", price_list_name)
					price_list_created = True
					# Müşterinin aktif anlaşma durumuna göre price list'i aktive/deaktive et
					if price_list.enabled != should_enable:
						price_list.enabled = should_enable
						price_list.save(ignore_permissions=True)
						if should_enable:
							msgprint(_("✅ Price List '{0}' activated").format(price_list_name), indicator="green")
						else:
							msgprint(_("ℹ️ Price List '{0}' deactivated (no active agreements)").format(price_list_name), indicator="orange")
					else:
						msgprint(_("✅ Price List '{0}' already exists").format(price_list_name), indicator="blue")
						
			except frappe.exceptions.DuplicateEntryError as e:
				if frappe.db.exists("Price List", price_list_name):
					frappe.log_error(
						message=f"Price list '{price_list_name}' already exists (race condition)",
						title="Agreement Price List - Duplicate Entry"
					)
					continue
				else:
					frappe.throw(_("Price List creation failed (duplicate): {0}").format(str(e)), ValidationError)
					
			except frappe.exceptions.MandatoryError as e:
				frappe.throw(_("Mandatory field missing (Price List): {0}").format(str(e)), ValidationError)
				
			except ValidationError as e:
				frappe.throw(_("Price List validation error: {0}").format(str(e)), ValidationError)

		# Price List başarıyla oluşturuldu mu kontrol et
		if not price_list_created:
			error_msg = _("Failed to create or verify Price List for customer '{0}'").format(doc.customer)
			frappe.log_error(
				message=error_msg,
				title="Agreement Price List - Creation Failed"
			)
			msgprint(f"❌ {error_msg}", indicator="red", alert=True)
			frappe.throw(error_msg, ValidationError)
		
		try:
			doc.price_list = f"{doc.customer}"
			doc.db_set("price_list", doc.price_list, update_modified=False)
		except Exception as e:
			frappe.throw(_("Could not link Price List to Agreement: {0}").format(str(e)), ValidationError)
		
		# Price List var, şimdi fiyatları senkronize et
		sync_item_prices(doc, method)
	
	except frappe.exceptions.LinkValidationError as e:
		_handle_agreement_error(e, "Price List Creation", doc.name)
		
	except frappe.exceptions.MandatoryError as e:
		_handle_agreement_error(e, "Price List Creation", doc.name)
		
	except ValidationError as e:
		_handle_agreement_error(e, "Price List Creation", doc.name)
	
	except Exception as e:
		_handle_agreement_error(e, "Price List Creation", doc.name)


def sync_item_prices(doc, method):
	"""Sync Item Prices when Agreement is updated.
	
	Each item is added to price list based on its currency.
	Overlapping records are cleaned using ORM (triggers hooks).
	
	Raises:
		ValidationError: Item Price synchronization failed
	"""
	if not doc.customer:
		frappe.log_error(
			message="Customer field is empty",
			title="Agreement Item Price Sync - Missing Customer"
		)
		msgprint(_("❌ Customer field is missing, cannot sync prices"), indicator="red", alert=True)
		return
	
	# Price List varlık kontrolü - MUTLAKA olmalı
	price_list_name = f"{doc.customer}"
	if not frappe.db.exists("Price List", price_list_name):
		error_msg = _("Price List '{0}' not found! Please create price list first.").format(price_list_name)
		frappe.log_error(
			message=f"Price List '{price_list_name}' does not exist for agreement {doc.name}",
			title="Agreement Item Price Sync - Critical: Price List Missing"
		)
		msgprint(f"❌ {error_msg}", indicator="red", alert=True)
		frappe.throw(error_msg, ValidationError)
		
	try:
		discount_rate = frappe.utils.flt(getattr(doc, "discount_rate", 0))
		
		try:
			company_ccy = frappe.db.get_value("Company", {"is_group": 0}, "default_currency")
			if not company_ccy:
				company_ccy = "EUR"
				frappe.log_error(
					message="No default currency found, using EUR",
					title="Agreement Item Price Sync - Missing Currency"
				)
		except Exception as e:
			company_ccy = "EUR"
			frappe.log_error(
				message=f"Could not get company currency: {str(e)}",
				title="Agreement Item Price Sync - Currency Error"
			)
		
		processed_items = 0
		deleted_prices = 0
		failed_items = []
		
		for item in doc.agreement_items:
			if not item.item_code:
				frappe.log_error(
					message=f"Item code is empty in row {item.idx}",
					title="Agreement Item Price Sync - Missing Item Code"
				)
				continue
				
			try:
				item_ccy = item.currency or company_ccy
				price_list_name = f"{doc.customer}"
				
				try:
					# Sadece bu anlaşmaya ait fiyatları temizle
					deleted_count = _delete_overlapping_item_prices(
						price_list_name, 
						item.item_code, 
						doc.valid_from, 
						doc.valid_to,
						doc.name  # Agreement name ekledik
					)
					deleted_prices += deleted_count
				except ValidationError as e:
					frappe.log_error(
						message=f"Cleanup failed for item {item.item_code}: {str(e)}",
						title="Agreement Item Price Sync - Cleanup Failed"
					)
				
				if not frappe.db.exists("Price List", price_list_name):
					error_msg = f"Price List '{price_list_name}' not found"
					frappe.log_error(
						message=f"{error_msg} (Item: {item.item_code})",
						title="Agreement Item Price Sync - Price List Not Found"
					)
					failed_items.append((item.item_code, error_msg))
					continue
					
				row_agreement_rate = frappe.utils.flt(getattr(item, "price_list_rate", 0))
				if row_agreement_rate:
					effective_rate = row_agreement_rate
				else:
					std_rate = frappe.utils.flt(getattr(item, "standard_selling_rate", 0))
					if not std_rate:
						try:
							std_rate = _get_standard_selling_rate(item.item_code, item_ccy)
						except Exception as e:
							frappe.log_error(
								message=f"Could not get standard selling rate for {item.item_code}: {str(e)}",
								title="Agreement Item Price Sync - Rate Not Found"
							)
							std_rate = 0.0
					
					effective_rate = std_rate * (1.0 - (discount_rate / 100.0)) if discount_rate else std_rate
				
				if effective_rate <= 0:
					error_msg = "Valid price not found or zero"
					frappe.log_error(
						message=f"{error_msg} (Item: {item.item_code}, Rate: {effective_rate})",
						title="Agreement Item Price Sync - Invalid Rate"
					)
					failed_items.append((item.item_code, error_msg))
					continue
				
				# Bu anlaşmaya ait mevcut fiyatı bul
				existing = _find_existing_item_price(
					price_list_name, 
					item.item_code, 
					item_ccy, 
					doc.valid_from, 
					doc.valid_to,
					doc.name  # Agreement name ekledik
				)
				
				try:
					if existing:
						ip = frappe.get_doc("Item Price", existing[0])
						ip.price_list_rate = effective_rate
						if hasattr(ip, "customer"):
							setattr(ip, "customer", doc.customer)
						# Agreement referansını güncelle
						ip.note = doc.name
						ip.save(ignore_permissions=True)
					else:
						ip = frappe.new_doc("Item Price")
						ip.item_code = item.item_code
						ip.price_list = price_list_name
						ip.price_list_rate = effective_rate
						ip.currency = item_ccy
						ip.valid_from = doc.valid_from
						ip.valid_upto = doc.valid_to
						# Agreement referansını kaydet (note alanına)
						ip.note = doc.name
						if hasattr(ip, "customer"):
							setattr(ip, "customer", doc.customer)
						ip.insert(ignore_permissions=True)
					
					processed_items += 1
					
				except frappe.exceptions.MandatoryError as e:
					error_msg = f"Mandatory field missing: {str(e)}"
					failed_items.append((item.item_code, error_msg))
					frappe.log_error(
						message=f"{error_msg} (Item: {item.item_code})",
						title="Agreement Item Price Sync - Mandatory Error"
					)
					
				except ValidationError as e:
					error_msg = f"Validation error: {str(e)}"
					failed_items.append((item.item_code, error_msg))
					frappe.log_error(
						message=f"{error_msg} (Item: {item.item_code})",
						title="Agreement Item Price Sync - Validation Error"
					)
					
			except Exception as e:
				error_msg = f"Unexpected error: {str(e)}"
				failed_items.append((item.item_code, error_msg))
				frappe.log_error(
					message=f"{error_msg}\n{traceback.format_exc()}",
					title="Agreement Item Price Sync - Item Error"
				)
		
		if processed_items > 0:
			msg = _("✅ {0} item prices updated").format(processed_items)
			if deleted_prices > 0:
				msg += _(" ({0} old records cleaned)").format(deleted_prices)
			msgprint(msg, indicator="green", alert=True)
		else:
			# Hiç item işlenemediyse uyarı ver
			if not failed_items:
				msgprint(_("⚠️ No items to process in this agreement"), indicator="orange", alert=True)
		
		if failed_items:
			error_summary = _("⚠️ {0} items could not be processed:").format(len(failed_items)) + "\n"
			for item_code, reason in failed_items[:3]:
				error_summary += f"  - {item_code}: {reason}\n"
			
			if len(failed_items) > 3:
				error_summary += _("  ... and {0} more").format(len(failed_items) - 3) + "\n"
			
			msgprint(error_summary, indicator="orange", alert=True)
			
			if processed_items == 0:
				# Hiçbir fiyat oluşturulamadıysa MUTLAKA throw et
				frappe.throw(_("❌ No item prices could be synchronized!") + f"\n{error_summary}", ValidationError)
		
	except frappe.exceptions.LinkValidationError as e:
		_handle_agreement_error(e, "Item Price Sync", doc.name)
		
	except ValidationError as e:
		_handle_agreement_error(e, "Item Price Sync", doc.name)
		
	except Exception as e:
		_handle_agreement_error(e, "Item Price Sync", doc.name)


def cleanup_item_prices(doc, method):
	"""Clean up Item Prices when Agreement is cancelled.
	
	Overlapping records are deleted using ORM (triggers hooks).
	
	Raises:
		ValidationError: Item Price cleanup failed
	"""
	if not doc.customer:
		error_msg = _("Customer field is empty, cannot cleanup prices")
		frappe.log_error(
			message=error_msg,
			title="Agreement Item Price Cleanup - Missing Customer"
		)
		msgprint(f"⚠️ {error_msg}", indicator="orange", alert=True)
		return

	try:
		price_list_name = f"{doc.customer}"
		total_removed = 0
		failed_items = []
		
		if not frappe.db.exists("Price List", price_list_name):
			msg = _("Price List '{0}' not found, no prices to cleanup").format(price_list_name)
			frappe.log_error(
				message=msg,
				title="Agreement Item Price Cleanup - Price List Not Found"
			)
			msgprint(f"ℹ️ {msg}", indicator="blue", alert=True)
			return
		
		for item in doc.agreement_items:
			if not item.item_code:
				frappe.log_error(
					message=f"Item code is empty in row {item.idx}",
					title="Agreement Item Price Cleanup - Missing Item Code"
				)
				continue
			
			try:
				# Sadece bu anlaşmaya ait fiyatları temizle
				removed = _delete_overlapping_item_prices(
					price_list_name, 
					item.item_code, 
					doc.valid_from, 
					doc.valid_to,
					doc.name  # Agreement name ekledik
				)
				total_removed += removed
				
			except ValidationError as e:
				error_msg = f"Cleanup error: {str(e)}"
				failed_items.append((item.item_code, error_msg))
				frappe.log_error(
					message=f"{error_msg} (Item: {item.item_code})",
					title="Agreement Item Price Cleanup - Critical Error"
				)
				
			except Exception as e:
				error_msg = f"Unexpected error: {str(e)}"
				failed_items.append((item.item_code, error_msg))
				frappe.log_error(
					message=f"{error_msg}\n{traceback.format_exc()}",
					title="Agreement Item Price Cleanup - Unexpected Error"
				)
		
		if total_removed > 0:
			msgprint(_("✅ {0} price records removed").format(total_removed), indicator="green", alert=True)
		else:
			# Hiç fiyat silinmediyse bilgi ver
			if not failed_items:
				msgprint(_("ℹ️ No price records found to remove for this agreement"), indicator="blue", alert=True)
		
		if failed_items:
			error_summary = _("⚠️ {0} items could not be cleaned:").format(len(failed_items)) + "\n"
			for item_code, reason in failed_items[:3]:
				error_summary += f"  - {item_code}: {reason}\n"
			
			if len(failed_items) > 3:
				error_summary += _("  ... and {0} more").format(len(failed_items) - 3) + "\n"
			
			msgprint(error_summary, indicator="orange", alert=True)
			
			if total_removed == 0 and len(failed_items) == len(doc.agreement_items):
				frappe.throw(_("❌ No price records could be removed!") + f"\n{error_summary}", ValidationError)
		
	except frappe.exceptions.LinkValidationError as e:
		_handle_agreement_error(e, "Item Price Cleanup", doc.name)
		
	except ValidationError as e:
		_handle_agreement_error(e, "Item Price Cleanup", doc.name)
	
	except Exception as e:
		_handle_agreement_error(e, "Item Price Cleanup", doc.name)
