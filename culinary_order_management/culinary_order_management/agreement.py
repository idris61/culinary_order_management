"""
Culinary Order Management - Agreement Integration (price lists & item prices)
"""

import frappe
from frappe import msgprint


def _get_standard_selling_rate(item_code: str, currency: str) -> float:
	""""Standard Selling" fiyat listesinden veya en yakın satış fiyatından birim fiyatı getirir."""
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


def _find_existing_item_price(price_list: str, item_code: str, currency: str, valid_from, valid_upto):
	"""Find existing Item Price by natural unique keys, handling NULL dates properly."""
	filters = {
		"price_list": price_list,
		"item_code": item_code,
		"currency": currency,
	}
	if valid_from:
		filters["valid_from"] = valid_from
	else:
		filters["valid_from"] = ["is", "not set"]
	if valid_upto:
		filters["valid_upto"] = valid_upto
	else:
		filters["valid_upto"] = ["is", "not set"]
	return frappe.get_all("Item Price", filters=filters, pluck="name")


def _delete_overlapping_item_prices(price_list: str, item_code: str, new_from, new_upto):
	"""Delete Item Price rows in same price list and item that overlap with given date range.

	If dates are null, treat as open-ended.
	"""
	conds = ["price_list=%s", "item_code=%s"]
	vals = [price_list, item_code]
	# Overlap logic
	if new_upto:
		conds.append("(valid_from IS NULL OR valid_from <= %s)")
		vals.append(new_upto)
	else:
		conds.append("1=1")
	if new_from:
		conds.append("(valid_upto IS NULL OR valid_upto >= %s)")
		vals.append(new_from)
	else:
		conds.append("1=1")
	where = " AND ".join(conds)
	frappe.db.sql(f"DELETE FROM `tabItem Price` WHERE {where}", vals)


