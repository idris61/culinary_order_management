import frappe
from frappe import whitelist
from frappe.utils.pdf import get_pdf
from frappe.utils import getdate, formatdate


@whitelist()
def create_proforma_invoice(parent_so_name):
    """Ana SO'dan otomatik proforma oluştur"""
    try:
        parent_so = frappe.get_doc("Sales Order", parent_so_name)
        
        # Zaten proforma var mı kontrol et
        existing = frappe.get_all("Proforma Invoice", 
            filters={"source_sales_order": parent_so_name},
            limit=1
        )
        if existing:
            # Proforma mevcut; PDF ekli mi kontrol et, yoksa oluştur
            existing_name = existing[0].name
            filename = f"Proforma_{parent_so_name}.pdf"
            attached = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": "Sales Order",
                    "attached_to_name": parent_so_name,
                    "file_name": filename,
                },
                limit=1,
            )
            if not attached:
                try:
                    generate_and_attach_proforma_pdf(existing_name, parent_so_name)
                except Exception as e:
                    frappe.log_error(f"Mevcut proforma için PDF oluşturma hatası: {str(e)}", "Proforma PDF Missing - Recreate")
                    raise
            return existing_name
        
        # Child SO'ları getir
        child_sos = frappe.get_all("Sales Order", 
            filters={"source_web_so": parent_so_name},
            fields=["name", "company"]
        )
        
        if not child_sos:
            frappe.throw("Child Sales Orders bulunamadı. Önce siparişi böl ve yönlendirin.")
        
        # Proforma oluştur
        proforma = frappe.new_doc("Proforma Invoice")
        proforma.customer = parent_so.customer
        proforma.source_sales_order = parent_so_name
        proforma.invoice_date = frappe.utils.today()
        proforma.due_date = frappe.utils.add_days(proforma.invoice_date, 30)
        
        # Child SO'ların itemlerini birleştir
        grand_total = 0
        for child_so in child_sos:
            child_items = frappe.get_doc("Sales Order", child_so.name).items
            for item in child_items:
                proforma.append("items", {
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "qty": item.qty,
                    "rate": item.rate,
                    "amount": item.amount,
                    "supplier_company": child_so.company
                })
                grand_total += item.amount
        
        proforma.grand_total = grand_total
        proforma.insert(ignore_permissions=True)
        proforma.submit()
        
        # PDF oluştur ve attach et
        pdf_result = generate_and_attach_proforma_pdf(proforma.name, parent_so_name)
        
        return proforma.name
        
    except Exception as e:
        frappe.log_error(f"Proforma Invoice oluşturma hatası: {str(e)}", "Proforma Creation Error")
        raise


def generate_and_attach_proforma_pdf(proforma_name, parent_so_name):
    """Proforma PDF oluştur ve Sales Order'a attach et"""
    try:
        proforma = frappe.get_doc("Proforma Invoice", proforma_name)
        parent_so = frappe.get_doc("Sales Order", parent_so_name)
        customer = frappe.get_doc("Customer", proforma.customer)
        company = frappe.get_doc("Company", parent_so.company)
        
        # Items'ı şirket bazında grupla
        items_by_company = {}
        for item in proforma.items:
            company_name = item.supplier_company
            if company_name not in items_by_company:
                items_by_company[company_name] = []
            items_by_company[company_name].append(item)

        # Tarihleri stringe çevir
        today_str = formatdate(frappe.utils.nowdate(), "dd.MM.yyyy")
        due_date_str = formatdate(getdate(proforma.due_date), "dd.MM.yyyy") if proforma.due_date else ""
        delivery_date_str = formatdate(getdate(parent_so.delivery_date), "dd.MM.yyyy") if getattr(parent_so, "delivery_date", None) else "TBD"

        # PDF template render et
        html_content = frappe.get_template("culinary_order_management/templates/proforma_template.html").render({
            "proforma": proforma,
            "customer": customer,
            "company": company,
            "parent_so": parent_so,
            "items_by_company": items_by_company,
            "today_str": today_str,
            "due_date_str": due_date_str,
            "delivery_date_str": delivery_date_str,
            "taxes": parent_so.taxes if hasattr(parent_so, 'taxes') else []
        })
        
        # PDF oluştur
        pdf_content = get_pdf(html_content)
        
        # Ana Sales Order'a attach et
        filename = f"Proforma_{proforma.source_sales_order}.pdf"
        
        file_doc = frappe.get_doc({
            'doctype': 'File',
            'file_name': filename,
            'content': pdf_content,
            'is_private': 0,
            'attached_to_doctype': 'Sales Order',
            'attached_to_name': parent_so_name
        })
        
        file_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        file_url = file_doc.file_url or file_doc.file_name
        frappe.msgprint(f"Proforma PDF Sales Order'a eklendi: {filename}")
        return file_url
        
    except Exception as e:
        frappe.log_error(f"Proforma PDF oluşturma hatası: {str(e)}", "Proforma PDF Error")
        raise


@whitelist()
def create_proforma_for_order(parent_so_name):
    """Sales Order butonundan çağırılan API"""
    try:
        proforma_name = create_proforma_invoice(parent_so_name)
        return {"status": "success", "proforma_name": proforma_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}