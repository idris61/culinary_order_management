from frappe import _


def get_data():
	return [
		{
			"module_name": "Culinary Order Management",
			"category": "Modules",
			"label": _("Culinary Order Management"),
			"color": "#7b5cff",
			"icon": "octicon octicon-briefcase",
			"type": "module",
			"hidden": 0,
		},
		{
			"label": _("Culinary Order Management"),
			"items": [
				{"type": "doctype", "name": "Agreement", "label": _("Agreement")},
			],
		},
	]
















