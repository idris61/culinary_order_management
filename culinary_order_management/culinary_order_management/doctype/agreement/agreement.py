import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class Agreement(Document):
	"""Customer-Supplier agreement master.
	
	Professional submittable document with automatic status management.
	Status is based on docstatus and validity dates.
	"""
	
	def onload(self):
		"""Load güncel fiyatları hesapla ve virtual field'lara set et."""
		if self.docstatus != 1:
			return
		
		from culinary_order_management.culinary_order_management.agreement import (
			_get_standard_selling_rate,
			_find_existing_item_price
		)
		
		for item in self.agreement_items:
			if not item.item_code:
				continue
			
			try:
				# Güncel Standard Selling fiyatı
				currency = item.currency or frappe.db.get_value("Company", {"is_group": 0}, "default_currency") or "EUR"
				current_standard = _get_standard_selling_rate(item.item_code, currency)
				
				# Güncel Agreement fiyatı (Item Price'dan)
				price_list_name = self.customer
				current_agreement = self._get_current_agreement_rate(item.item_code, price_list_name, currency)
				
				# Virtual field'lara set et
				item.current_standard_rate = current_standard
				item.current_agreement_rate = current_agreement
				
				# Fiyat değişimi HTML göstergesi
				item.price_change_indicator = self._get_price_change_html(
					original_standard=frappe.utils.flt(item.standard_selling_rate),
					current_standard=current_standard,
					original_agreement=frappe.utils.flt(item.price_list_rate),
					current_agreement=current_agreement,
					currency=currency
				)
				
			except Exception as e:
				frappe.log_error(
					message=f"Failed to load current prices for {item.item_code}: {str(e)}",
					title="Agreement Load - Price Calculation Failed"
				)
	
	def _get_current_agreement_rate(self, item_code: str, price_list: str, currency: str) -> float:
		"""Item Price'dan güncel Agreement fiyatını çek."""
		try:
			item_price = frappe.db.get_value(
				"Item Price",
				{
					"price_list": price_list,
					"item_code": item_code,
					"currency": currency,
					"note": ["like", f"%{self.name}%"]
				},
				"price_list_rate"
			)
			
			return float(item_price) if item_price else 0.0
			
		except Exception:
			return 0.0
	
	def _get_price_change_html(
		self,
		original_standard: float,
		current_standard: float,
		original_agreement: float,
		current_agreement: float,
		currency: str
	) -> str:
		"""Fiyat değişimi HTML göstergesi oluştur."""
		
		# Değişiklik hesapla
		standard_diff = current_standard - original_standard
		standard_pct = (standard_diff / original_standard * 100) if original_standard > 0 else 0
		
		agreement_diff = current_agreement - original_agreement
		agreement_pct = (agreement_diff / original_agreement * 100) if original_agreement > 0 else 0
		
		# Renk belirleme
		def get_color(diff):
			if abs(diff) < 0.01:
				return "#28a745"  # green
			return "#dc3545" if diff > 0 else "#28a745"  # red/green
		
		standard_color = get_color(standard_diff)
		agreement_color = get_color(agreement_diff)
		
		# Değişiklik yoksa
		if abs(standard_diff) < 0.01 and abs(agreement_diff) < 0.01:
			return '<div style="padding: 10px; color: #28a745; font-weight: bold;">✅ Prices are up to date</div>'
		
		html = f"""
		<div style="padding: 10px; background-color: #f8f9fa; border-radius: 5px; border-left: 4px solid {agreement_color};">
			<table style="width: 100%; font-size: 12px; border-collapse: collapse;">
				<thead>
					<tr style="border-bottom: 2px solid #dee2e6;">
						<th style="text-align: left; padding: 5px; font-weight: bold;">Type</th>
						<th style="text-align: right; padding: 5px; font-weight: bold;">Original</th>
						<th style="text-align: right; padding: 5px; font-weight: bold;">Current</th>
						<th style="text-align: right; padding: 5px; font-weight: bold;">Change</th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td style="padding: 5px;">Standard Selling</td>
						<td style="text-align: right; padding: 5px;">{original_standard:.2f} {currency}</td>
						<td style="text-align: right; padding: 5px; font-weight: bold;">{current_standard:.2f} {currency}</td>
						<td style="text-align: right; padding: 5px; color: {standard_color}; font-weight: bold;">
							{standard_diff:+.2f} ({standard_pct:+.1f}%)
						</td>
					</tr>
					<tr style="background-color: #ffffff;">
						<td style="padding: 5px;">Agreement Price</td>
						<td style="text-align: right; padding: 5px;">{original_agreement:.2f} {currency}</td>
						<td style="text-align: right; padding: 5px; font-weight: bold;">{current_agreement:.2f} {currency}</td>
						<td style="text-align: right; padding: 5px; color: {agreement_color}; font-weight: bold;">
							{agreement_diff:+.2f} ({agreement_pct:+.1f}%)
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		"""
		
		return html
	
	def validate(self):
		"""Validate agreement before save."""
		self.validate_dates()
		self.validate_items()
		self.update_status()
	
	def before_submit(self):
		"""Validate before submit."""
		self.validate_dates()
		self.validate_items()
		
		# Check for overlapping agreements
		self.check_overlapping_agreements()
	
	def on_submit(self):
		"""Submit edildiğinde fiyat listelerini oluştur.
		
		Sadece aktif anlaşmalar için fiyatları oluştur.
		Başlamadı durumundakiler scheduled job ile aktif olunca oluşturulacak.
		"""
		# External hook fonksiyonunu çağır
		from culinary_order_management.culinary_order_management.agreement import create_price_list_for_agreement
		
		# Sadece aktif anlaşmalar için fiyat oluştur
		if self.status == "Active":
			create_price_list_for_agreement(self, "on_submit")
	
	def on_update_after_submit(self):
		"""Allow limited updates after submit."""
		if self.has_value_changed("valid_from") or self.has_value_changed("valid_to"):
			frappe.throw(_("Validity dates cannot be changed after submission. Please cancel and create a new agreement."))
		
		if self.has_value_changed("customer") or self.has_value_changed("supplier"):
			frappe.throw(_("Customer and Supplier cannot be changed after submission."))
		
		# Fiyatları senkronize et
		from culinary_order_management.culinary_order_management.agreement import sync_item_prices
		sync_item_prices(self, "on_update_after_submit")
	
	def validate_dates(self):
		"""Validate validity dates."""
		if not self.valid_from:
			frappe.throw(_("Valid From date is mandatory"))
		
		if not self.valid_to:
			frappe.throw(_("Valid To date is mandatory"))
		
		valid_from = getdate(self.valid_from)
		valid_to = getdate(self.valid_to)
		
		if valid_from > valid_to:
			frappe.throw(_("Valid To date cannot be before Valid From date"))
	
	def validate_items(self):
		"""Validate agreement items."""
		if not self.agreement_items:
			frappe.throw(_("Please add at least one item"))
		
		# Duplicate item check
		item_codes = [item.item_code for item in self.agreement_items if item.item_code]
		if len(item_codes) != len(set(item_codes)):
			frappe.throw(_("Duplicate items are not allowed"))
		
		# Price validation
		for item in self.agreement_items:
			if not item.item_code:
				frappe.throw(_("Row {0}: Item Code is mandatory").format(item.idx))
			
			if not item.price_list_rate or item.price_list_rate <= 0:
				frappe.throw(_("Row {0}: Please enter a valid price").format(item.idx))
	
	def check_overlapping_agreements(self):
		"""Aynı müşteri-tedarikçi için aktif anlaşma kontrolü (tarih bağımsız)."""
		if self.docstatus != 0:
			return
		
		# Eğer replacement işlemi içindeyse kontrolü atla
		if self.flags.get("is_replacement"):
			return
		
		active_agreements = frappe.db.sql("""
			SELECT name, valid_from, valid_to, status
			FROM `tabAgreement`
			WHERE customer = %s
			  AND supplier = %s
			  AND docstatus = 1
			  AND name != %s
		""", (self.customer, self.supplier, self.name), as_dict=True)
		
		if active_agreements:
			agreement_names = ", ".join([d.name for d in active_agreements])
			frappe.throw(
				_("Aktif anlaşma mevcut: {0}. Lütfen önce mevcut anlaşmayı iptal edin.").format(agreement_names),
				title=_("Aktif Anlaşma Var")
			)
	
	def update_status(self):
		"""Tarih bazlı dinamik status hesaplama."""
		# İptal edildiyse
		if self.docstatus == 2:
			self.status = "Cancelled"
			return
		
		# Taslaksa henüz başlamamış kabul ediyoruz
		if self.docstatus == 0:
			self.status = "Not Started"
			return
		
		# Tarih kontrolü (sadece submitted belgeler için)
		if self.docstatus == 1 and self.valid_from and self.valid_to:
			today = getdate(nowdate())
			valid_from = getdate(self.valid_from)
			valid_to = getdate(self.valid_to)
			
			if today < valid_from:
				self.status = "Not Started"
			elif today > valid_to:
				self.status = "Expired"
			else:
				self.status = "Active"
	
	def on_cancel(self):
		"""İptal edildiğinde status güncelle, Price List'i deaktive et ve fiyatları temizle."""
		self.update_status()
		
		# Price List'i deaktive et (ama önce başka aktif anlaşma var mı kontrol et)
		if self.customer:
			price_list_name = f"{self.customer}"
			if frappe.db.exists("Price List", price_list_name):
				# Aynı müşteri için başka aktif anlaşma var mı?
				other_active = frappe.db.count("Agreement", {
					"customer": self.customer,
					"docstatus": 1,
					"status": "Active",
					"name": ["!=", self.name]
				})
				
				# Başka aktif anlaşma yoksa Price List'i deaktive et
				if not other_active:
					frappe.db.set_value("Price List", price_list_name, "enabled", 0, update_modified=False)
		
		# External hook fonksiyonunu çağır (fiyatları temizler)
		from culinary_order_management.culinary_order_management.agreement import cleanup_item_prices
		cleanup_item_prices(self, "on_cancel")


