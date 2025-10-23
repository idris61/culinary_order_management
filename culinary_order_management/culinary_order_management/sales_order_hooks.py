import frappe
import re
from frappe.model.naming import make_autoname
from frappe.utils import flt
from frappe.model.document import Document
from frappe import whitelist


def split_order_to_companies(doc, method):
    """
    Satış siparişi submit edildikten sonra ürünlere göre marka/mutfak şirketlerine ayrıştır
    
    Args:
        doc: Sales Order doc
        method: Event method name (after_submit)
    """
    # Sadece Culinary şirketi siparişleri için çalışsın
    if doc.company != "Culinary":
        return
    
    try:
        # Debug: Başlangıç bilgisi
        frappe.log_error(f"Split Order başlıyor - SO: {doc.name}, Items: {len(doc.items)}", "Split Order Debug")
        
        # Teslimat adresi (varsa)
        customer_address = get_customer_delivery_address(doc.customer, doc.shipping_address_name)
        
        # Ürünleri gruplandır (mutfak/supplier)
        kitchen_items, supplier_items = group_items_by_type(doc.items)
        
        # Debug: Gruplama sonucu
        print(f"🔵 Gruplama - Mutfak: {len(kitchen_items)}, Supplier: {len(supplier_items)}")
        frappe.log_error(f"🔵 Gruplama - Mutfak: {len(kitchen_items)}, Supplier: {len(supplier_items)}", "Split Order Debug")
        
        # Debug: Item detayları
        for i, item in enumerate(doc.items):
            is_kitchen = is_kitchen_item(item.item_code)
            supplier = get_item_brand(item.item_code)  # Artık supplier döndürüyor
            print(f"🔵 Item {i+1}: {item.item_code} - Kitchen: {is_kitchen}, Supplier: {supplier}")
            frappe.log_error(f"🔵 Item {i+1}: {item.item_code} - Kitchen: {is_kitchen}, Supplier: {supplier}", "Split Order Debug")
        
        # Mutfak siparişlerini oluştur
        if kitchen_items:
            print(f"🟢 Mutfak items var: {len(kitchen_items)}")
            frappe.log_error(f"🟢 Mutfak items var: {len(kitchen_items)}", "Split Order Debug")
            
            customer_pin = getattr(customer_address, "pincode", None)
            print(f"🔵 Customer PIN: {customer_pin}")
            frappe.log_error(f"🔵 Customer PIN: {customer_pin}", "Split Order Debug")
            
            kitchen_company = find_nearest_kitchen(customer_pin, doc.customer)
            print(f"🔵 Kitchen Company: {kitchen_company}")
            frappe.log_error(f"🔵 Kitchen Company: {kitchen_company}", "Split Order Debug")
            
            if kitchen_company and not child_order_exists(doc, kitchen_company):
                print(f"🟢 Creating Kitchen SO for: {kitchen_company}")
                frappe.log_error(f"🟢 Creating Kitchen SO for: {kitchen_company}", "Split Order Debug")
                create_company_sales_order(doc, kitchen_items, kitchen_company, "kitchen")
            else:
                print(f"❌ Kitchen SO not created - Company: {kitchen_company}, Exists: {child_order_exists(doc, kitchen_company) if kitchen_company else 'N/A'}")
                frappe.log_error(f"❌ Kitchen SO not created - Company: {kitchen_company}, Exists: {child_order_exists(doc, kitchen_company) if kitchen_company else 'N/A'}", "Split Order Debug")
        else:
            print(f"❌ No kitchen items found")
            frappe.log_error(f"❌ No kitchen items found", "Split Order Debug")
        
        # Supplier siparişlerini oluştur
        print(f"🔵 Processing {len(supplier_items)} supplier groups")
        frappe.log_error(f"🔵 Processing {len(supplier_items)} supplier groups", "Split Order Debug")
        
        for supplier_name, items in supplier_items.items():
            print(f"🔵 Processing supplier: {supplier_name} with {len(items)} items")
            frappe.log_error(f"🔵 Processing supplier: {supplier_name} with {len(items)} items", "Split Order Debug")
            
            supplier_company = get_brand_company(supplier_name)
            print(f"🔵 Supplier Company for {supplier_name}: {supplier_company}")
            frappe.log_error(f"🔵 Supplier Company for {supplier_name}: {supplier_company}", "Split Order Debug")
            
            if supplier_company and not child_order_exists(doc, supplier_company):
                print(f"🟢 Creating Supplier SO for: {supplier_company}")
                frappe.log_error(f"🟢 Creating Supplier SO for: {supplier_company}", "Split Order Debug")
                create_company_sales_order(doc, items, supplier_company, supplier_name)
            else:
                print(f"❌ Supplier SO not created for {supplier_name} - Company: {supplier_company}, Exists: {child_order_exists(doc, supplier_company) if supplier_company else 'N/A'}")
                frappe.log_error(f"❌ Supplier SO not created for {supplier_name} - Company: {supplier_company}, Exists: {child_order_exists(doc, supplier_company) if supplier_company else 'N/A'}", "Split Order Debug")
        
        # Proforma oluştur
        try:
            from culinary_order_management.culinary_order_management.proforma_hooks import create_proforma_invoice
            create_proforma_invoice(doc.name)
        except Exception as proforma_error:
            frappe.log_error(f"Proforma oluşturma hatası: {str(proforma_error)}", "Proforma Creation Error")
        
    except Exception as e:
        frappe.log_error(f"Sipariş ayrıştırma hatası: {str(e)}", "Culinary Order Split Error")


