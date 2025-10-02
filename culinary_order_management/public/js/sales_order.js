frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.company === "Culinary") {
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
    }
});