@frappe.whitelist()
def check_active_agreement(customer, supplier, current_agreement=None):
	"""Müşteri-tedarikçi için aktif anlaşma kontrolü.
	
	Returns:
		dict: {"has_active": bool, "agreements": [{"name": str, "valid_from": date, "valid_to": date}]}
	"""
	filters = {
		"customer": customer,
		"supplier": supplier,
		"docstatus": 1
	}
	
	if current_agreement:
		filters["name"] = ["!=", current_agreement]
	
	active = frappe.get_all(
		"Agreement",
		filters=filters,
		fields=["name", "valid_from", "valid_to", "status"]
	)
	
	return {
		"has_active": len(active) > 0,
		"agreements": active
	}


@frappe.whitelist()
def replace_agreement(old_agreement, new_agreement):
	"""Eski anlaşmayı cancel et, yeni anlaşmayı submit et.
	
	Transaction içinde çalışır - hata olursa rollback yapılır.
	Frappe otomatik transaction yönetimi kullanır.
	"""
	try:
		# Eski anlaşmayı cancel et
		old_doc = frappe.get_doc("Agreement", old_agreement)
		if old_doc.docstatus != 1:
			frappe.throw(_("Eski anlaşma zaten submit edilmemiş"))
		
		old_doc.cancel()
		
		# Yeni anlaşmayı submit et
		new_doc = frappe.get_doc("Agreement", new_agreement)
		if new_doc.docstatus != 0:
			frappe.throw(_("Yeni anlaşma zaten submit edilmiş"))
		
		# Flag ekle - check_overlapping_agreements atlanacak
		new_doc.flags.is_replacement = True
		new_doc.submit()
		
		return {
			"success": True,
			"message": _("Eski anlaşma iptal edildi, yeni anlaşma onaylandı")
		}
		
	except Exception as e:
		frappe.log_error(
			message=f"Agreement replacement failed: {str(e)}",
			title="Agreement Replacement Error"
		)
		frappe.throw(_("İşlem başarısız: {0}").format(str(e)))


