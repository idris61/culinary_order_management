import frappe
from frappe import _
from frappe.utils import getdate
from typing import Optional, Dict, Any


def get_conversion_rate(from_currency: str, to_currency: str, date: str) -> float:
	"""Currency conversion rate al"""
	if from_currency == to_currency:
		return 1.0
	try:
		rate = frappe.db.get_value(
			"Currency Exchange",
			{
				"from_currency": from_currency,
				"to_currency": to_currency,
				"date": ["<=", date],
			},
			"exchange_rate",
			order_by="date desc",
		)
		if rate:
			return float(rate)
		else:
			frappe.log_error(
				f"Currency conversion rate not found: {from_currency} to {to_currency} on {date}"
			)
			return 1.0
	except Exception as e:
		frappe.log_error(f"Currency conversion error: {str(e)}")
		return 1.0


def _get_item_price_from_agreements(
	customer: str, item_code: str, posting_date
) -> Optional[Dict[str, Any]]:
	# Müşteri + ürün için geçerli anlaşma kalemini getirir
	rows = frappe.db.sql(
		"""
		select ag.name as agreement,
		       ag.supplier,
		       ai.item_code,
		       ai.price_list_rate,
		       ai.currency,
		       ag.valid_from,
		       ag.valid_to
		  from `tabAgreement` ag
		  join `tabAgreement Item` ai on ai.parent = ag.name
		 where ag.customer = %s
		   and ai.item_code = %s
		   and ifnull(ag.valid_from, '0001-01-01') <= %s
		   and ifnull(ag.valid_to, '9999-12-31') >= %s
		 order by ag.valid_from desc
		 limit 1
		""",
		(customer, item_code, posting_date, posting_date),
		as_dict=True,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_item_price_from_agreement(
	customer: str, item_code: str, posting_date: str, so_currency: str = "EUR"
) -> Dict[str, Any]:
	"""
	Client-side'dan çağrılır - item seçildiğinde fiyatı otomatik olarak getirir
	"""
	try:
		info = _get_item_price_from_agreements(customer, item_code, posting_date)
		if not info:
			return {}

		# Currency conversion yap
		agreement_currency = info["currency"]
		agreement_rate = info["price_list_rate"]

		if agreement_currency != so_currency:
			conversion_rate = get_conversion_rate(
				agreement_currency, so_currency, posting_date
			)
			converted_rate = agreement_rate * conversion_rate
		else:
			converted_rate = agreement_rate

		return {
			"price_list_rate": converted_rate,
			"currency": so_currency,
			"supplier": info["supplier"],
		}
	except Exception as e:
		frappe.log_error(f"get_item_price_from_agreement error: {str(e)}")
		return {}


def validate_sales_order(doc, method=None):
	if not doc.customer:
		return

	# Validate each item against agreements and set price
	posting_date = (
		doc.get("transaction_date") or doc.get("delivery_date") or frappe.utils.nowdate()
	)

	# Sales Order'ın currency'sini al
	so_currency = doc.currency or frappe.get_default("currency") or "EUR"

	for item in doc.items:
		info = _get_item_price_from_agreements(doc.customer, item.item_code, posting_date)
		if not info:
			frappe.throw(
				_(
					"Item {0} is not allowed for this Customer per Agreements or no valid price."
				).format(item.item_code)
			)

		# Geçerlilik tarihi kontrolü
		valid_from = info.get("valid_from")
		valid_to = info.get("valid_to")
		posting_date_obj = getdate(posting_date)

		if valid_from:
			valid_from_obj = getdate(valid_from)
			if posting_date_obj < valid_from_obj:
				frappe.throw(
					_("Item {0} Agreement is not valid yet. Valid from: {1}").format(
						item.item_code, valid_from
					)
				)

		if valid_to:
			valid_to_obj = getdate(valid_to)
			if posting_date_obj > valid_to_obj:
				frappe.throw(
					_("Item {0} Agreement has expired. Valid until: {1}").format(
						item.item_code, valid_to
					)
				)

		# Currency conversion yap
		agreement_currency = info["currency"]
		agreement_rate = info["price_list_rate"]

		if agreement_currency != so_currency:
			conversion_rate = get_conversion_rate(
				agreement_currency, so_currency, posting_date
			)
			converted_rate = agreement_rate * conversion_rate
		else:
			converted_rate = agreement_rate

		# Set rate and mark as read-only via flag for client script to enforce
		item.rate = converted_rate
		item.price_list_rate = converted_rate
		item._agreement_supplier = info["supplier"]
		item._agreement_rate_locked = 1

		# Tutarı hesapla (qty * rate)
		item.amount = item.qty * converted_rate
