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


