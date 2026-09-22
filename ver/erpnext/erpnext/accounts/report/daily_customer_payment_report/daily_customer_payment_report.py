# Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from collections import OrderedDict

import frappe
from frappe import _, _dict
from frappe.utils import cstr, getdate

from erpnext import get_company_currency, get_default_company
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children
from erpnext.accounts.report.utils import convert_to_presentation_currency, get_currency
from erpnext.accounts.utils import get_account_currency

# to cache translations
TRANSLATIONS = frappe._dict()


def execute(filters=None):
	if not filters:
		return [], []

	account_details = {}

	if filters and filters.get("print_in_account_currency") and not filters.get("account"):
		frappe.throw(_("Select an account to print in account currency"))

	for acc in frappe.db.sql("""select name, is_group from tabAccount""", as_dict=1):
		account_details.setdefault(acc.name, acc)

	if filters.get("party"):
		filters.party = frappe.parse_json(filters.get("party"))

	validate_filters(filters, account_details)

	validate_party(filters)

	columns = get_columns(filters)

	update_translations()

	res = get_result(filters, account_details)

	return columns, res


def update_translations():
	TRANSLATIONS.update(
		dict(OPENING=_("Opening"), TOTAL=_("Total"), CLOSING_TOTAL=_("Closing (Opening + Total)"))
	)


def validate_filters(filters, account_details):

	if not filters.get("from_date") and not filters.get("to_date"):
		frappe.throw(
			_("{0} is mandatory").format(frappe.bold(_("Posting Date")))
		)

	if filters.get("account") and filters.get("group_by") == "Group by Account":
		filters.account = frappe.parse_json(filters.get("account"))
		for account in filters.account:
			if account_details[account].is_group == 0:
				frappe.throw(_("Can not filter based on Child Account, if grouped by Account"))

def validate_party(filters):
	party_type, party = filters.get("party_type"), filters.get("party")

	if party and party_type:
		for d in party:
			if not frappe.db.exists(party_type, d):
				frappe.throw(_("Invalid {0}: {1}").format(party_type, d))

def get_result(filters, account_details):
	user_roles = frappe.get_roles()
	user = frappe.session.user
	
	# Si l'utilisateur est Sales User ou Sales Manager, filtrer uniquement ses paiements
	if ("Sales User" in user_roles or "Sales Manager" in user_roles) and "System Manager" not in user_roles:		# on ajoute une condition pour ne voir que ses paiements
		filters["owner"] = user
	else:
		# sinon voir tous les paiements, on supprime ce filtre si présent
		filters.pop("owner", None)

	payment_entries = get_payment_entries(filters)

	# Si filtre owner présent, filtrer dans le résultat (sécurité)
	if "owner" in filters:
		payment_entries = [p for p in payment_entries if p["owner"] == filters["owner"]]

	result = get_result_as_list(payment_entries, filters)

	return result


def get_payment_entries(filters):
	currency_map = get_currency(filters)
	select_fields = """, custom_party_sold, custom_total_unpaid, paid_amount """

	if filters.get("show_remarks"):
		if remarks_length := frappe.db.get_single_value("Accounts Settings", "general_ledger_remarks_length"):
			select_fields += f", substr(remarks, 1, {remarks_length}) as 'remarks'"
		else:
			select_fields += """,remarks"""

	# Make sure order_by_statement is initialized
	order_by_statement = "ORDER BY posting_date, creation"

	# Make sure get_conditions is called correctly
	conditions = get_conditions(filters)
	if conditions:
		conditions = "AND " + " AND ".join(conditions)
	else:
		conditions = ""  # Avoid an empty "AND"

	# Using the query with the correct formatting
	payment_entries = frappe.db.sql(
		"""
		SELECT
			name, posting_date, party_type, party, mode_of_payment,
			custom_observation, owner, creation {select_fields}
		FROM `tabPayment Entry`
		WHERE party_type = %(party_type)s
		AND posting_date = %(from_date)s
		AND docstatus = 1
		{conditions}
		{order_by_statement}
		""".format(
			select_fields=select_fields,
			conditions=get_conditions(filters),
			order_by_statement=order_by_statement,
		),
		filters,
		as_dict=1,
	)

	if filters.get("presentation_currency"):
		return convert_to_presentation_currency(payment_entries, currency_map)
	else:
		return payment_entries


