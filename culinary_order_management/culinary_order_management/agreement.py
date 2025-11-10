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


def sync_agreement_prices_on_standard_change(doc, method):
	"""Item Price (Standard Selling) güncellendiğinde ilgili Agreement'ların Item Price kayıtlarını güncelle.
	
	ÖNEMLİ: Agreement Item'a DOKUNULMAZ (submitted belge)
	Sadece Item Price kayıtları güncellenir.
	
	Args:
		doc: Item Price document
		method: ERPNext hook method name (after_insert veya on_update)
	"""
	# Sadece Standard Selling price list için çalış
	if doc.price_list != "Standard Selling":
		return
	
	# Item code kontrolü
	if not doc.item_code:
		return
	
	# Değişiklik var mı kontrol et (sadece update için - insert'te atlıyoruz)
	if method == "on_update" and not doc.has_value_changed("price_list_rate"):
		return
	
	try:
		# Bu item'ı içeren aktif agreement'ları bul
		agreements = frappe.db.sql("""
			SELECT DISTINCT 
				a.name, 
				a.customer, 
				a.discount_rate,
				a.valid_from,
				a.valid_to,
				ai.item_code,
				ai.currency
			FROM `tabAgreement` a
			JOIN `tabAgreement Item` ai ON ai.parent = a.name
			WHERE a.docstatus = 1
			  AND a.status = 'Active'
			  AND ai.item_code = %s
		""", (doc.item_code,), as_dict=True)
		
		if not agreements:
			frappe.logger().info(f"No active agreements found for item {doc.item_code}")
			return
		
		updated_count = 0
		failed_agreements = []
		
		for agreement_data in agreements:
			try:
				# Yeni fiyatı hesapla
				new_standard_rate = doc.price_list_rate
				discount_rate = frappe.utils.flt(agreement_data.discount_rate or 0)
				
				if discount_rate > 0:
					new_price = new_standard_rate * (1 - discount_rate / 100.0)
				else:
					new_price = new_standard_rate
				
				# Price List name
				price_list_name = agreement_data.customer
				currency = agreement_data.currency or doc.currency
				
				# Item Price'ı güncelle (eski fiyatı da döndürür)
				updated, old_agr_price = update_agreement_item_price(
					price_list=price_list_name,
					item_code=agreement_data.item_code,
					currency=currency,
					new_price=new_price,
					valid_from=agreement_data.valid_from,
					valid_upto=agreement_data.valid_to,
					agreement_name=agreement_data.name
				)
				
				if updated:
					updated_count += 1
					frappe.logger().info(
						f"✅ Agreement {agreement_data.name} - {agreement_data.item_code}: "
						f"Price updated from {old_agr_price} to {new_price} {currency}"
					)
					
					# Eski standard rate bul (Agreement Item'dan)
					old_std_rate = frappe.db.get_value("Agreement Item", {
						"parent": agreement_data.name,
						"item_code": agreement_data.item_code
					}, "standard_selling_rate") or 0
					
					# Child table'a kaydet
					create_price_change_log(
						agreement_name=agreement_data.name,
						item_code=agreement_data.item_code,
						old_price=old_agr_price,
						new_price=new_price,
						currency=currency,
						old_standard=float(old_std_rate),
						new_standard=new_standard_rate,
						source="Automatic"
					)
					
			except Exception as e:
				failed_agreements.append((agreement_data.name, str(e)))
				frappe.log_error(
					message=f"Agreement {agreement_data.name} price update failed: {str(e)}\n{traceback.format_exc()}",
					title="Agreement Price Sync - Item Update Failed"
				)
		
		# Sonuç mesajı
		if updated_count > 0:
			msg = _("✅ {0} agreement price updated for {1}").format(updated_count, doc.item_code)
			msgprint(msg, indicator="green", alert=True)
			
			# Log oluştur
			frappe.logger().info(f"Standard price change: {doc.item_code} - {updated_count} agreements updated")
		
		if failed_agreements:
			error_msg = _("⚠️ {0} agreement(s) could not be updated:").format(len(failed_agreements)) + "\n"
			for name, error in failed_agreements[:3]:
				error_msg += f"  - {name}: {error}\n"
			
			if len(failed_agreements) > 3:
				error_msg += f"  ... and {len(failed_agreements) - 3} more\n"
			
			msgprint(error_msg, indicator="orange", alert=True)
			
	except Exception as e:
		frappe.log_error(
			message=f"Failed to sync agreement prices for {doc.item_code}: {str(e)}\n{traceback.format_exc()}",
			title="Agreement Price Sync - Critical Error"
		)
		# Re-raise etme - Item Price update'i iptal etmesin
		msgprint(
			_("⚠️ Agreement price sync failed: {0}").format(str(e)),
			indicator="red",
			alert=True
		)