@whitelist()
def split_order_to_companies_api(name: str):
    """Sales Order formundaki butondan manuel tetikleme.
    Doc submit edilmiş olmalı.
    """
    try:
        print(f"🔵 API Called - SO Name: {name}")
        frappe.log_error(f"🔵 API Called - SO Name: {name}", "Split Order API Debug")
        
        doc = frappe.get_doc("Sales Order", name)
        print(f"🔵 SO Loaded - Status: {doc.docstatus}, Company: {doc.company}, Items: {len(doc.items)}")
        frappe.log_error(f"🔵 SO Loaded - Status: {doc.docstatus}, Company: {doc.company}, Items: {len(doc.items)}", "Split Order API Debug")
        
        if doc.docstatus != 1:
            error_msg = "Sipariş onaylanmış olmalı (Submitted)."
            print(f"❌ Error: {error_msg}")
            frappe.log_error(f"❌ Error: {error_msg}", "Split Order API Debug")
            return {"ok": False, "error": error_msg}
        
        if doc.company != "Culinary":
            error_msg = "Sadece Culinary şirketi siparişleri bölünebilir."
            print(f"❌ Error: {error_msg}")
            frappe.log_error(f"❌ Error: {error_msg}", "Split Order API Debug")
            return {"ok": False, "error": error_msg}
        
        print(f"🟢 Starting split_order_to_companies for: {name}")
        frappe.log_error(f"🟢 Starting split_order_to_companies for: {name}", "Split Order API Debug")
        
        split_order_to_companies(doc, "after_submit")
        
        print(f"✅ Split Order Completed for: {name}")
        frappe.log_error(f"✅ Split Order Completed for: {name}", "Split Order API Debug")
        
        return {"ok": True, "message": "Sipariş başarıyla ayrıştırıldı."}
        
    except Exception as e:
        error_msg = f"API Exception: {str(e)}"
        print(f"💥 {error_msg}")
        frappe.log_error(f"💥 {error_msg}", "Split Order API Debug")
        return {"ok": False, "error": str(e)}


def get_customer_delivery_address(customer, shipping_address_name):
    """Müşterinin teslimat adresini getir.

    Yalnızca Sales Order üzerindeki `shipping_address_name` kullanılır.
    (Adres doctype importu bazı ortamlarda kolon hatasına yol açtığından
    fallback kapatıldı.)
    """
    if shipping_address_name:
        try:
            return frappe.get_doc("Address", shipping_address_name)
        except Exception:
            return None
    return None


def group_items_by_type(items):
    """Ürünleri mutfak/supplier gruplarına ayır"""
    kitchen_items = []
    supplier_items = {}
    
    for item in items:
        if is_kitchen_item(item.item_code):
            kitchen_items.append(item)
        else:
            # Supplier bilgisini al
            supplier = get_item_brand(item.item_code)  # Artık supplier döndürüyor
            if supplier:
                if supplier not in supplier_items:
                    supplier_items[supplier] = []
                supplier_items[supplier].append(item)
    
    return kitchen_items, supplier_items


def is_kitchen_item(item_code):
    """Ürünün mutfak ürünü olup olmadığını kontrol et"""
    val = frappe.db.get_value("Item", item_code, "is_kitchen_item")
    return bool(val)


