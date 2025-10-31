console.log('=== Agreement List JS Loading ===');

frappe.listview_settings['Agreement'] = {
	add_fields: ['valid_from', 'valid_to', 'docstatus'],
	
	onload: function(listview) {
		console.log('Agreement ListView onload triggered');
		console.log('ListView:', listview);
	},
	
	get_indicator: function(doc) {
		console.log('get_indicator called for:', doc.name);
		console.log('  docstatus:', doc.docstatus);
		console.log('  valid_from:', doc.valid_from);
		console.log('  valid_to:', doc.valid_to);
		
		// ERPNext standard status with date-based logic
		if (doc.docstatus === 0) {
			console.log('  → Result: Draft');
			return [__('Draft'), 'gray', 'docstatus,=,0'];
		}
		
		if (doc.docstatus === 2) {
			console.log('  → Result: Cancelled');
			return [__('Cancelled'), 'red', 'docstatus,=,2'];
		}
		
		if (doc.docstatus === 1) {
			const today = frappe.datetime.get_today();
			const valid_from = doc.valid_from;
			const valid_to = doc.valid_to;
			
			console.log('  Today:', today);
			console.log('  Date comparison:', {
				today_lt_valid_from: today < valid_from,
				today_gt_valid_to: today > valid_to,
				today_between: (today >= valid_from && today <= valid_to)
			});
			
			if (valid_from && valid_to) {
				if (today < valid_from) {
					console.log('  → Result: Not Started');
					return [__('Not Started'), 'orange', 'docstatus,=,1'];
				} else if (today > valid_to) {
					console.log('  → Result: Expired');
					return [__('Expired'), 'darkgray', 'docstatus,=,1'];
				} else {
					console.log('  → Result: Active');
					return [__('Active'), 'green', 'docstatus,=,1'];
				}
			}
			
			console.log('  → Result: Submitted (fallback)');
			return [__('Submitted'), 'blue', 'docstatus,=,1'];
		}
		
		console.log('  → Result: undefined (no match)');
	}
};

console.log('Agreement listview_settings registered:', frappe.listview_settings['Agreement']);
