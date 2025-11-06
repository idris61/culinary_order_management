// Agreement Form Script
frappe.ui.form.on('Agreement', {
	before_submit: function(frm) {
		// Submit edilmeden önce aktif anlaşma kontrolü
		if (frm.doc.customer && frm.doc.supplier) {
			return new Promise((resolve, reject) => {
				frappe.call({
					method: 'culinary_order_management.culinary_order_management.doctype.agreement.agreement.check_active_agreement',
					args: {
						customer: frm.doc.customer,
						supplier: frm.doc.supplier,
						current_agreement: frm.doc.name
					},
					async: false,
					callback: function(r) {
						if (r.message && r.message.has_active) {
							// Aktif anlaşma var - dialog göster
							const agreements = r.message.agreements;
							const agreement_list = agreements.map(a => 
								`${a.name} (${a.valid_from} - ${a.valid_to})`
							).join('<br>');
							
							frappe.confirm(
								`<strong>Bu müşteri-tedarikçi için aktif anlaşma mevcut:</strong><br><br>${agreement_list}<br><br>Mevcut anlaşmayı iptal edip yeni anlaşmayı onaylamak istiyor musunuz?`,
								() => {
									// Evet - eski anlaşmayı cancel et, yeni anlaşmayı submit et
									frappe.call({
										method: 'culinary_order_management.culinary_order_management.doctype.agreement.agreement.replace_agreement',
										args: {
											old_agreement: agreements[0].name,
											new_agreement: frm.doc.name
										},
										freeze: true,
										freeze_message: __('İşleniyor...'),
										callback: function(r) {
											if (r.message && r.message.success) {
												frappe.show_alert({
													message: r.message.message,
													indicator: 'green'
												});
												// Sayfa reload - tekrar submit etme
												setTimeout(() => {
													frm.reload_doc();
												}, 500);
											}
										},
										error: function(r) {
											frappe.msgprint({
												title: __('Hata'),
												indicator: 'red',
												message: r.message || 'İşlem başarısız oldu'
											});
										}
									});
									// Submit işlemini durdur (replace_agreement içinde zaten submit ediliyor)
									reject();
								},
								() => {
									// Hayır - submit işlemini iptal et
									frappe.show_alert({
										message: __('Anlaşma taslak olarak kaldı'),
										indicator: 'orange'
									});
									reject();
								}
							);
						} else {
							// Aktif anlaşma yok - normal submit devam etsin
							resolve();
						}
					},
					error: function() {
						reject();
					}
				});
			});
		}
	}
});
