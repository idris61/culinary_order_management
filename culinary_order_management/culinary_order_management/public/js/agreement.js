// Amaç: Agreement → Agreement Items tablosunda "item_code" alanını
// seçili tedarikçiye (supplier) göre filtrelemek ve tedarikçi değiştiğinde
// kalemlerdeki ürün alanlarını temizleyerek veri tutarlılığını korumak.

function bind_item_supplier_filter(frm) {
	const grid = frm.fields_dict['agreement_items']?.grid;
	if (!grid) return;
	const df = grid.get_field('item_code');
	if (!df) return;
	df.get_query = function(doc) {
		const supplier = doc.supplier || null;
		if (!supplier) {
			// Tedarikçi seçilmeden ürün listelenmesin
			return { filters: { name: ["in", []] } };
		}
		return {
			query: 'culinary_order_management.culinary_order_management.api.item_query_by_supplier',
			filters: { supplier }
		};
	};
	frm.refresh_field('agreement_items');
}

frappe.ui.form.on('Agreement', {
	refresh(frm) {
		bind_item_supplier_filter(frm);
	},
	supplier(frm) {
		// Tedarikçi değişince seçili ürün alanlarını sıfırla
		(frm.doc.agreement_items || []).forEach(row => {
			row.item_code = "";
			row.price_list_rate = null;
			row.uom = null;
		});
		frm.refresh_field('agreement_items');
		bind_item_supplier_filter(frm);
	}
});

// Agreement Item’da item seçilince: isim, UOM ve fiyatı doldur
frappe.ui.form.on('Agreement Item', {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;

        // Item Name fetch_from ile de gelir; yine de garanti altına alalım
        frappe.db.get_value('Item', row.item_code, ['item_name', 'stock_uom']).then(r => {
            if (r && r.message) {
                if (!row.item_name) frappe.model.set_value(cdt, cdn, 'item_name', r.message.item_name);
                if (!row.uom) frappe.model.set_value(cdt, cdn, 'uom', r.message.stock_uom);
            }
        });

        // Standart satış fiyatını çek (Standard Selling, müşterinin para birimi öncelik)
        const currency = row.currency || (frm.doc.default_currency || frm.doc.currency) || 'EUR';
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Item Price',
                filters: {
                    price_list: 'Standard Selling',
                    item_code: row.item_code,
                    currency: currency
                },
                fields: ['price_list_rate'],
                limit_page_length: 1
            },
        }).then(res => {
            const rate = (res.message && res.message[0] && res.message[0].price_list_rate) || 0;
            if (rate) {
                frappe.model.set_value(cdt, cdn, 'price_list_rate', rate);
                if (!row.currency) frappe.model.set_value(cdt, cdn, 'currency', currency);
            }
        });
    },

    // UOM seçimi için yalnız item’a tanımlı UOM’leri listele
    uom(frm, cdt, cdn) {
        // no-op; get_query aşağıda tanımlı
    }
});

// Grid alan sorguları
frappe.ui.form.on('Agreement', {
    onload(frm) {
        const grid = frm.fields_dict['agreement_items']?.grid;
        if (!grid) return;
        const uom_df = grid.get_field('uom');
        if (uom_df) {
            uom_df.get_query = function(doc, cdt, cdn) {
                const row = locals[cdt][cdn];
                if (!row || !row.item_code) return {};
                return {
                    query: 'frappe.desk.search.search_link',
                    filters: {
                        doctype: 'UOM',
                        reference_doctype: 'Item',
                        reference_name: row.item_code
                    }
                };
            }
        }
    }
});