def update_agreement_item_price(
	price_list: str,
	item_code: str,
	currency: str,
	new_price: float,
	valid_from,
	valid_upto,
	agreement_name: str
) -> tuple:
	"""Belirli bir Agreement'ın Item Price kaydını güncelle.
	
	Args:
		price_list: Price list name (customer name)
		item_code: Item code
		currency: Currency
		new_price: New price
		valid_from: Valid from date
		valid_upto: Valid to date
		agreement_name: Agreement name (for note field)
		
	Returns:
		tuple: (success: bool, old_price: float) - Eski fiyatı da döndür
	"""
	try:
		# Mevcut Item Price'ı bul
		existing = _find_existing_item_price(
			price_list,
			item_code,
			currency,
			valid_from,
			valid_upto,
			agreement_name
		)
		
		if not existing:
			frappe.log_error(
				message=f"Item Price not found for {item_code} in {price_list} (Agreement: {agreement_name})",
				title="Agreement Price Update - Item Price Not Found"
			)
			return (False, 0)
		
		# ÖNCE eski fiyatı al
		item_price_name = existing[0]
		old_price = frappe.db.get_value("Item Price", item_price_name, "price_list_rate")
		
		# Item Price'ı güncelle
		frappe.db.set_value(
			"Item Price",
			item_price_name,
			"price_list_rate",
			new_price,
			update_modified=True
		)
		
		# Commit et (önemli!)
		frappe.db.commit()
		
		frappe.logger().info(
			f"Item Price {item_price_name} updated: {old_price} → {new_price} {currency}"
		)
		
		return (True, float(old_price) if old_price else 0)
		
	except Exception as e:
		frappe.log_error(
			message=f"Failed to update Item Price: {str(e)}\n{traceback.format_exc()}",
			title="Agreement Price Update - Update Failed"
		)
		return (False, 0)


@frappe.whitelist()
def manual_update_agreement_prices(agreement_name: str):
	"""Manuel olarak Agreement'ın Item Price kayıtlarını güncelle.
	
	Args:
		agreement_name: Agreement name
		
	Returns:
		dict: {"success": bool, "updated_count": int, "price_changes": list}
	"""
	try:
		# Agreement'ı getir
		agreement = frappe.get_doc("Agreement", agreement_name)
		
		# Sadece submitted ve aktif agreement'lar güncellenebilir
		if agreement.docstatus != 1:
			return {
				"success": False,
				"error": _("Only submitted agreements can be updated")
			}
		
		if agreement.status != "Active":
			return {
				"success": False,
				"error": _("Only active agreements can be updated")
			}
		
		updated_count = 0
		price_changes = []
		failed_items = []
		
		for item in agreement.agreement_items:
			if not item.item_code:
				continue
			
			try:
				# Güncel Standard Selling fiyatını çek
				currency = item.currency or frappe.db.get_value("Company", {"is_group": 0}, "default_currency") or "EUR"
				new_standard_rate = _get_standard_selling_rate(item.item_code, currency)
				
				if not new_standard_rate or new_standard_rate <= 0:
					failed_items.append((item.item_code, "Standard Selling price not found"))
					continue
				
				# Yeni fiyatı hesapla
				discount_rate = frappe.utils.flt(agreement.discount_rate or 0)
				if discount_rate > 0:
					new_price = new_standard_rate * (1 - discount_rate / 100.0)
				else:
					new_price = new_standard_rate
				
				# Eski fiyatı al
				price_list_name = agreement.customer
				existing = _find_existing_item_price(
					price_list_name,
					item.item_code,
					currency,
					agreement.valid_from,
					agreement.valid_to,
					agreement.name
				)
				
				if not existing:
					failed_items.append((item.item_code, "Item Price not found"))
					continue
				
				# Eski fiyatı oku
				old_price = frappe.db.get_value("Item Price", existing[0], "price_list_rate")
				
				# Fiyat değişti mi?
				if abs(float(old_price) - new_price) < 0.01:
					continue
				
				# Güncelle (eski fiyatı döndürür)
				updated, returned_old_price = update_agreement_item_price(
					price_list=price_list_name,
					item_code=item.item_code,
					currency=currency,
					new_price=new_price,
					valid_from=agreement.valid_from,
					valid_upto=agreement.valid_to,
					agreement_name=agreement.name
				)
				
				if updated:
					updated_count += 1
					price_changes.append({
						"item_code": item.item_code,
						"old_price": returned_old_price,
						"new_price": new_price,
						"currency": currency
					})
					
					# Log oluştur (child table'a kaydet)
					create_price_change_log(
						agreement_name=agreement.name,
						item_code=item.item_code,
						old_price=returned_old_price,
						new_price=new_price,
						currency=currency,
						old_standard=frappe.utils.flt(item.standard_selling_rate),
						new_standard=new_standard_rate,
						source="Manual"
					)
					
			except Exception as e:
				failed_items.append((item.item_code, str(e)))
				frappe.log_error(
					message=f"Failed to update price for {item.item_code}: {str(e)}\n{traceback.format_exc()}",
					title="Manual Agreement Price Update - Item Failed"
				)
		
		# Sonuç mesajı
		result = {
			"success": True,
			"updated_count": updated_count,
			"price_changes": price_changes
		}
		
		if failed_items:
			error_msg = _("⚠️ {0} item(s) could not be updated:").format(len(failed_items)) + "\n"
			for item_code, reason in failed_items[:3]:
				error_msg += f"  - {item_code}: {reason}\n"
			result["warning"] = error_msg
		
		frappe.db.commit()
		return result
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Manual agreement price update failed: {str(e)}\n{traceback.format_exc()}",
			title="Manual Agreement Price Update - Failed"
		)
		return {
			"success": False,
			"error": str(e)
		}


