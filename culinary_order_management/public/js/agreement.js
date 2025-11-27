// Local helpers (avoid frappe.utils dependency in client runtime)
const toFloat = (v) => {
    const n = parseFloat(v);
    return isNaN(n) ? 0 : n;
};
const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

frappe.ui.form.on('Agreement', {
    refresh(frm) {
        const grid = frm.fields_dict.agreement_items && frm.fields_dict.agreement_items.grid;
        if (!grid) return;
        const itemCodeDf = grid.get_field('item_code');
        if (itemCodeDf && !itemCodeDf.__formatter_overridden) {
            itemCodeDf.formatter = function(value) {
                return value || '';
            };
            itemCodeDf.__formatter_overridden = true;
        }

        // Ürün aramasını seçili tedarikçiye göre filtrele
        grid.get_field('item_code').get_query = function() {
            return {
                query: 'erpnext.controllers.queries.item_query',
                filters: {
                    supplier: frm.doc.supplier || undefined,
                    is_sales_item: 1
                }
            };
        };

        // Quick access to generated Price List
        if (frm.doc.price_list) {
            frm.add_custom_button(__('Open Price List'), () => {
                frappe.set_route('Form', 'Price List', frm.doc.price_list);
            });
        }
    },
    discount_rate(frm) {
        // İndirim oranı değiştiğinde tüm satırlarda anlaşma fiyatını güncelle
        apply_agreement_discount(frm);
    },
    customer(frm) {
        // müşteri değiştiğinde tabloyu yeniden kurmayız; sadece fiyat hesaplarken kullanılır
    },
    supplier(frm) {
        // Tedarikçi seçildiğinde tüm ürünleri tabloya getir
        if (!frm.doc.supplier) return;
        frm.clear_table('agreement_items');
        // set_query tekrar uygula (yeni satırlarda da tedarikçi filtreli olsun)
        const grid = frm.fields_dict.agreement_items && frm.fields_dict.agreement_items.grid;
        if (grid) {
            grid.get_field('item_code').get_query = function() {
                return {
                    query: 'erpnext.controllers.queries.item_query',
                    filters: {
                        supplier: frm.doc.supplier || undefined,
                        is_sales_item: 1
                    }
                };
            };
        }
        frappe.call({
            method: 'culinary_order_management.culinary_order_management.agreement.get_supplier_items_with_standard_prices',
            args: {
                supplier: frm.doc.supplier,
                currency: (frm.doc.agreement_items && frm.doc.agreement_items[0] && frm.doc.agreement_items[0].currency) || null,
            },
        }).then(r => {
            (r.message || []).forEach(row => {
                const d = frm.add_child('agreement_items');
                d.item_code = row.item_code;
                d.item_name = row.item_name;
                d.item_group = row.item_group;
                d.kitchen_item = row.kitchen_item ? 1 : 0;
                d.uom = row.uom;
                d.standard_selling_rate = row.standard_selling_rate;
                d.price_list_rate = row.price_list_rate;
                d.currency = row.currency;
            });
            frm.refresh_field('agreement_items');
            // mevcut indirim oranını uygula
            apply_agreement_discount(frm);
        });
    },
    
    before_submit: function(frm) {
        // Önce customer notes modal'ını aç
        return new Promise((resolve, reject) => {
            // Modal dialog oluştur
            const dialog = new frappe.ui.Dialog({
                title: __('Add Customer Note'),
                fields: [
                    {
                        fieldtype: 'Small Text',
                        fieldname: 'customer_note',
                        label: __('Note'),
                        reqd: 0,
                        description: __('You can add a note for the customer before approving the agreement.')
                    }
                ],
                primary_action_label: __('Save and Continue'),
                primary_action: function(values) {
                    // Not varsa custom_customer_note alanına yaz
                    if (values.customer_note && values.customer_note.trim()) {
                        frm.set_value('custom_customer_note', values.customer_note.trim());
                    }
                    
                    dialog.hide();
                    
                    // Modal kapandıktan sonra mevcut aktif anlaşma kontrolünü yap
                    if (frm.doc.customer && frm.doc.supplier) {
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
                                        `<strong>${__('Active agreement exists for this customer-supplier:')}</strong><br><br>${agreement_list}<br><br>${__('Do you want to cancel the existing agreement and approve the new agreement?')}`,
                                        () => {
                                            // Evet - eski anlaşmayı cancel et, yeni anlaşmayı submit et
                                            frappe.call({
                                                method: 'culinary_order_management.culinary_order_management.doctype.agreement.agreement.replace_agreement',
                                                args: {
                                                    old_agreement: agreements[0].name,
                                                    new_agreement: frm.doc.name
                                                },
                                                freeze: true,
                                                freeze_message: __('Processing...'),
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
                                                        title: __('Error'),
                                                        indicator: 'red',
                                                        message: r.message || __('Operation failed')
                                                    });
                                                }
                                            });
                                            // Submit işlemini durdur (replace_agreement içinde zaten submit ediliyor)
                                            reject();
                                        },
                                        () => {
                                            // Hayır - submit işlemini iptal et
                                            frappe.show_alert({
                                                message: __('Agreement remained as draft'),
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
                    } else {
                        // Customer ve supplier yoksa direkt resolve
                        resolve();
                    }
                },
                secondary_action_label: __('Continue (Don\'t Add Note)'),
                secondary_action: function() {
                    // Not eklenmeden devam et, mevcut aktif anlaşma kontrolünü yap
                    dialog.hide();
                    
                    if (frm.doc.customer && frm.doc.supplier) {
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
                                        `<strong>${__('Active agreement exists for this customer-supplier:')}</strong><br><br>${agreement_list}<br><br>${__('Do you want to cancel the existing agreement and approve the new agreement?')}`,
                                        () => {
                                            // Evet - eski anlaşmayı cancel et, yeni anlaşmayı submit et
                                            frappe.call({
                                                method: 'culinary_order_management.culinary_order_management.doctype.agreement.agreement.replace_agreement',
                                                args: {
                                                    old_agreement: agreements[0].name,
                                                    new_agreement: frm.doc.name
                                                },
                                                freeze: true,
                                                freeze_message: __('Processing...'),
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
                                                        title: __('Error'),
                                                        indicator: 'red',
                                                        message: r.message || __('Operation failed')
                                                    });
                                                }
                                            });
                                            // Submit işlemini durdur (replace_agreement içinde zaten submit ediliyor)
                                            reject();
                                        },
                                        () => {
                                            // Hayır - submit işlemini iptal et
                                            frappe.show_alert({
                                                message: __('Agreement remained as draft'),
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
                    } else {
                        // Customer ve supplier yoksa direkt resolve
                        resolve();
                    }
                }
            });
            
            dialog.show();
        });
    }
});

function apply_agreement_discount(frm) {
    const discount = toFloat(frm.doc.discount_rate || 0);
    (frm.doc.agreement_items || []).forEach(d => {
        const base = toFloat(d.standard_selling_rate || 0);
        if (base > 0) {
            const eff = discount ? base * (1.0 - discount / 100.0) : base;
            d.price_list_rate = round2(eff);
        }
    });
    frm.refresh_field('agreement_items');
}