def get_item_brand(item_code):
    """Ürünün markasını Supplier Items tablosundan getir"""
    try:
        # Supplier Items tablosundan supplier bilgisini al
        supplier_items = frappe.get_all("Item Supplier", 
            filters={"parent": item_code},
            fields=["supplier"],
            limit=1
        )
        
        if supplier_items:
            supplier = supplier_items[0].supplier
            print(f"🔵 Item {item_code} supplier: {supplier}")
            frappe.log_error(f"🔵 Item {item_code} supplier: {supplier}", "Split Order Debug")
            return supplier
        
        print(f"❌ No supplier found for item: {item_code}")
        frappe.log_error(f"❌ No supplier found for item: {item_code}", "Split Order Debug")
        return None
        
    except Exception as e:
        print(f"💥 Error getting supplier for item {item_code}: {str(e)}")
        frappe.log_error(f"💥 Error getting supplier for item {item_code}: {str(e)}", "Split Order Debug")
        return None


def find_nearest_kitchen(customer_pincode, customer_name):
    """Müşteri posta koduna göre mutfak şirketini bul.

    Basit kural: Şirket adı "Mutfak -" ile başlıyorsa ve varsayılan adres posta kodu eşitse eşleşir.
    Eşleşme yoksa ilk uygun mutfak şirketi geri döner.
    """
    if not customer_pincode:
        return None

    from frappe.contacts.doctype.address.address import get_default_address

    kitchen_companies = frappe.get_all(
        "Company",
        filters={"name": ["like", "Mutfak - %"]},
        pluck="name",
    )

    # Tam posta kodu eşleşmesi
    for company in kitchen_companies:
        addr_name = get_default_address("Company", company)
        if not addr_name:
            continue
        addr = frappe.db.get_value(
            "Address", addr_name, ["pincode"], as_dict=True
        )
        if addr and addr.get("pincode") == customer_pincode:
            return company

    # Fallback: ilk mutfak şirketi
    if kitchen_companies:
        return kitchen_companies[0]

    frappe.log_error(
        f"Mutfak bulunamadı - müşteri: {customer_name}, posta kodu: {customer_pincode}",
        "Kitchen Routing",
    )
    return None


def get_brand_company(supplier_name):
    """Supplier için varsayılan şirketi getir"""
    try:
        print(f"🔵 Getting company for supplier: {supplier_name}")
        frappe.log_error(f"🔵 Getting company for supplier: {supplier_name}", "Split Order Debug")
        
        # 1) Supplier adı ile eşleşen Company var mı?
        if frappe.db.exists("Company", supplier_name):
            print(f"🟢 Company exists with supplier name: {supplier_name}")
            frappe.log_error(f"🟢 Company exists with supplier name: {supplier_name}", "Split Order Debug")
            return supplier_name
        
        # 2) Supplier adını Company adıyla eşleştir (ör: "Edel Weiss" -> "Edel Weiss Company")
        company_variations = [
            supplier_name,
            f"{supplier_name} Company",
            f"{supplier_name} GmbH",
            f"{supplier_name} AG",
            f"{supplier_name} Ltd",
            f"{supplier_name} Limited"
        ]
        
        for variation in company_variations:
            if frappe.db.exists("Company", variation):
                print(f"🟢 Company found with variation: {variation}")
                frappe.log_error(f"🟢 Company found with variation: {variation}", "Split Order Debug")
                return variation
        
        print(f"❌ No company found for supplier: {supplier_name}")
        frappe.log_error(f"❌ No company found for supplier: {supplier_name}", "Split Order Debug")
        return None
        
    except Exception as e:
        print(f"💥 Error getting company for supplier {supplier_name}: {str(e)}")
        frappe.log_error(f"💥 Error getting company for supplier {supplier_name}: {str(e)}", "Split Order Debug")
        return None


def _generate_po_number(parent_so, target_company):
    """Parent SO'dan base PO numarasını çıkar ve company ile birleştir"""
    base_po = None
    if hasattr(parent_so, "woocommerce_id") and parent_so.woocommerce_id:
        base_po = parent_so.woocommerce_id
    elif hasattr(parent_so, "po_no") and parent_so.po_no:
        base_po = parent_so.po_no
    else:
        # SO adından number kısmını çıkar (WEB1-027703 -> 027703 -> 27703)
        match = re.search(r'-(\d+)$', parent_so.name)
        if match:
            base_po = match.group(1).lstrip('0') or match.group(1)
    
    company_abbr = _company_prefix(target_company)
    return f"{base_po}-{company_abbr}"


def _prepare_sales_order_base(parent_so, target_company):
    """Yeni SO dokümanı oluştur ve temel bilgileri doldur"""
    new_so = frappe.new_doc("Sales Order")
    new_so.company = target_company
    new_so.customer = parent_so.customer
    new_so.transaction_date = parent_so.transaction_date
    new_so.delivery_date = parent_so.delivery_date or parent_so.transaction_date
    new_so.shipping_address_name = parent_so.shipping_address_name
    new_so.customer_address = parent_so.customer_address
    new_so.po_no = _generate_po_number(parent_so, target_company)
    return new_so


