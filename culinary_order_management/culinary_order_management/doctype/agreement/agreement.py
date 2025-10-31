import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class Agreement(Document):
	"""Customer-Supplier agreement master.
	
	Professional submittable document with automatic status management.
	Status is based on docstatus and validity dates.
	"""
	
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
	
	def on_update_after_submit(self):
		"""Allow limited updates after submit."""
		if self.has_value_changed("valid_from") or self.has_value_changed("valid_to"):
			frappe.throw(_("Validity dates cannot be changed after submission. Please cancel and create a new agreement."))
		
		if self.has_value_changed("customer") or self.has_value_changed("supplier"):
			frappe.throw(_("Customer and Supplier cannot be changed after submission."))
	
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
		"""Check for overlapping active agreements for same customer-supplier."""
		if self.docstatus != 0:
			return
		
		overlapping = frappe.db.sql("""
			SELECT name, valid_from, valid_to
			FROM `tabAgreement`
			WHERE customer = %s
			  AND supplier = %s
			  AND docstatus = 1
			  AND name != %s
			  AND (
			      (valid_from <= %s AND valid_to >= %s)
			      OR (valid_from <= %s AND valid_to >= %s)
			      OR (valid_from >= %s AND valid_to <= %s)
			  )
		""", (
			self.customer,
			self.supplier,
			self.name,
			self.valid_from, self.valid_from,
			self.valid_to, self.valid_to,
			self.valid_from, self.valid_to
		), as_dict=True)
		
		if overlapping:
			agreement_names = ", ".join([d.name for d in overlapping])
			frappe.throw(
				_("Active agreement exists for this customer-supplier combination in the same date range: {0}").format(agreement_names),
				title=_("Overlapping Agreement")
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
		"""İptal edildiğinde status güncelle."""
		self.update_status()


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
			
			# Status değiştiyse kaydet
			if old_status != doc.status:
				doc.db_set("status", doc.status, update_modified=False)
				updated_count += 1
				frappe.logger().info(f"Agreement {doc.name} status güncellendi: {old_status} -> {doc.status}")
			
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
