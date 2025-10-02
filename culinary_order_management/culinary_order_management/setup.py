import frappe


def ensure_admin_company_permissions_clear(*args, **kwargs):
    """Ensure Administrator has no Company-level User Permission that hides cross-company docs.

    Called on after_install and after_migrate to avoid list visibility issues in dev/test.
    Safe no-op if records do not exist.
    """
    try:
        names = frappe.get_all(
            "User Permission",
            filters={"user": "Administrator", "allow": "Company"},
            pluck="name",
        )
        for name in names:
            try:
                frappe.delete_doc("User Permission", name, force=True)
            except Exception:
                # ignore if already deleted or protected
                pass
        if names:
            frappe.db.commit()
    except Exception:
        # defensive: do not block installs/migrations
        pass


