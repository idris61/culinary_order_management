# -*- coding: utf-8 -*-
# Copyright (c) 2025, Culinary
# DATEV PDF Override - wkhtmltopdf network sorununu çözer
#
# Bu modül erpnext_datev'in attach_print fonksiyonunu override eder.
# Monkey patch __init__.py'de uygulanır.

import frappe
from frappe import _
from frappe.translate import print_language


def attach_print_custom(doctype, name, language, print_format):
	"""
	DATEV için özelleştirilmiş PDF oluşturma fonksiyonu.
	
	Orijinal attach_print fonksiyonunun override'ı.
	wkhtmltopdf network hatalarını önlemek için:
	- no_letterhead=1 kullanır (external kaynaklar yok)
	- Basit PDF formatı oluşturur
	"""
	
	with print_language(language):
		# no_letterhead ile PDF oluştur (external kaynaklar olmadan)
		data = frappe.get_print(
			doctype, 
			name, 
			print_format or "", 
			as_pdf=True,
			no_letterhead=1  # Logo/letterhead olmadan (network erişimi yok)
		)
	
	# E-Invoice XML ekle (varsa)
	if doctype == "Sales Invoice" and "eu_einvoice" in frappe.get_installed_apps():
		try:
			from eu_einvoice.european_e_invoice.custom.sales_invoice import attach_xml_to_pdf
			data = attach_xml_to_pdf(name, data)
		except Exception:
			msg = _("Failed to attach XML to Sales Invoice PDF for DATEV")
			frappe.log_error(title=msg, reference_doctype=doctype, reference_name=name)
			frappe.msgprint(msg, indicator="red", alert=True)
	
	# File olarak kaydet
	file_doc = frappe.new_doc("File")
	file_doc.file_name = f"{name}.pdf"
	file_doc.content = data
	file_doc.attached_to_doctype = doctype
	file_doc.attached_to_name = name
	file_doc.is_private = 1
	file_doc.save()
	
	return file_doc.name


# Not: send_to_datev_custom fonksiyonu kaldırıldı
# Monkey patch sadece attach_print fonksiyonunu override ediyor
# DATEV'in kendi send() fonksiyonu çalışmaya devam ediyor

