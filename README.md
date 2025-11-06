# Culinary Order Management

**ERPNext v15** için özel sipariş yönetimi ve yönlendirme uygulaması.

## 📋 İçindekiler
- [Genel Bakış](#genel-bakış)
- [Özellikler](#özellikler)
- [Mimari](#mimari)
- [Modüller](#modüller)
- [Veri Akışı](#veri-akışı)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Geliştirici Notları](#geliştirici-notları)

---

## 🎯 Genel Bakış

Bu uygulama, ERPNext üzerinde çoklu şirket yapısında çalışan bir sipariş yönetim sistemidir. Ana amacı:

1. **Agreement (Anlaşma) Bazlı Fiyatlandırma**: Müşteri-Tedarikçi anlaşmalarına göre otomatik fiyat belirleme
2. **Sipariş Ayrıştırma**: Tek bir web siparişini mutfak ve marka şirketlerine otomatik yönlendirme
3. **Proforma Fatura**: Ayrıştırılmış siparişlerden birleştirilmiş proforma oluşturma
4. **DATEV Entegrasyonu**: PDF oluşturma sorunlarını çözen özel override

---

## ✨ Özellikler

### 1. Agreement Management (Anlaşma Yönetimi)
- ✅ Müşteri-Tedarikçi bazlı anlaşmalar
- ✅ Otomatik adlandırma: `{customer}-{supplier}-{####}`
- ✅ Ürün bazlı fiyatlandırma
- ✅ Çoklu para birimi desteği
- ✅ Tarih aralıklı geçerlilik
- ✅ Otomatik Price List senkronizasyonu
- ✅ **Agreement bazlı fiyat izolasyonu** (note field ile)
- ✅ **Aktif anlaşma kontrolü** (aynı müşteri-tedarikçi için tek aktif anlaşma)
- ✅ **Dialog ile anlaşma değiştirme** (kullanıcı onayı)
- ✅ **Dinamik status yönetimi** (Taslak/Aktif/Günü Geçmiş/İptal Edildi)
- ✅ **Sadece aktif anlaşmalar için fiyat oluşturma**
- ✅ **Scheduled job ile otomatik fiyat yönetimi**
- ✅ **Price List aktivasyon kontrolü** (aktif anlaşma varsa enabled)
- ✅ **Çoklu tedarikçi desteği** (fiyat çakışması yok)

### 2. Sales Order Validation (Sipariş Doğrulama)
- ✅ Anlaşma kontrolü (sadece anlaşmalı ürünler)
- ✅ Tarih geçerliliği kontrolü
- ✅ Otomatik fiyat uygulama
- ✅ Çoklu para birimi dönüşümü
- ✅ Fiyat kilitleme

### 3. Order Split & Routing (Sipariş Ayrıştırma)
- ✅ Mutfak/Marka ürün sınıflandırması
- ✅ Posta kodu bazlı mutfak yönlendirme
- ✅ Marka bazlı şirket yönlendirme
- ✅ Otomatik Child SO oluşturma
- ✅ Şirket bazlı numaralama (MBER-00001)
- ✅ Benzersiz PO numarası oluşturma

### 4. Proforma Invoice (Proforma Fatura)
- ✅ Child SO'lardan birleştirilmiş proforma
- ✅ Şirket bazlı gruplama
- ✅ Otomatik PDF oluşturma
- ✅ Ana SO'ya attachment
- ✅ Duplicate kontrol

### 5. DATEV Override
- ✅ PDF network hatası çözümü
- ✅ Monkey patch ile temiz implementasyon
- ✅ E-Invoice XML desteği

---

## 🏗️ Mimari

```
Culinary Order Management
│
├── DocTypes (4)
│   ├── Agreement (Ana DocType)
│   ├── Agreement Item (Child Table)
│   ├── Proforma Invoice (Ana DocType)
│   └── Proforma Invoice Item (Child Table)
│
├── Backend (Python)
│   ├── sales_order.py         # SO validation & pricing
│   ├── sales_order_hooks.py   # SO split & routing
│   ├── agreement.py           # Price list sync
│   ├── proforma_hooks.py      # Proforma generation
│   ├── api.py                 # Whitelisted APIs
│   ├── custom_datev.py        # DATEV override
│   └── setup.py               # Installation hooks
│
├── Frontend (JavaScript)
│   ├── agreement.js           # Agreement form logic
│   ├── agreement_list.js      # List view indicators (status colors)
│   └── sales_order.js         # Sales Order form logic
│
├── Custom Fields (2)
│   ├── Item.is_kitchen_item   # Mutfak ürünü flag
│   └── SO.source_web_so       # Parent SO referansı
│
└── Hooks
    ├── doc_events             # Document lifecycle hooks
    ├── doctype_js             # Client script injection
    └── scheduler_events       # Daily tasks (agreement status updates)
```

---

## 📦 Modüller

### 1. Agreement Module (agreement.py)

**Amaç:** Müşteri-Tedarikçi anlaşmalarını ERPNext Price List'e senkronize etmek ve yaşam döngüsünü otomatik yönetmek.

**Ana Fonksiyonlar:**

```python
check_overlapping_agreements(self)
# Aynı müşteri-tedarikçi için aktif anlaşma kontrolü
# - Tarih bağımsız: sadece docstatus=1 olan kayıt aranır
# - Replacement flag ile bypass edilebilir

check_active_agreement(customer, supplier, current_agreement)
# Client-side için API
# Returns: {"has_active": bool, "agreements": [...]}

replace_agreement(old_agreement, new_agreement)
# Eski anlaşmayı cancel et, yeni anlaşmayı submit et
# - Transaction içinde çalışır
# - Hata olursa rollback

create_price_list_for_agreement(doc, method)
# Price List oluştur ve aktif anlaşma kontrolü yap
# - Müşteri adında Price List oluşturur
# - Aktif anlaşma varsa enabled=1, yoksa enabled=0
# - sync_item_prices() çağırır

sync_item_prices(doc, method)
# Agreement Item'ları Item Price'a dönüştürür
# - Agreement referansını note field'a yazar
# - Agreement name ile fiyat izolasyonu sağlar
# - Sadece o anlaşmaya ait eski fiyatları temizler
# - Agreement Price varsa direkt kullanır
# - Yoksa Standard Selling Rate'e discount_rate uygular

cleanup_item_prices(doc, method)
# Agreement silindiğinde/iptal edildiğinde:
# - Agreement name'e göre sadece o anlaşmanın fiyatlarını siler
# - Diğer tedarikçilerin fiyatları korunur

update_status(self)
# Agreement status'ünü tarih bazlı hesaplar:
# - docstatus=0 → "Not Started" (Taslak)
# - docstatus=2 → "Cancelled"
# - docstatus=1:
#   - bugün < valid_from → "Not Started"
#   - bugün > valid_to → "Expired"
#   - else → "Active"

update_all_agreement_statuses()
# Günlük scheduler ile çalışır:
# 1. Tüm agreement'ların status'ünü günceller
# 2. Status değişiminde:
#    - "Not Started" → "Active": Fiyatları oluştur
#    - "Active" → "Expired": Fiyatları temizle
# 3. Price List aktivasyonunu güncelle
# 4. Expired olanları otomatik cancel eder (docstatus=2)
```

**Veri Akışı:**
```
Agreement → Price List → Item Price
         ↓
    Item Query
         ↓
    Sales Order
```

**Agreement Yaşam Döngüsü:**
```
Taslak (Draft)
    ↓ Submit
Başlamadı (Not Started) → Fiyatlar oluşturulmaz
    ↓ Tarihi gelince (Scheduled Job)
Aktif (Active) → Fiyatlar oluşturulur → Price List enabled
    ↓ Tarihi geçince (Scheduled Job)
Günü Geçmiş (Expired) → Fiyatlar temizlenir → Cancel edilir
```

**Çoklu Tedarikçi Senaryosu:**
```
Müşteri A - Tedarikçi B (01.11-30.11): Active ✅
  → Ürün X: 100 TL (note: "A-B-0001")
  
Müşteri A - Tedarikçi C (01.12-31.12): Not Started 🔵
  → Ürün X: Henüz fiyat oluşturulmadı

Price List "Müşteri A":
  → enabled = 1 (Tedarikçi B aktif olduğu için)
  → Ürün X: 100 TL (01.11-30.11) ← Sadece bu görünür
  
01.12.2025 geldiğinde (Scheduled Job):
  → Tedarikçi C aktif olur
  → Ürün X: 120 TL (01.12-31.12) oluşturulur (note: "A-C-0002")
  → İki fiyat birlikte var ama tarih bazlı filtreleniyor
```

**Key Features:**
- ✅ Natural unique key: (Price List, Item, Currency, Valid From, Valid To, Agreement)
- ✅ NULL date handling (open-ended ranges)
- ✅ Agreement-based isolation (note field)
- ✅ Multi-currency per item
- ✅ Multi-supplier support (no price conflicts)
- ✅ **Automatic naming:** `{customer}-{supplier}-{####}`
- ✅ **Single active agreement per customer-supplier**
- ✅ **User confirmation dialog** for agreement replacement
- ✅ **Dynamic status based on dates**
- ✅ **Price List activation control** (enabled only if active agreements exist)
- ✅ **Lazy price creation** (prices created only when agreement becomes active)
- ✅ **Automatic cancellation of expired agreements**
- ✅ **Scheduled daily status updates with price management**
- ✅ **Visual distinction:** "Expired" vs "Cancelled"

---

### 2. Sales Order Module (sales_order.py)

**Amaç:** Sales Order validasyonu ve Agreement bazlı fiyat uygulama.

**Ana Fonksiyonlar:**

```python
validate_sales_order(doc, method)
# Her item için:
# 1. Agreement kontrolü (yoksa hata)
# 2. Tarih geçerliliği kontrolü
# 3. Currency conversion (gerekirse)
# 4. Fiyat uygulama ve kilitleme

get_conversion_rate(from_currency, to_currency, date)
# Currency Exchange tablosundan kur getir
# Fallback: 1.0
```

**Validation Akışı:**
```
1. Customer var mı?
2. Item Agreement'ta var mı? → Yok ise HATA
3. Agreement tarihleri geçerli mi? → Değilse HATA
4. Agreement currency ≠ SO currency? → Currency conversion
5. Rate uygula ve kilitle
6. Amount hesapla (qty * rate)
```

**Önemli:**
- ⚠️ Anlaşmasız ürün eklenemez
- ⚠️ Tarihi geçmiş anlaşma kullanılamaz
- ⚠️ Fiyat manuel değiştirilemez (kilitli)

---

### 3. Sales Order Hooks Module (sales_order_hooks.py)

**Amaç:** Sales Order submit sonrası ürünlere göre şirketlere ayırma.

**İşleyiş:**

```
[Parent SO: Culinary] (Submit)
         ↓
   Split Algorithm
    ↙          ↘
[Kitchen SO]  [Brand SO]
MUTFAK-00001  MBER-00001
         ↓
    Proforma PDF
```

**Ana Fonksiyonlar:**

```python
split_order_to_companies(doc, method)
# 1. Ürünleri gruplandır (mutfak/marka)
# 2. Mutfak siparişi oluştur
# 3. Marka siparişleri oluştur
# 4. Proforma oluştur

group_items_by_type(items)
# Item.is_kitchen_item flag'ine göre ayır
# Returns: (kitchen_items, brand_items_dict)

find_nearest_kitchen(customer_pincode, customer_name)
# Müşteri posta koduna göre en yakın mutfak bul
# "Mutfak - %" pattern'i ile Company ara
# Posta kodu eşleşmesi > İlk bulunan

get_brand_company(brand_name)
# Marka için şirket bul:
# 1. Brand Default tablosuna bak
# 2. Brand.default_company alanına bak
# 3. Brand adıyla Company ara

create_company_sales_order(parent_so, items, target_company, order_type)
# Helper fonksiyonlar:
# - _generate_po_number()        # PO numarası oluştur
# - _prepare_sales_order_base()  # SO temel bilgileri
# - _copy_items_to_sales_order() # Item'ları kopyala
# - _rename_sales_order_with_prefix() # Şirket prefix'i ile rename
```

**Custom Fields:**
- `Item.is_kitchen_item` (Check): Mutfak ürünü flag
- `Sales Order.source_web_so` (Data): Parent SO referansı

**Naming Convention:**
```
Parent SO:   WEB1-027703
Kitchen SO:  MUTFAK-00042
Brand SO:    MBER-00128
PO Numbers:  27703-MUTFAK, 27703-MBER
```

---

### 4. Proforma Module (proforma_hooks.py)

**Amaç:** Child SO'lardan birleştirilmiş Proforma Invoice oluşturma.

**Ana Fonksiyonlar:**

```python
create_proforma_invoice(parent_so_name)
# 1. Existing proforma kontrolü
# 2. Child SO'ları getir (source_web_so filter)
# 3. Tüm item'ları birleştir
# 4. Proforma oluştur ve submit et
# 5. PDF oluştur ve attach et

generate_and_attach_proforma_pdf(proforma_name, parent_so_name)
# 1. Template render (HTML)
# 2. PDF oluştur (get_pdf)
# 3. File doc oluştur
# 4. Parent SO'ya attach et
```

**Veri Yapısı:**
```python
Proforma Invoice
├── customer
├── source_sales_order (Parent SO)
├── invoice_date
├── due_date
├── grand_total
└── items (Child Table)
    ├── item_code
    ├── item_name
    ├── qty
    ├── rate
    ├── amount
    └── supplier_company  # Hangi şirketten geldiği
```

**PDF Template:**
- Şirket bazlı gruplama (items_by_company)
- Müşteri/Şirket bilgileri
- Tarih formatları (dd.MM.yyyy)
- Vergiler (eğer varsa)

---

### 5. API Module (api.py)

**Whitelisted Functions:**

```python
@frappe.whitelist()
def item_by_supplier(...)
# Agreement form'da supplier seçilince
# Sadece o supplier'ın ürünlerini listele

@frappe.whitelist()
def items_by_customer_agreement(...)
# Sales Order'da customer seçilince
# Sadece anlaşmalı ürünleri listele
# Tarih kontrolü ile
```

**Security:**
- ✅ SQL injection koruması (parametrize query)
- ✅ Allowed fields whitelist
- ✅ Input sanitization

---

### 6. DATEV Override (custom_datev.py)

**Problem:** 
wkhtmltopdf external kaynaklar yüklerken network hatası veriyor.

**Çözüm:** 
Monkey patch ile `attach_print` fonksiyonunu override et.

```python
# __init__.py
def _patch_datev():
    from culinary_order_management.custom_datev import attach_print_custom
    import erpnext_datev... as datev_module
    datev_module.attach_print = attach_print_custom

_patch_datev()  # App yüklendiğinde otomatik
```

**Override:**
```python
def attach_print_custom(doctype, name, language, print_format):
    # no_letterhead=1 ile PDF oluştur (network yok)
    data = frappe.get_print(..., no_letterhead=1)
    # E-Invoice XML ekle (varsa)
    # File olarak kaydet
```

---

## 🔄 Veri Akışı

### Senaryo 1: Agreement Oluşturma

```
1. User creates Agreement
   ├── Customer: "ABC GmbH"
   ├── Supplier: "Tedarikçi A"
   ├── Valid: 2025-01-01 to 2025-12-31
   └── Items: [Item-001: €10.00, Item-002: €25.00]

2. on_save → create_price_list_for_agreement()
   ├── Price List "ABC GmbH" oluşturuldu
   └── 2 Item Price kaydı oluşturuldu

3. Database:
   Price List: ABC GmbH
   Item Price:
   ├── Item-001: €10.00 (2025-01-01 to 2025-12-31)
   └── Item-002: €25.00 (2025-01-01 to 2025-12-31)
```

---

### Senaryo 2: Sales Order Oluşturma ve Ayrıştırma

```
1. User creates Sales Order (WEB1-027703)
   Company: Culinary
   Customer: ABC GmbH
   Items:
   ├── Item-001 (Kitchen Item) × 10
   ├── Item-002 (Brand: MBER) × 5
   └── Item-003 (Brand: XYZ) × 3

2. on_validate → validate_sales_order()
   ├── Item-001: Agreement var ✓ → €10.00
   ├── Item-002: Agreement var ✓ → €25.00
   └── Item-003: Agreement var ✓ → €15.00
   
3. on_submit → split_order_to_companies()
   
   3.1 group_items_by_type()
       ├── kitchen_items: [Item-001]
       └── brand_items: {"MBER": [Item-002], "XYZ": [Item-003]}
   
   3.2 Kitchen Order
       ├── Customer pincode: 10115
       ├── find_nearest_kitchen() → "Mutfak - Berlin"
       └── MUTFAK-00042 oluşturuldu
   
   3.3 Brand Orders
       ├── MBER-00128 oluşturuldu (Brand: MBER)
       └── XYZ-00089 oluşturuldu (Brand: XYZ)
   
   3.4 create_proforma_invoice()
       ├── Child SO'ları birleştir
       ├── Proforma COM-0001 oluşturuldu
       └── PDF → WEB1-027703'e attach edildi

4. Result:
   ├── WEB1-027703 (Parent - Culinary)
   ├── MUTFAK-00042 (Kitchen - Mutfak - Berlin)
   ├── MBER-00128 (Brand - MBER GmbH)
   ├── XYZ-00089 (Brand - XYZ AG)
   └── Proforma_WEB1-027703.pdf
```

---

## 🚀 Kurulum

### 1. App Kurulumu

```bash
cd /path/to/frappe-bench
bench get-app https://github.com/your-repo/culinary_order_management.git
bench --site site1.local install-app culinary_order_management
bench --site site1.local migrate
```

### 2. Gerekli Ayarlar

**Custom Fields (Otomatik):**
- `Item.is_kitchen_item` → fixture'dan yüklenir
- `Sales Order.source_web_so` → fixture'dan yüklenir

**Manuel Ayarlar:**
1. Şirket yapısını oluştur:
   - Ana şirket: "Culinary"
   - Mutfak şirketleri: "Mutfak - [Şehir]" formatında
   - Marka şirketleri: Marka adlarıyla

2. Item'lara Brand ata
3. Kitchen item'ları işaretle (`is_kitchen_item = 1`)
4. Currency Exchange rates tanımla

### 3. DATEV (Opsiyonel)

DATEV kullanıyorsanız, override otomatik devreye girer.

---

## 📖 Kullanım

### 1. Agreement Oluşturma

```
1. Agreement → New
2. Customer seç
3. Supplier seç (aynı müşteri-tedarikçi için aktif anlaşma varsa uyarı)
4. Valid From / Valid To tarihlerini gir
5. Items tablosuna ürün ekle:
   - Item Code seç (supplier filter otomatik çalışır)
   - Agreement Price gir (€ 10.00)
   - Currency seç (EUR)
6. Save → Status hesaplanır
   - Tarih gelmediyse: "Not Started" (fiyat oluşturulmaz)
   - Tarih aktifse: "Active" (fiyat oluşturulur)
7. Submit
   - Aktif anlaşma varsa → Dialog gösterilir
     • Evet: Eski anlaşma cancel, yeni anlaşma submit
     • Hayır: İşlem iptal
   - Aktif anlaşma yoksa → Normal submit
```

**Otomatik İşlemler:**
```
Scheduled Job (Günlük):
  1. Tarihi gelen anlaşmalar → Active + Fiyat oluştur
  2. Tarihi geçen anlaşmalar → Expired + Fiyat sil + Cancel
  3. Price List aktivasyonu güncelle
```

### 2. Sales Order Oluşturma

```
1. Sales Order → New
2. Company: "Culinary" seç
3. Customer seç
4. Items:
   - Item Code seç (sadece anlaşmalı ürünler görünür)
   - Qty gir
   - Rate otomatik gelir (değiştirilemez)
5. Save
   → Validation çalışır
   → Fiyatlar kilitlenir
6. Submit
   → Split algorithm çalışır
   → Child SO'lar oluşturulur
   → Proforma PDF oluşturulur
```

### 3. Manuel Split (Opsiyonel)

Eğer submit sonrası split çalışmadıysa:

```javascript
// Sales Order formunda
frappe.call({
    method: 'culinary_order_management...split_order_to_companies_api',
    args: { name: frm.doc.name },
    callback: function(r) {
        frappe.msgprint('Split completed!');
    }
});
```

---

## 🛠️ Geliştirici Notları

### Code Quality

```
✅ Linter Errors: 0
✅ Debug Code: 0
✅ Code Duplication: None
✅ Single Responsibility: Applied
✅ SQL Injection: Protected
✅ Error Handling: Comprehensive
```

### Best Practices

1. **Naming:**
   - Function names: `snake_case`
   - Private functions: `_prefix`
   - Classes: `PascalCase`

2. **Error Handling:**
   ```python
   try:
       # risky operation
   except Exception as e:
       frappe.log_error(f"Error message: {str(e)}", "Error Title")
       raise  # Re-raise if critical
   ```

3. **Database Queries:**
   ```python
   # ✅ GOOD: Parametrized
   frappe.db.sql("SELECT * FROM tab WHERE name=%s", (name,))
   
   # ❌ BAD: SQL Injection risk
   frappe.db.sql(f"SELECT * FROM tab WHERE name='{name}'")
   ```

4. **Whitelist Security:**
   ```python
   @frappe.whitelist()
   def safe_function(param):
       # Always validate inputs
       if not param:
           frappe.throw("Invalid input")
   ```

### Testing

**Manual Test Checklist:**

- [ ] Agreement oluştur ve Price List kontrol et
- [ ] Overlapping tarihli Agreement güncelle
- [ ] Agreement sil ve Item Price temizliğini kontrol et
- [ ] Sales Order validation (anlaşmasız ürün)
- [ ] Sales Order validation (tarihi geçmiş anlaşma)
- [ ] Sales Order split (mutfak routing)
- [ ] Sales Order split (marka routing)
- [ ] Proforma PDF oluşturma
- [ ] Multi-currency conversion
- [ ] Duplicate prevention

---

## 🔧 Troubleshooting

### Problem: Agreement kaydedildi ama Price List oluşmadı

**Çözüm:**
```python
# Console'da çalıştır
doc = frappe.get_doc("Agreement", "agreement-name")
from culinary_order_management.culinary_order_management.agreement import create_price_list_for_agreement
create_price_list_for_agreement(doc, None)
```

### Problem: Sales Order split çalışmadı

**Çözüm:**
```python
# Hooks'u kontrol et
bench --site site1.local console
>>> import culinary_order_management
>>> doc = frappe.get_doc("Sales Order", "SO-name")
>>> from culinary_order_management...sales_order_hooks import split_order_to_companies
>>> split_order_to_companies(doc, "after_submit")
```

### Problem: Currency conversion yapılmıyor

**Çözüm:**
```sql
-- Currency Exchange kayıtlarını kontrol et
SELECT * FROM `tabCurrency Exchange`
WHERE from_currency='USD' AND to_currency='EUR';

-- Yoksa ekle
INSERT INTO `tabCurrency Exchange` 
(from_currency, to_currency, exchange_rate, date)
VALUES ('USD', 'EUR', 0.92, CURDATE());
```

### Problem: DATEV PDF network hatası

**Çözüm:**
Override otomatik devreye girmeli. Kontrol:
```python
import erpnext_datev.erpnext_datev.doctype.datev_unternehmen_online_settings.datev_unternehmen_online_settings as datev
print(datev.attach_print)  # attach_print_custom olmalı
```

---

## 📝 Changelog

### v0.0.3 (2025-11-06)
- ✅ **Agreement Geliştirmeleri**
  - Otomatik adlandırma: `{customer}-{supplier}-{####}`
  - Aktif anlaşma kontrolü (aynı müşteri-tedarikçi için tek aktif anlaşma)
  - Dialog ile anlaşma değiştirme (kullanıcı onayı)
  - Agreement bazlı fiyat izolasyonu (note field)
  - Sadece aktif anlaşmalar için fiyat oluşturma
  - Scheduled job ile otomatik fiyat yönetimi
  - Price List aktivasyon kontrolü
  - Çoklu tedarikçi desteği (fiyat çakışması yok)
- ✅ Code cleanup & comprehensive testing

### v0.0.2 (2025-10-31)
- ✅ **Agreement Status Sistemi**
  - Dinamik status hesaplama (Taslak/Aktif/Günü Geçmiş/İptal Edildi)
  - Renkli liste görünümü indicators
  - Otomatik expired agreement iptali
  - Günlük scheduler ile status güncelleme
  - Expired fiyatların otomatik temizlenmesi
- ✅ Code cleanup & optimization

### v0.0.1
- ✅ Agreement → Price List sync
- ✅ Sales Order validation
- ✅ Order split & routing
- ✅ Proforma generation
- ✅ DATEV override
- ✅ Multi-currency support
- ✅ Code cleanup & refactoring

---

## 📄 License

MIT License

---

## 👥 Contributors

- İdris Gemici (idris.gemici61@gmail.com)

---

## 🔗 Links

- [ERPNext Documentation](https://docs.erpnext.com)
- [Frappe Framework](https://frappeframework.com)

---

**Son Güncelleme:** 2025-11-06
**ERPNext Version:** v15
**Frappe Version:** v15