@frappe.whitelist()
def update_all_agreement_statuses():
	"""Tüm agreement'ların statuslerini güncelle ve expired olanları otomatik cancel et.
	
	Bu fonksiyon scheduled job olarak her gün çalıştırılabilir.
	
	Önemli: Expired olan agreement'lar otomatik cancel edilir (docstatus=2).
	Cancel işlemi mevcut on_cancel hook'u ile fiyatları otomatik temizler.
	"""
	agreements = frappe.get_all(
		"Agreement",
		fields=["name", "docstatus", "valid_from", "valid_to", "status"],
		filters={"docstatus": ["!=", 2]}  # Zaten cancel edilmiş olanları atlıyoruz
	)
	
	updated_count = 0
	cancelled_count = 0
	
	for agreement_data in agreements:
		try:
			doc = frappe.get_doc("Agreement", agreement_data.name)
			old_status = doc.status
			doc.update_status()
			
			# Status değiştiyse kaydet ve Price List'i güncelle
			if old_status != doc.status:
				doc.db_set("status", doc.status, update_modified=False)
				updated_count += 1
				frappe.logger().info(f"Agreement {doc.name} status güncellendi: {old_status} -> {doc.status}")
				
				# Status değişimlerine göre fiyat yönetimi
				if old_status == "Not Started" and doc.status == "Active":
					# Anlaşma aktif oldu - fiyatları oluştur
					from culinary_order_management.culinary_order_management.agreement import create_price_list_for_agreement
					try:
						create_price_list_for_agreement(doc, "status_change")
						frappe.logger().info(f"Agreement {doc.name} aktif oldu - fiyatlar oluşturuldu")
					except Exception as e:
						frappe.log_error(
							message=f"Fiyat oluşturma hatası: {str(e)}",
							title="Agreement Activation - Price Creation Failed"
						)
				
				elif old_status == "Active" and doc.status == "Expired":
					# Anlaşma expired oldu - fiyatları temizle
					from culinary_order_management.culinary_order_management.agreement import cleanup_item_prices
					try:
						cleanup_item_prices(doc, "status_change")
						frappe.logger().info(f"Agreement {doc.name} expired oldu - fiyatlar temizlendi")
					except Exception as e:
						frappe.log_error(
							message=f"Fiyat temizleme hatası: {str(e)}",
							title="Agreement Expiration - Price Cleanup Failed"
						)
				
				# Price List durumunu güncelle
				if doc.customer:
					price_list_name = f"{doc.customer}"
					if frappe.db.exists("Price List", price_list_name):
						# Aynı müşteri için herhangi bir aktif anlaşma var mı kontrol et
						active_count = frappe.db.count("Agreement", {
							"customer": doc.customer,
							"docstatus": 1,
							"status": "Active"
						})
						
						should_enable = 1 if active_count > 0 else 0
						frappe.db.set_value("Price List", price_list_name, "enabled", should_enable, update_modified=False)
						frappe.logger().info(f"Price List {price_list_name} {'aktivated' if should_enable else 'deactivated'}")
			
			# Kritik: Expired olmuş ve submitted olan agreement'ları otomatik cancel et
			if doc.status == "Expired" and doc.docstatus == 1:
				try:
					# Cancel et (on_cancel hook'u tetiklenir ve fiyatlar temizlenir)
					doc.cancel()
					# Status'ü "Expired" olarak koru (liste görünümünde "Günü Geçmiş" gösterilsin)
					doc.db_set("status", "Expired", update_modified=False)
					cancelled_count += 1
					frappe.logger().info(f"Agreement {doc.name} expired - otomatik cancel edildi, fiyatlar temizlendi")
				except Exception as cancel_error:
					frappe.log_error(
						message=f"Agreement {doc.name} cancel işlemi hatası: {str(cancel_error)}",
						title="Agreement Auto-Cancel Error"
					)
		
		except Exception as e:
			frappe.log_error(
				message=f"Agreement {agreement_data.name} işlenirken hata: {str(e)}",
				title="Agreement Status Update Error"
			)
	
	frappe.db.commit()
	frappe.logger().info(f"Toplam {updated_count} agreement status güncellendi, {cancelled_count} expired agreement otomatik cancel edildi")
	return {"updated": updated_count, "total": len(agreements), "cancelled": cancelled_count}
