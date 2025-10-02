import frappe


def set_supplier_display_on_item(doc, method):
	"""
	Item kaydı kaydedilirken, tedarikçi öğelerindeki (Supplier Items) ilk tedarikçiyi
	okuyup `supplier_display` alanına yazar. Liste görünümünde tedarikçi göstermek için kullanılır.
	"""
	try:
		primary_supplier = None
		# Child table fieldname ERPNext'te 'supplier_items' (doctype: Item Supplier)
		if getattr(doc, "supplier_items", None) and len(doc.supplier_items) > 0:
			# Önceliklendirme: is_primary_supplier / is_primary  == 1 varsa onu al; yoksa ilk satır
			primary_row = next(
				(
					r
					for r in doc.supplier_items
					if int(r.get("is_primary_supplier", r.get("is_primary", 0)) or 0) == 1
				),
				None,
			)
			primary_supplier = (primary_row or doc.supplier_items[0]).get("supplier")
		else:
			# Doc üzerinde yoksa, DB'den oku
			rows = frappe.get_all(
				"Item Supplier",
				filters={"parent": doc.name},
				fields=["supplier", "is_primary_supplier", "idx"],
				order_by="(ifnull(is_primary_supplier,0)) desc, idx asc",
			)
			if rows:
				primary_supplier = rows[0].supplier
		doc.supplier_display = primary_supplier
	except Exception:
		frappe.log_error("Set Supplier Display Error", frappe.get_traceback())


