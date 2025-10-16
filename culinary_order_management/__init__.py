__version__ = "0.0.1"


# DATEV PDF Override - Monkey Patch
# App yüklendiğinde otomatik uygulanır
def _patch_datev():
	"""erpnext_datev attach_print fonksiyonunu override eder"""
	try:
		from culinary_order_management.custom_datev import attach_print_custom
		import erpnext_datev.erpnext_datev.doctype.datev_unternehmen_online_settings.datev_unternehmen_online_settings as datev_module
		
		# Orijinal fonksiyonu custom ile değiştir
		datev_module.attach_print = attach_print_custom
		
	except Exception:
		pass  # erpnext_datev kurulu değilse sessizce geç


# Patch'i uygula
_patch_datev()
