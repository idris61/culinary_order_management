# Copyright (c) 2024, Culinary Order Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProformaInvoice(Document):
    def validate(self):
        """Custom validations"""
        pass
    
    def on_submit(self):
        """Actions on submit"""
        pass
    
    def calculate_totals(self):
        """Calculate grand total from items"""
        self.grand_total = sum(item.amount for item in self.items)
        return self.grand_total
