## Culinary Order Management (ERPNext v15)

Sipariş ayrıştırma ve yönlendirme uygulaması. WooCommerce’ten gelen ana Satış Siparişi (Culinary şirketi) otomatik işlenir; kalemler mutfak/marka şirketlerine bölünerek ayrı çocuk Satış Siparişlerine dönüştürülür.

### Özellikler
- `after_submit` ile otomatik bölme ve yönlendirme
- Mutfak yönlendirmesi: müşteri posta kodu → en yakın "Mutfak - …" şirketi
- Marka yönlendirmesi: ürün `brand` → ilgili şirket (Brand Default/Brand adı=Company)
- Çocuk SO adları şirket kısaltmasıyla başlar; şirket bazlı seri (ör. `MBER-00001`)
- Çocuk SO üzerinde `source_web_so` ile kaynak ana SO referansı
- Yönetim kolaylığı: `after_install/after_migrate` ile Admin üzerindeki Company User Permission kayıtları temizlenir (görünürlük sorunlarını önler)

### Kurulum
```bash
bench get-app https://github.com/idris61/culinary_order_management.git
bench --site your-site.local install-app culinary_order_management
```

### Kullanım Notları
- Mutfak şirketlerinin varsayılan adreslerinde `pincode` dolu olmalıdır.
- Ürün kartlarında `is_kitchen_item` alanı mutfak ürünleri için işaretlenmelidir.
- Marka yönlendirmesi için Brand → Company eşlemesi yapılmalıdır (Brand Default veya Brand adı=Company).

### Geliştirme
Bu depo `pre-commit` ile format/lint çalıştırmaya hazırdır.
```bash
cd apps/culinary_order_management
pre-commit install
```

### İletişim
Geliştirici: Idris Gemici  
E‑posta: idris.gemici61@gmail.com

### Lisans
MIT
