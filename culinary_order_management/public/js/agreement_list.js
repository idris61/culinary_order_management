frappe.listview_settings['Agreement'] = {
	add_fields: ["status", "valid_from", "valid_to", "docstatus"],
	
	// Frappe'nin varsayılan workflow indicator'ını devre dışı bırak
	has_indicator_for_draft: 1,
	has_indicator_for_cancelled: 1,
	
	get_indicator: function(doc) {
		// Tarih bazlı durum göstergesi - Frappe standart renkleri
		const status_colors = {
			"Active": "green",
			"Expired": "orange",
			"Not Started": "blue",
			"Cancelled": "red"
		};
		
		// Draft (docstatus=0)
		if (doc.docstatus == 0) {
			return [__("Draft"), "blue", "docstatus,=,0"];
		}
		
		// Cancelled (docstatus=2) - Status field'ına göre göster
		if (doc.docstatus == 2) {
			// Eğer status "Expired" ise Günü Geçmiş göster
			if (doc.status == "Expired") {
				return [__("Expired"), "orange", "status,=,Expired"];
			}
			// Manuel iptal edilmiş
			return [__("Cancelled"), "red", "status,=,Cancelled"];
		}
		
		// Submitted (docstatus=1) - Status field'ına göre göster
		if (doc.status) {
			let color = status_colors[doc.status] || "gray";
			return [__(doc.status), color, "status,=," + doc.status];
		}
		
		// Varsayılan
		return [__("Active"), "green", "docstatus,=,1"];
	}
};
