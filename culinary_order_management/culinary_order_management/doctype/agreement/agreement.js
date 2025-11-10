// Agreement Form Script
frappe.ui.form.on('Agreement', {
	refresh: function(frm) {
		// Sadece submitted ve aktif agreement'lar için bilgilendirme
		if (frm.doc.docstatus === 1 && frm.doc.status === 'Active') {
			// Fiyat değişikliği olan ürünleri tespit et (bilgilendirme amaçlı)
			let price_changed_count = 0;
			
			if (frm.doc.agreement_items) {
				frm.doc.agreement_items.forEach(function(item) {
					let original = parseFloat(item.price_list_rate) || 0;
					let current = parseFloat(item.current_agreement_rate) || 0;
					if (Math.abs(current - original) > 0.01 && current > 0) {
						price_changed_count++;
					}
				});
			}
			
			if (price_changed_count > 0) {
				// Bilgilendirme indicator (aksiyon gerektirmez)
				frm.dashboard.add_indicator(__('Fiyat Değişikliği: {0} ürün', [price_changed_count]), 'blue');
				
				// Bilgilendirme butonu - Fiyat değişikliklerini göster
				frm.add_custom_button(__('Fiyat Değişikliklerini Gör'), function() {
					// Fiyat değişikliklerini listele
					let html = '<table class="table table-bordered" style="margin-top: 10px;"><thead><tr>' +
							  '<th>Ürün</th><th>Original Price</th><th>Current Price (Portal)</th><th>Fark</th>' +
							  '</tr></thead><tbody>';
					
					let changes = [];
					frm.doc.agreement_items.forEach(function(item) {
						let original = parseFloat(item.price_list_rate) || 0;
						let current = parseFloat(item.current_agreement_rate) || 0;
						
						if (Math.abs(current - original) > 0.01 && current > 0) {
							let diff = current - original;
							let diff_pct = (diff / original * 100).toFixed(2);
							let color = diff > 0 ? 'red' : 'green';
							
							html += `<tr>
								<td><strong>${item.item_code}</strong><br><small>${item.item_name || ''}</small></td>
								<td>${original.toFixed(2)} ${item.currency || 'EUR'}</td>
								<td style="font-weight: bold;">${current.toFixed(2)} ${item.currency || 'EUR'}</td>
								<td style="color: ${color}; font-weight: bold;">${diff > 0 ? '+' : ''}${diff.toFixed(2)} (${diff > 0 ? '+' : ''}${diff_pct}%)</td>
							</tr>`;
							
							changes.push({item_code: item.item_code, diff: diff});
						}
					});
					
					html += '</tbody></table>';
					
					if (changes.length > 0) {
						html = '<div style="margin-bottom: 15px;">' +
							   '<p><strong>ℹ️ BİLGİLENDİRME:</strong></p>' +
							   '<p>Portal fiyatları <strong>zaten güncel</strong>. Aşağıdaki farklar Agreement yapıldıktan sonra oluşan fiyat değişikliklerini gösterir.</p>' +
							   '<p><em>Agreement belgesi (tarihsel kayıt) değişmez, portal her zaman güncel fiyatları gösterir.</em></p>' +
							   '</div>' + html;
						
						frappe.msgprint({
							title: __('Fiyat Değişiklikleri (Bilgilendirme)'),
							indicator: 'blue',
							message: html,
							wide: true
						});
					} else {
						frappe.msgprint({
							title: __('Fiyat Durumu'),
							indicator: 'green',
							message: '<p>✅ Tüm fiyatlar Agreement yapıldığından beri değişmedi.</p>'
						});
					}
				}, __('Bilgi'));
			} else {
				// Fiyatlar güncel
				frm.dashboard.add_indicator(__('Fiyatlar Güncel'), 'green');
			}
			
			// Price History silme butonu
			if (frm.doc.price_history && frm.doc.price_history.length > 0) {
				frm.add_custom_button(__('Price History Temizle'), function() {
					frappe.confirm(
						__('Tüm fiyat değişiklik geçmişi silinecek. Bu işlem geri alınamaz!<br><br>Devam etmek istiyor musunuz?'),
						() => {
							frappe.call({
								method: 'culinary_order_management.culinary_order_management.agreement.clear_price_history',
								args: {
									agreement_name: frm.doc.name
								},
								freeze: true,
								freeze_message: __('Temizleniyor...'),
								callback: function(r) {
									if (r.message && r.message.success) {
										frappe.show_alert({
											message: __('✅ {0} kayıt silindi', [r.message.deleted_count]),
											indicator: 'green'
										});
										frm.reload_doc();
									}
								}
							});
						}
					);
				}, __('İşlemler'));
			}
		}
	},
	
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
