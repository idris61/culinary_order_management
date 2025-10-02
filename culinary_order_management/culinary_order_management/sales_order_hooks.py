import frappe
import re
from frappe.model.naming import make_autoname
from frappe.utils import flt
from frappe.model.document import Document


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
        # Teslimat adresi (varsa)
        customer_address = get_customer_delivery_address(doc.customer, doc.shipping_address_name)
        
        # Ürünleri gruplandır (mutfak/marka)
        kitchen_items, brand_items = group_items_by_type(doc.items)
        
        # Mutfak siparişlerini oluştur
        if kitchen_items:
            customer_pin = getattr(customer_address, "pincode", None)
            kitchen_company = find_nearest_kitchen(customer_pin, doc.customer)
            if kitchen_company and not child_order_exists(doc.name, kitchen_company):
                create_company_sales_order(doc, kitchen_items, kitchen_company, "kitchen")
        
        # Marka siparişlerini oluştur
        for brand_name, items in brand_items.items():
            brand_company = get_brand_company(brand_name)
            if brand_company and not child_order_exists(doc.name, brand_company):
                create_company_sales_order(doc, items, brand_company, brand_name)
        
        # İleride ana SO üzerinde özet göstermek istersek buraya eklenecek
        
    except Exception as e:
        frappe.log_error(f"Sipariş ayrıştırma hatası: {str(e)}", "Culinary Order Split Error")


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
    """Ürünleri mutfak/marka gruplarına ayır"""
    kitchen_items = []
    brand_items = {}
    
    for item in items:
        if is_kitchen_item(item.item_code):
            kitchen_items.append(item)
        else:
            # Marka bilgisini al
            brand = get_item_brand(item.item_code)
            if brand:
                if brand not in brand_items:
                    brand_items[brand] = []
                brand_items[brand].append(item)
    
    return kitchen_items, brand_items


def is_kitchen_item(item_code):
    """Ürünün mutfak ürünü olup olmadığını kontrol et"""
    val = frappe.db.get_value("Item", item_code, "is_kitchen_item")
    return bool(val)


def get_item_brand(item_code):
    """Ürünün markasını getir"""
    brand = frappe.db.get_value("Item", item_code, "brand")
    return brand


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


def get_brand_company(brand_name):
    """Marka için varsayılan şirketi getir"""
    try:
        # 1) Opsiyonel: Brand Default (varsa)
        brand_defaults = frappe.get_all(
            "Brand Default",
            filters={"brand": brand_name},
            fields=["company"],
            limit=1,
        )
        if brand_defaults:
            return brand_defaults[0].company
    except Exception:
        # DocType yoksa sessizce geç
        pass

    try:
        # 2) Brand doc üzerindeki olası default_company alanı (varsa)
        default_company = frappe.db.get_value("Brand", brand_name, "default_company")
        if default_company:
            return default_company
    except Exception:
        pass

    # 3) Alan/doctype yoksa, marka adıyla aynı isimde bir Company var mı?
    try:
        if frappe.db.exists("Company", brand_name):
            return brand_name
    except Exception:
        pass

    # 4) Eşleşme bulunamadı; marka yönlendirmesini atla
    return None


def create_company_sales_order(parent_so, items, target_company, order_type):
    """Hedef şirket için Sales Order oluştur"""
    try:
        # Yeni Sales Order dokümanı oluştur
        new_so = frappe.new_doc("Sales Order")
        new_so.company = target_company
        new_so.customer = parent_so.customer
        new_so.transaction_date = parent_so.transaction_date
        new_so.delivery_date = parent_so.delivery_date or parent_so.transaction_date
        new_so.shipping_address_name = parent_so.shipping_address_name
        new_so.customer_address = parent_so.customer_address

        # Satırları kopyala
        for item in items:
            item_row = new_so.append("items")
            item_row.item_code = item.item_code
            item_row.item_name = item.item_name
            item_row.qty = item.qty
            item_row.rate = item.rate
            item_row.amount = item.amount
            item_row.description = item.description

        # İsimlendirme: Hedef şirketin kısaltmasıyla başlayan şirket-bazlı seri
        prefix = _company_prefix(target_company)
        # ERPNext Sales Order isimlendirmesi naming_series'e bağlı olduğu için
        # güvenilir yöntem: varsayılan isimle insert edip, sonrasında rename

        # Kaydet ve submit et
        new_so.insert(ignore_permissions=True)

        # Insert sonrası, submit etmeden önce yeniden adlandır
        try:
            target_name = make_autoname(f"{prefix}-.#####")
            if target_name and target_name != new_so.name:
                frappe.rename_doc("Sales Order", new_so.name, target_name, force=True)
                new_so.name = target_name
        except Exception:
            # Her durumda devam etsin; varsayılan isim kalabilir
            pass
        # Vergi/tutarlar insert sonrası da hesaplanır; submit öncesi güvence altına al
        new_so.calculate_taxes_and_totals()
        new_so.submit()

        # Referans bilgilerini kaydet
        # (source_culinary_so) kaldırıldı
        # Web’den gelen SO kimliği (ana SO’nun adı) çocukta saklansın
        frappe.db.set_value(
            "Sales Order",
            new_so.name,
            "source_web_so",
            parent_so.name,
        )

        frappe.log_error(
            f"Hedef şirket SO oluşturuldu: {new_so.name} (şirket: {target_company}, tip: {order_type})",
            "Order Split Success",
        )
            
    except Exception as e:
        frappe.log_error(
            f"Hedef şirket SO oluşturamadı - şirket: {target_company}, hata: {str(e)}",
            "Company SO Creation Error"
        )
        raise


def child_order_exists(parent_so_name: str, company: str) -> bool:
    """Aynı kaynak SO ve şirket için çocuk SO zaten var mı?"""
    return bool(
        frappe.get_all(
            "Sales Order",
            filters={"source_culinary_so": parent_so_name, "company": company},
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
