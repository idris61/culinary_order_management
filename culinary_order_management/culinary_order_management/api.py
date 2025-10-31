import json
from typing import Any, Dict, List, Optional, Tuple

import frappe
from frappe import _
from frappe.permissions import has_permission


def _parse_filters(raw_filters: Any) -> Dict[str, Any]:
	"""filters parametresini sözlüğe dönüştürür (JSON string olabilir)."""
	if isinstance(raw_filters, str):
		try:
			return json.loads(raw_filters) if raw_filters else {}
		except Exception:
			return {}
	return raw_filters or {}


@frappe.whitelist()
def item_by_supplier(
	doctype: str = "Item",
	txt: str = "",
	searchfield: str = "name",
	start: int = 0,
	page_len: int = 20,
	filters: Optional[Any] = None,
) -> List[Tuple[str, str]]:
	"""Tedarikçiye bağlı ürünleri döndürür.
	
	`tabItem Supplier` üzerinden eşleşme yapılır.
	Arama, item `name` ve `item_name` alanlarında yapılır.
	
	Requires: Item read permission
	"""
	# Permission check
	if not has_permission("Item", "read"):
		frappe.throw(_("You don't have permission to read Item"), frappe.PermissionError)
	
	flt = _parse_filters(filters)
	supplier = flt.get("supplier") or flt.get("default_supplier")

	if not supplier or supplier == "__NONE__":
		return []

	like_txt = f"%{txt}%" if txt else "%"

	# Güvenli alan doğrulama: sadece izin verilen alan adları
	allowed_fields = {"name", "item_name"}
	sf = searchfield if searchfield in allowed_fields else "name"

	return frappe.db.sql(
		"""
		select i.name, i.item_name
		  from `tabItem` i
		  where exists (
				select 1 from `tabItem Supplier` s
				 where s.parent = i.name and s.supplier = %s
		  )
			and (i.{sf} like %s or i.item_name like %s)
		  order by i.modified desc
		  limit %s offset %s
		""".format(sf=sf),
		(supplier, like_txt, like_txt, page_len, start),
	)


@frappe.whitelist()
def item_query_by_supplier(
	doctype: str = "Item",
	txt: str = "",
	searchfield: str = "name",
	start: int = 0,
	page_len: int = 20,
	filters: Optional[Any] = None,
):
	"""Link alanı sorguları için tedarikçiye göre ürün sorgusu proxy'si.
	
	Permission check item_by_supplier() içinde yapılır.
	"""
	return item_by_supplier(doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
def items_by_customer_agreement(
	doctype: str = "Item",
	txt: str = "",
	searchfield: str = "name",
	start: int = 0,
	page_len: int = 20,
	filters: Optional[Any] = None,
):
	"""Müşterinin geçerli anlaşmalarına göre sipariş edebileceği ürünleri listeler.
	
	Tarih kontrolü Agreement.valid_from/valid_to üzerinden yapılır.
	
	Requires: Agreement read permission
	"""
	# Permission check
	if not has_permission("Agreement", "read"):
		frappe.throw(_("You don't have permission to read Agreement"), frappe.PermissionError)
	
	flt = _parse_filters(filters)
	customer = flt.get("customer")
	posting_date = flt.get("posting_date") or frappe.utils.nowdate()

	if not customer:
		return []

	like_txt = f"%{txt}%" if txt else "%"

	# Güvenli alan doğrulama: sadece izin verilen alan adları
	allowed_fields = {"name", "item_name"}
	sf = searchfield if searchfield in allowed_fields else "name"

	query = f"""
		select i.name, i.item_name
		  from `tabAgreement` ag
		  join `tabAgreement Item` ai on ai.parent = ag.name
		  join `tabItem` i on i.name = ai.item_code
		 where ag.customer = %s
		   and ifnull(ag.valid_from, '0001-01-01') <= %s
		   and ifnull(ag.valid_to, '9999-12-31') >= %s
		   and (i.{sf} like %s or i.item_name like %s)
		 group by i.name, i.item_name
		 order by max(ag.valid_from) desc
		 limit %s offset %s
	"""

	return frappe.db.sql(
		query,
		(customer, posting_date, posting_date, like_txt, like_txt, page_len, start),
	)