@frappe.whitelist()
def get_supplier_items_with_standard_prices(supplier: str, currency: str | None = None):
	"""Seçilen tedarikçiye ait tüm aktif stok kalemlerini ve standart satış fiyatlarını döndürür.

	Dönüş formatı: [{"item_code", "item_name", "uom", "standard_selling_rate", "price_list_rate", "currency"}]
	price_list_rate = standard_selling_rate ile başlatılır; istemci tarafında gerekirse üzerine yazılabilir.
	"""
	if not supplier:
		return []

	# Tedarikçiye bağlı item'ları getir
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
		# Öncelik: Tedarikçinin fatura para birimi
		supplier_currency = frappe.db.get_value("Supplier", supplier, "default_currency")
		if not supplier_currency:
			company_currency = frappe.db.get_value("Company", {"is_group": 0}, "default_currency")
			currency = company_currency or "EUR"
		else:
			currency = supplier_currency

	# Fiyatları toplu çek (Standard Selling + ilgili currency)
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

	# Sonuçları tek döngüde hazırla
	result = []
	append = result.append
	for it in items:
		std_rate = price_map.get(it.item_code, 0.0)
		if not std_rate:
			# Fallback: ilgili para biriminde kayıt yoksa en güncel satış fiyatını getir
			std_rate = _get_standard_selling_rate(it.item_code, currency)
		append(
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
	"""
	Agreement oluşturulduğunda/güncellendiğinde fiyat listesi oluştur
	Her agreement item'ın kendi currency'si olabilir
	"""
	if not doc.customer:
		return
		
	try:
		# Agreement item'larından currency'leri topla
		currencies_used = set()
		for item in doc.agreement_items:
			if item.currency:
				currencies_used.add(item.currency)
		
		# Eğer hiç currency belirtilmemişse şirket para birimini kullan
		if not currencies_used:
			company_currency = frappe.db.get_value("Company", {"is_group": 0}, "default_currency") or "EUR"
			currencies_used.add(company_currency)
		
		# Her currency için aynı isimli (müşteri adı) fiyat listesini kullan
		for currency in currencies_used:
			price_list_name = f"{doc.customer}"
			if not frappe.db.exists("Price List", price_list_name):
				price_list = frappe.new_doc("Price List")
				price_list.price_list_name = price_list_name
				price_list.enabled = 1
				price_list.selling = 1
				price_list.currency = currency
				price_list.insert()
				frappe.db.commit()
				msgprint(f"✅ Fiyat listesi '{price_list_name}' oluşturuldu ({currency})")
			else:
				price_list = frappe.get_doc("Price List", price_list_name)
				if not price_list.enabled:
					price_list.enabled = 1
					price_list.save()
					frappe.db.commit()
					msgprint(f"✅ Fiyat listesi '{price_list_name}' aktif edildi")

		# Anlaşmaya bağla (tek isim: müşteri adı)
		doc.price_list = f"{doc.customer}"
		doc.db_set("price_list", doc.price_list)
		
		# Agreement ürünlerini fiyat listelerine ekle
		sync_item_prices(doc, method)
	
	except Exception as e:
		frappe.log_error(f"Price list creation error: {str(e)}")
		msgprint(f"❌ Fiyat listesi oluşturma hatası: {str(e)}", alert=True)


def sync_item_prices(doc, method):
	"""
	Agreement güncellendiğinde Item Price'ları senkronize et
	Her item kendi currency'sine göre fiyat listesine eklenir
	"""
	if not doc.customer:
		return
		
	try:
		# Agreement ürünlerini kendi currency'lerine göre fiyat listelerine ekle
		discount_rate = frappe.utils.flt(getattr(doc, "discount_rate", 0))
		company_ccy = frappe.db.get_value("Company", {"is_group": 0}, "default_currency") or "EUR"
		for item in doc.agreement_items:
			if not item.item_code:
				continue
			# Aynı müşteri listesinde bu ürün için yeni tarih aralığı ile çakışan kayıtları temizle
			item_ccy = item.currency or company_ccy
			price_list_name = f"{doc.customer}"
			_delete_overlapping_item_prices(price_list_name, item.item_code, doc.valid_from, doc.valid_to)
			if not frappe.db.exists("Price List", price_list_name):
				continue
			# Eğer satırda anlaşma fiyatı varsa doğrudan onu kullan; yoksa standart fiyata indirim uygula
			row_agreement_rate = frappe.utils.flt(getattr(item, "price_list_rate", 0))
			if row_agreement_rate:
				effective_rate = row_agreement_rate
			else:
				std_rate = frappe.utils.flt(getattr(item, "standard_selling_rate", 0))
				if not std_rate:
					std_rate = _get_standard_selling_rate(item.item_code, item_ccy)
				effective_rate = std_rate * (1.0 - (discount_rate / 100.0)) if discount_rate else std_rate
			# Upsert: Aynı anahtarla kayıt varsa güncelle, yoksa oluştur
			existing = _find_existing_item_price(price_list_name, item.item_code, item_ccy, doc.valid_from, doc.valid_to)
			if existing:
				ip = frappe.get_doc("Item Price", existing[0])
				ip.price_list_rate = effective_rate
				# Müşteri bilgisi (rapor kolaylığı)
				if hasattr(ip, "customer"):
					setattr(ip, "customer", doc.customer)
				ip.save()
			else:
				ip = frappe.new_doc("Item Price")
				ip.item_code = item.item_code
				ip.price_list = price_list_name
				ip.price_list_rate = effective_rate
				ip.currency = item_ccy
				ip.valid_from = doc.valid_from
				ip.valid_upto = doc.valid_to
				if hasattr(ip, "customer"):
					setattr(ip, "customer", doc.customer)
				ip.insert()
		
		frappe.db.commit()
		msgprint(f"✅ {len(doc.agreement_items)} ürün fiyatı güncellendi")
		
	except Exception as e:
		frappe.log_error(f"Item price sync error: {str(e)}")
		msgprint(f"❌ Ürün fiyatı güncelleme hatası: {str(e)}", alert=True)


def cleanup_item_prices(doc, method):
	"""
	Agreement silindiğinde Item Price'ları temizle
	Bu müşteri için oluşturulan tüm currency'li fiyat listelerini sil
	"""
	if not doc.customer:
		return

	try:
		# Bu anlaşma tarih aralığı ile çakışan ürün kayıtlarını müşterinin fiyat listesinde temizle
		removed = 0
		price_list_name = f"{doc.customer}"
		for item in doc.agreement_items:
			before = frappe.db.count("Item Price", filters={"price_list": price_list_name, "item_code": item.item_code})
			_delete_overlapping_item_prices(price_list_name, item.item_code, doc.valid_from, doc.valid_to)
			after = frappe.db.count("Item Price", filters={"price_list": price_list_name, "item_code": item.item_code})
			removed += max(0, before - after)
		frappe.db.commit()
		msgprint(f"✅ {removed} fiyat kaydı kaldırıldı")
	except Exception as e:
		frappe.log_error(f"Price list cleanup error: {str(e)}")
		msgprint(f"❌ Fiyat kaydı temizleme hatası: {str(e)}", alert=True)


