# Culinary Order Management (ERPNext v15)

Culinary platformu için sipariş ayrıştırma, yönlendirme ve proforma fatura yönetimi uygulaması. WooCommerce'ten gelen ana Satış Siparişleri otomatik işlenerek mutfak ve marka şirketlerine yönlendirilir.

## 🚀 Ana Özellikler

### 📦 Sipariş Ayrıştırma ve Yönlendirme
- **Otomatik Süreç**: Sales Order `after_submit` ile otomatik bölme ve yönlendirme
- **Akıllı Mutfak Yönlendirmesi**: Müşteri posta kodu → en yakın "Mutfak - …" şirketi
- **Marka Yönlendirmesi**: Ürün brand → ilgili şirket (Brand Default/Brand adı=Company)
- **Standart İsimlendirme**: Child SO adları şirket kısaltmasıyla başlar; şirket bazlı seri (örn. `MBER-00001`)

### 📋 Proforma Fatura Sistemi
- **Otomatik Proforma**: Ana SO'dan child SO'ları birleştirerek tek proforma
- **PDF Üretimi**: HTML template ile profesyonel PDF çıktısı
- **Müşteri Odaklı**: Tek PDF'de tüm tedarikçi kalemleri
- **Dosya Yönetimi**: PDF otomatik Sales Order'a attach edilir

### 👤 Yönetici Kolaylıkları
- **Sınırsız Erişim**: Admin kullanıcısı üzerindeki Company User Permission kayıtları otomatik temizlenir
- **Manuel Kontrol**: "Böl ve Yönlendir" ve "Proforma Oluştur" butonları ile manuel işlem
- **Hata Takibi**: Kapsamlı error logging ve mesajlaşma

## 📁 Doküman Yapısı

```
culinary_order_management/
├── 𝖼𝗎𝗅𝗂𝗇𝖺𝗋𝗒_𝗈𝗋𝖽𝖾𝗋_𝗆𝖺𝗇𝖺𝗀𝖾𝗆𝖾𝗇𝗍/
│   ├── sales_order_hooks.py       # Ana böl ve yönlendirme mantığı
│   ├── proforma_hooks.py          # Proforma oluşturma ve PDF
│   ├── setup.py                   # Admin permission temizleme
│   └── doctype/
│       └── proforma_invoice/      # Proforma Invoice dokümanı
├── fixtures/
│   ├── custom_field.json          # Özel alanlar
│   └── proforma_invoice.json      # Proforma Invoice dizini
├── templates/
│   └── proforma_template.html     # PDF HTML template
└── public/js/
    └── sales_order.js             # UI butonları
```

## ⚙️ Kurulum

```bash
# Depoyu indirin
bench get-app https://github.com/idris61/culinary_order_management.git

# Uygulamayı yükleyin
bench --site your-site.local install-app culinary_order_management

# Cache temizleyin ve yeniden başlatın
bench --site your-site.local clear-cache
bench restart
```

## 🔧 Kullanım Kılavuzu

### Gereksinimler
- ERPNext v15
- WooCommerce Fusion entegrasyonu
- Şirket yapısı:
  - Ana şirket: `Culinary`
  - Mutfak şirketleri: `Mutfak - Berlin`, `Mutfak - München` vb.
  - Marka şirketleri: Her marka için ayrı şirket

### Temel Ayarlar

#### 1. Ürün Kartları
```python
# Ürün -> Özel Alanlar
is_kitchen_item = True/False  # Mutfak ürünü işaretlenmeli
brand = "Bir Marka"           # Marka ürünü için marka adı
```

#### 2. Mutfak Şirketleri
- Şirket adı: `Mutfak-[Şehir]` formatında
- Varsayılan adres: `pincode` alanı dolu olmalı

#### 3. Marka Yönlendirmesi
- Brand → Company eşlemesi (Brand Default veya Brand adı=Company)

### İş Akışı

1. **Sipariş Girişi**: WordPress → WooCommerce → ERPNext
2. **Otomatik Ayrıştırma**: `after_submit` hook ile:
   - Mutfak ürünleri → en yakın mutfak şirketi
   - Marka ürünleri → ilgili marka şirketi
3. **Proforma Üretimi**: Child SO'ları birleştirerek tek PDF
4. **Faturalama**: Her şirket kendi child SO'sunu fatura eder

### Manuel İşlemler

#### Böl ve Yönlendir
- Sales Order açın
- "Aksiyonlar" → "Böl ve Yönlendir" butonuna tıklayın
- Çocak siparişler otomatik oluşturulur

#### Proforma Oluştur
- "Faturalama" → "Proforma Oluştur" butonuna tıklayın
- PDF otomatik Sales Order'a eklenir

## 📊 Özel Alanlar

### Sales Order
- `source_web_so`: Ana veya child SO referansı

### Item
- `is_kitchen_item`: Mutfak ürünü işaretleyicisi

### Proforma Invoice
- `customer`: Müşteri referansı
- `source_sales_order`: Kaynak Sales Order
- `items`: Child SO'lardan gelen kalemler (`supplier_company` ile gruplandırılmış)

## 🎯 Değişiklik Özeti

### Son Versiyonda Eklenenler
- ✅ **Proforma Fatura Sistemi**: Otomatik PDF üretimi
- ✅ **Manual Buttons**: UI'dan manuel kontrol
- ✅ **Admin Permissions**: Sınırsız erişim düzeltmesi
- ✅ **Error Handling**: Kapsamlı hata yönetimi
- ✅ **Production Ready**: Debug kodları temizlendi

### Temizlenen Kodlar
- ❌ Debug print statement'ları
- ❌ Console.log() kodları  
- ❌ Gereksiz CSS kuralları
- ❌ Optimize edilememiş template sorguları

## 🔍 Sorun Giderme

### Common Issues

#### Child SO'lar Görünmüyor
```bash
# Admin permission'ları temizle
bench --site your-site.local console
# frappe.delete_doc("User Permission", "name", ignore_permissions=True, force=True)
```

#### PDF Oluşturulmuyor
- Child SO'ların mevcut olduğunu kontrol edin
- Template hatası yoksa cache'i temizlemeyi deneyin
- Browser console'da JavaScript hatalarını kontrol edin

## 🧪 Geliştirme

### Projenin Klonlanması
```bash
cd apps/
git clone https://github.com/idris61/culinary_order_management.git
cd culinary_order_management
```

### Test Yapısı
- Sales Order oluşturun (company: Culinary)
- Submit edin (otomatik hook tetiklenir)
- Child SO'ları kontrol edin
- Proforma PDF'i denetleyin

### Development Workflow
```bash
# Kod değişiklikleri sonrası
bench --site your-site.local clear-cache
bench --site your-site.local build --app culinary_order_management

# Test için console
bench --site your-site.local console
```

## 📞 İletişim

- **Geliştirici**: İdris
- **E-posta**: idris.gemici61@gmail.com
- **GitHub**: https://github.com/idris61/culinary_order_management

## 📄 Lisans

MIT License - Detaylar için LICENSE dosyasına bakınız.

---

**Not**: Bu uygulama Culinary platformuna özgü olarak geliştirilmiştir. Başka ERPNext kurulumlarında kullanırken gerekli adaptasyonları yapınız.