def _copy_items_to_sales_order(new_so, items):
    """Item'ları yeni SO'ya kopyala"""
    for item in items:
        item_row = new_so.append("items")
        item_row.item_code = item.item_code
        item_row.item_name = item.item_name
        item_row.qty = item.qty
        item_row.rate = item.rate
        item_row.amount = item.amount
        item_row.description = item.description


def _rename_sales_order_with_prefix(new_so, target_company):
    """SO'yu şirket prefix'i ile yeniden adlandır"""
    prefix = _company_prefix(target_company)
    try:
        target_name = make_autoname(f"{prefix}-.#####")
        if target_name and target_name != new_so.name:
            frappe.rename_doc("Sales Order", new_so.name, target_name, force=True)
            new_so.name = target_name
    except Exception:
        pass  # Varsayılan isim kalabilir


def create_company_sales_order(parent_so, items, target_company, order_type):
    """Hedef şirket için Sales Order oluştur"""
    try:
        print(f"🟢 Creating Company SO - Target: {target_company}, Items: {len(items)}, Type: {order_type}")
        frappe.log_error(f"🟢 Creating Company SO - Target: {target_company}, Items: {len(items)}, Type: {order_type}", "Split Order Debug")
        
        # SO oluştur ve temel bilgileri doldur
        new_so = _prepare_sales_order_base(parent_so, target_company)
        print(f"🔵 SO Base prepared: {new_so.name}")
        frappe.log_error(f"🔵 SO Base prepared: {new_so.name}", "Split Order Debug")
        
        # Item'ları kopyala
        _copy_items_to_sales_order(new_so, items)
        print(f"🔵 Items copied: {len(new_so.items)}")
        frappe.log_error(f"🔵 Items copied: {len(new_so.items)}", "Split Order Debug")
        
        # Kaydet
        new_so.insert(ignore_permissions=True)
        print(f"🔵 SO Inserted: {new_so.name}")
        frappe.log_error(f"🔵 SO Inserted: {new_so.name}", "Split Order Debug")
        
        # Yeniden adlandır
        _rename_sales_order_with_prefix(new_so, target_company)
        print(f"🔵 SO Renamed: {new_so.name}")
        frappe.log_error(f"🔵 SO Renamed: {new_so.name}", "Split Order Debug")
        
        # Vergi/tutarları hesapla ve submit et
        new_so.calculate_taxes_and_totals()
        new_so.submit()
        print(f"✅ SO Submitted: {new_so.name}")
        frappe.log_error(f"✅ SO Submitted: {new_so.name}", "Split Order Debug")
        
        # Referans bilgisini kaydet
        frappe.db.set_value("Sales Order", new_so.name, "source_web_so", parent_so.name)
        print(f"🔵 Reference saved: {new_so.name} -> {parent_so.name}")
        frappe.log_error(f"🔵 Reference saved: {new_so.name} -> {parent_so.name}", "Split Order Debug")
            
    except Exception as e:
        error_msg = f"Hedef şirket SO oluşturamadı - şirket: {target_company}, hata: {str(e)}"
        print(f"💥 {error_msg}")
        frappe.log_error(error_msg, "Company SO Creation Error")
        raise


def child_order_exists(parent_so: Document, company: str) -> bool:
    """Aynı parent SO name ve şirket için çocuk SO var mı?"""
    source_id = parent_so.name  # Child SO'larda parent_so.name kaydediliyor
    return bool(
        frappe.get_all(
            "Sales Order",
            filters={"source_web_so": source_id, "company": company},
            limit=1,
        )
    )


def _slugify_prefix(value: str) -> str:
    """Brand adını güvenli bir prefix'e dönüştür.

    Sadece harf/rakam ve '-' içerir, büyük harfe çevrilir, boşluklar '-'.
    Çok uzun adlar kırpılır.
    """
    if not value:
        return "BRAND"
    value = value.strip()
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^A-Za-z0-9\-]", "", value)
    return (value.upper() or "BRAND")[:30]


def _company_prefix(company_name: str) -> str:
    """Şirket için adlandırma ön eki döndür (Company.abbr varsa onu kullan).

    Her şirket kendi serisini tutar; örn: "MBER-00001".
    """
    abbr = None
    try:
        abbr = frappe.db.get_value("Company", company_name, "abbr")
    except Exception:
        abbr = None
    if abbr:
        return _slugify_prefix(abbr)
    return _slugify_prefix(company_name)