def get_conditions(filters):
	conditions = []

	if filters.get("group_by") == "Group by Party" and not filters.get("party_type"):
		conditions.append("party_type in ('Customer', 'Supplier')")

	if filters.get("party_type"):
		conditions.append("party_type=%(party_type)s")

	if filters.get("party"):
		conditions.append("party in %(party)s")

	if not (
		filters.get("party")
		or filters.get("group_by") in ["Group by Account", "Group by Party"]
	):
		conditions.append("(posting_date >=%(from_date)s )")

	conditions.append("(posting_date <=%(to_date)s )")

	if filters.get("show_cancelled_entries"):
		conditions.append("docstatus = 0")

	return "and {}".format(" and ".join(conditions)) if conditions else ""

def get_totals_dict():
	def _get_debit_credit_dict(label):
		return _dict(
			account="'{0}'".format(label),
			debit=0.0,
			credit=0.0,
			debit_in_account_currency=0.0,
			credit_in_account_currency=0.0,
		)

	return _dict(
		opening=_get_debit_credit_dict(TRANSLATIONS.OPENING),
		total=_get_debit_credit_dict(TRANSLATIONS.TOTAL),
		closing=_get_debit_credit_dict(TRANSLATIONS.CLOSING_TOTAL),
	)


def group_by_field(group_by):
	if group_by == "Group by Party":
		return "party"
	elif group_by in ["Group by Voucher (Consolidated)", "Group by Account"]:
		return "account"
	else:
		return ""


def initialize_gle_map(payment_entries, filters):
	gle_map = OrderedDict()
	group_by = group_by_field(filters.get("group_by"))

	for gle in payment_entries:
		gle_map.setdefault(gle.get(group_by), _dict(totals=get_totals_dict(), entries=[]))
	return gle_map


def get_accountwise_gle(filters, payment_entries, gle_map):
	totals = get_totals_dict()
	entries = []
	consolidated_gle = OrderedDict()
	group_by = group_by_field(filters.get("group_by"))
	group_by_voucher_consolidated = filters.get("group_by") == "Group by Voucher (Consolidated)"

	def update_value_in_dict(data, key, gle):
		data[key].debit += gle.debit
		data[key].credit += gle.credit

		data[key].debit_in_account_currency += gle.debit_in_account_currency
		data[key].credit_in_account_currency += gle.credit_in_account_currency

		if filters.get("show_net_values_in_party_account") and account_type_map.get(
			data[key].account
		) in ("Receivable", "Payable"):
			net_value = data[key].debit - data[key].credit
			net_value_in_account_currency = (
				data[key].debit_in_account_currency - data[key].credit_in_account_currency
			)

			if net_value < 0:
				dr_or_cr = "credit"
				rev_dr_or_cr = "debit"
			else:
				dr_or_cr = "debit"
				rev_dr_or_cr = "credit"

			data[key][dr_or_cr] = abs(net_value)
			data[key][dr_or_cr + "_in_account_currency"] = abs(net_value_in_account_currency)
			data[key][rev_dr_or_cr] = 0
			data[key][rev_dr_or_cr + "_in_account_currency"] = 0

		if data[key].against_voucher and gle.against_voucher:
			data[key].against_voucher += ", " + gle.against_voucher

	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	show_opening_entries = filters.get("show_opening_entries")

	for gle in payment_entries:
		group_by_value = gle.get(group_by)

		if gle.posting_date < from_date or (not show_opening_entries):
			if not group_by_voucher_consolidated:
				update_value_in_dict(gle_map[group_by_value].totals, "opening", gle)
				update_value_in_dict(gle_map[group_by_value].totals, "closing", gle)

			update_value_in_dict(totals, "opening", gle)
			update_value_in_dict(totals, "closing", gle)

		elif gle.posting_date <= to_date or (show_opening_entries):
			if not group_by_voucher_consolidated:
				update_value_in_dict(gle_map[group_by_value].totals, "total", gle)
				update_value_in_dict(gle_map[group_by_value].totals, "closing", gle)
				update_value_in_dict(totals, "total", gle)
				update_value_in_dict(totals, "closing", gle)

				gle_map[group_by_value].entries.append(gle)

			elif group_by_voucher_consolidated:
				keylist = [
					gle.get("party_type"),
					gle.get("party"),
				]
				
				key = tuple(keylist)
				if key not in consolidated_gle:
					consolidated_gle.setdefault(key, gle)
				else:
					update_value_in_dict(consolidated_gle, key, gle)

	for key, value in consolidated_gle.items():
		update_value_in_dict(totals, "total", value)
		entries.append(value)

	return totals, entries

