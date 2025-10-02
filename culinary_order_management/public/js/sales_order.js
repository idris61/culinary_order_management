frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        if (frm.doc.company === "Culinary") {
            // Böl ve Yönlendir butonu - sadece submitted SO'larda
            if (frm.doc.docstatus === 1) {
                frm.add_custom_button(__('Böl ve Yönlendir'), () => {
                    frappe.call({
                        method: 'culinary_order_management.culinary_order_management.sales_order_hooks.split_order_to_companies_api',
                        args: { name: frm.doc.name },
                        freeze: true,
                        freeze_message: __('Sipariş ayrıştırılıyor...'),
                    }).then(() => {
                        frappe.msgprint(__('Sipariş başarıyla ayrıştırıldı ve yönlendirildi.'));
                        frm.reload_doc();
                    });
                }, __('Aksiyonlar'));
            }
            
            // Proforma Oluştur butonu - her zaman göster
            frm.add_custom_button(__('Proforma Oluştur'), () => {
                if (frm.doc.docstatus !== 1) {
                    frappe.msgprint(__('Önce siparişi onaylayın.'));
                    return;
                }
                frappe.call({
                    method: 'culinary_order_management.culinary_order_management.proforma_hooks.create_proforma_for_order',
                    args: { parent_so_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Proforma oluşturuluyor...'),
                }).then((r) => {
                    if (r.message && r.message.status === 'success') {
                        frappe.msgprint(__('Proforma başarıyla oluşturuldu ve PDF Sales Order\'a eklendi.'));
                        frm.reload_doc();
                    } else if (r.message && r.message.status === 'error') {
                        frappe.msgprint(__('Proforma oluşturma hatası: {0}', [r.message.message || 'Bilinmeyen hata']));
                    }
                }).catch((e) => {
                    frappe.msgprint(__('Proforma oluşturma hatası: {0}', [e.message || 'Bilinmeyen hata']));
                });
            }, __('Faturalama'));
        }
    }
});