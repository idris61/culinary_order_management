app_name = "culinary_order_management"
app_title = "Culinary Order Management"
app_publisher = "İdris"
app_description = "Order ayrıştırma, yönlendirme ve komisyon yönetimi için özel uygulama"
app_email = "idris.gemici61@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "culinary_order_management",
# 		"logo": "/assets/culinary_order_management/logo.png",
# 		"title": "Culinary Order Management",
# 		"route": "/culinary_order_management",
# 		"has_permission": "culinary_order_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/culinary_order_management/css/culinary_order_management.css"
# app_include_js = "/assets/culinary_order_management/js/culinary_order_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/culinary_order_management/css/culinary_order_management.css"
# web_include_js = "/assets/culinary_order_management/js/culinary_order_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "culinary_order_management/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Sales Order" : "public/js/sales_order.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "culinary_order_management/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Fixtures
# ----------
fixtures = ["custom_field.json", "proforma_invoice.json"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "culinary_order_management.utils.jinja_methods",
# 	"filters": "culinary_order_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "culinary_order_management.install.before_install"
after_install = "culinary_order_management.culinary_order_management.setup.ensure_admin_company_permissions_clear"

# Uninstallation
# ------------

# before_uninstall = "culinary_order_management.uninstall.before_uninstall"
# after_uninstall = "culinary_order_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "culinary_order_management.utils.before_app_install"
# after_app_install = "culinary_order_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "culinary_order_management.utils.before_app_uninstall"
# after_app_uninstall = "culinary_order_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "culinary_order_management.notifications.get_notification_config"

# Permissions
# -----------
# Parent (split) Sales Order'ları varsayılan listelerden gizle
# Permission query conditions removed - split functionality disabled
permission_query_conditions = {}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Order": {
        "after_submit": "culinary_order_management.culinary_order_management.sales_order_hooks.split_order_to_companies"
    }
}

# Item hooks removed - supplier_display field was unused

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"culinary_order_management.tasks.all"
# 	],
# 	"daily": [
# 		"culinary_order_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"culinary_order_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"culinary_order_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"culinary_order_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "culinary_order_management.install.before_tests"
after_migrate = "culinary_order_management.culinary_order_management.setup.ensure_admin_company_permissions_clear"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "culinary_order_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "culinary_order_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["culinary_order_management.utils.before_request"]
# after_request = ["culinary_order_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["culinary_order_management.utils.before_job"]
# after_job = ["culinary_order_management.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"culinary_order_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