def get_result_as_list(data, filters):
	balance, balance_in_account_currency = 0, 0
	inv_details = get_supplier_invoice_details()

	for d in data:
		if not d.get("posting_date"):
			balance, balance_in_account_currency = 0, 0

		balance = get_balance(d, balance, "debit", "credit")
		d["balance"] = balance

		d["account_currency"] = filters.account_currency
		d["bill_no"] = inv_details.get(d.get("against_voucher"), "")

	return data


def get_supplier_invoice_details():
	inv_details = {}
	for d in frappe.db.sql(
		""" select name, bill_no from `tabPurchase Invoice`
		where docstatus = 1 and bill_no is not null and bill_no != '' """,
		as_dict=1,
	):
		inv_details[d.name] = d.bill_no

	return inv_details


def get_balance(row, balance, debit_field, credit_field):
	balance += row.get(debit_field, 0) - row.get(credit_field, 0)

	return balance


def get_columns(filters):
	company = get_default_company()
	currency = get_company_currency(company)

	columns = [
		{
			"label": _("GL Entry"),
			"fieldname": "gl_entry",
			"fieldtype": "Link",
			"options": "GL Entry",
			"hidden": 1,
		},
		{
			"label": _("Posting Date"), 
			"fieldname": "posting_date", 
			"fieldtype": "Date", 
			"width": 180
		},
		{
			"label": _("Party"), 
			"fieldname": "party", 
			"width": 180,
			"fieldtype": "Dynamic Link",
			"options": "Customer",
			"link": True,
		},
		{
			"label": _("Mode of Payment"),
			"fieldname": "mode_of_payment",
			"fieldtype": "data",
			"width": 180,
		},
		{
			"label": _("Previous Balance ({0})").format(currency),
			"fieldname": "custom_party_sold",
			"fieldtype": "Float",
			"width": 180,
		},
		{
			"label": _("Paid Amount ({0})").format(currency),
			"fieldname": "paid_amount",
			"fieldtype": "Float",
			"width": 180,
		},
		{
			"label": _("Balance ({0})").format(currency),
			"fieldname": "custom_total_unpaid",
			"fieldtype": "Float",
			"width": 180,
		},
		{
			"label": _("Voucher No"),
			"fieldname": "name",
			"fieldtype": "Dynamic Link",
			"options": "Payment Entry",  # Make sure this is the doctype of the payment entry
			"width": 180,
			"link": True,  # This turns the field into a clickable link
		},		
		{
			"label": _("Observation"), 
			"fieldname": "custom_observation", 
			"width": 200
		},
	]

	if filters.get("show_remarks"):
		columns.extend([{"label": _("Remarks"), "fieldname": "remarks", "width": 400}])

	return columns