def create_price_change_log(
	agreement_name: str,
	item_code: str,
	old_price: float,
	new_price: float,
	currency: str,
	old_standard: float = 0,
	new_standard: float = 0,
	source: str = "Automatic"
):
	"""Fiyat değişiklik logu oluştur (child table'a kaydet).
	
	Args:
		agreement_name: Agreement name
		item_code: Item code
		old_price: Old agreement price
		new_price: New agreement price
		currency: Currency
		old_standard: Old standard selling rate
		new_standard: New standard selling rate
		source: "Automatic" or "Manual"
	"""
	try:
		# Child table'a doğrudan SQL ile ekle (submitted belge için)
		diff = new_price - old_price
		diff_pct = (diff / old_price * 100) if old_price > 0 else 0
		
		# Yeni row oluştur
		row = frappe.new_doc("Agreement Item Price History")
		row.parent = agreement_name
		row.parenttype = "Agreement"
		row.parentfield = "price_history"
		row.change_date = frappe.utils.now()
		row.item_code = item_code
		row.old_standard_rate = old_standard
		row.new_standard_rate = new_standard
		row.old_agreement_rate = old_price
		row.new_agreement_rate = new_price
		row.currency = currency
		row.change_percentage = diff_pct
		row.changed_by = frappe.session.user
		row.source = source
		row.insert(ignore_permissions=True)
		
		frappe.db.commit()
		
		frappe.logger().info(f"Price change logged to child table: {agreement_name} - {item_code}: {old_price} → {new_price}")
		
	except Exception as e:
		frappe.log_error(
			message=f"Failed to create price change log: {str(e)}\n{traceback.format_exc()}",
			title="Price Change Log - Failed"
		)


@frappe.whitelist()
def clear_price_history(agreement_name: str, item_code: str = None):
	"""Agreement'ın fiyat değişiklik geçmişini temizle.
	
	Args:
		agreement_name: Agreement name
		item_code: Opsiyonel - Belirli bir ürün için temizle
		
	Returns:
		dict: {"success": bool, "deleted_count": int}
	"""
	try:
		# Permission check
		if not frappe.has_permission("Agreement", "write"):
			return {
				"success": False,
				"error": _("You don't have permission to modify Agreement")
			}
		
		# Silme filtreleri
		filters = {"parent": agreement_name}
		if item_code:
			filters["item_code"] = item_code
		
		# Kaç kayıt silinecek?
		count = frappe.db.count("Agreement Item Price History", filters)
		
		if count == 0:
			return {
				"success": True,
				"deleted_count": 0,
				"message": _("No records to delete")
			}
		
		# SQL ile toplu silme (hızlı)
		frappe.db.delete("Agreement Item Price History", filters)
		frappe.db.commit()
		
		frappe.logger().info(f"Price history cleared: {agreement_name} - {count} records deleted")
		
		return {
			"success": True,
			"deleted_count": count,
			"message": _("{0} records deleted").format(count)
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Failed to clear price history: {str(e)}\n{traceback.format_exc()}",
			title="Clear Price History - Failed"
		)
		return {
			"success": False,
			"error": str(e)
		}


@frappe.whitelist()
def delete_price_history_row(row_name: str):
	"""Tek bir price history kaydını sil.
	
	Args:
		row_name: Price history row name
		
	Returns:
		dict: {"success": bool}
	"""
	try:
		# Permission check
		if not frappe.has_permission("Agreement", "write"):
			return {
				"success": False,
				"error": _("You don't have permission to modify Agreement")
			}
		
		# ORM ile sil (hooks tetiklenir)
		frappe.delete_doc("Agreement Item Price History", row_name, ignore_permissions=True, force=True)
		frappe.db.commit()
		
		frappe.logger().info(f"Price history row deleted: {row_name}")
		
		return {
			"success": True,
			"message": _("Record deleted")
		}
		
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			message=f"Failed to delete price history row: {str(e)}\n{traceback.format_exc()}",
			title="Delete Price History Row - Failed"
		)
		return {
			"success": False,
			"error": str(e)
		}
