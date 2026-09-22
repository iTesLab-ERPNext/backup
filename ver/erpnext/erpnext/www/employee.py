import frappe

def get_context(context):
    employees = frappe.get_all("Employee", fields=["name", "first_name", "last_name", "position", "department", "image"])
    context.employees = employees