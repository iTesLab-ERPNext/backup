frappe.listview_settings["Item"] = {
	add_fields: ["item_name", "stock_uom", "item_group", "image", "has_variants", "end_of_life", "disabled"],
	filters: [["disabled", "=", "0"]],

	get_indicator: function (doc) {
		if (doc.disabled) {
			return [__("Disabled"), "grey", "disabled,=,Yes"];
		} else if (doc.end_of_life && doc.end_of_life < frappe.datetime.get_today()) {
			return [__("Expired"), "grey", "end_of_life,<,Today"];
		} else if (doc.has_variants) {
			return [__("Template"), "orange", "has_variants,=,Yes"];
		} else if (doc.variant_of) {
			return [__("Variant"), "green", "variant_of,=," + doc.variant_of];
		}
	},

	reports: [
		{
			name: "Stock Summary",
			route: "/app/stock-balance",
		},
		{
			name: "Stock Ledger",
			report_type: "Script Report",
		},
		{
			name: "Stock Balance",
			report_type: "Script Report",
		},
		{
			name: "Stock Projected Qty",
			report_type: "Script Report",
		},
	],
	ormatters: {
        name: function(value, doc) {
            const baseUrl = frappe.urllib.get_base_url(); // URL de base de l'application
            const reportUrl = `/app/query-report/Item%20Transactions?item_code=${encodeURIComponent(value)}&valuation_field_type=Currency`;

            // Ajouter un bouton pour afficher les données dans un popup
            return `<a href="javascript:void(0)" 
                        onclick="event.stopPropagation(); openReportPopup('${value}', '${reportUrl}')"
                        style="text-decoration: none;">
                        <i class="fa fa-file" aria-hidden="true" 
                           style="color:rgb(139, 178, 236); font-size: 20px; cursor: pointer;" 
                           title="${__("See article transactions")}"></i>
                    </a>`;
        }
    }
};

// Fonction pour ouvrir le popup du rapport
window.openReportPopup = function(item_code, reportUrl) {
    const dialog = new frappe.ui.Dialog({
		title: `${__("Item Transactions")} : ${item_code}`,
		fields: [
            { label: `${__("Report")}`, fieldname: 'report_data', fieldtype: 'HTML' }
        ],
        primary_action_label: 'Fermer',
        primary_action: function() {
            dialog.hide();
        }
    });

    dialog.show();

    frappe.call({
        method: "frappe.desk.query_report.run",
        args: {
            report_name: "Item Transactions",
            filters: { item_code: item_code }
        },
        callback: function(response) {
            if (response && response.message) {
                const reportHTML = formatReportHTML(response.message.result);
                dialog.fields_dict.report_data.$wrapper.html(reportHTML);
            } else {
                dialog.fields_dict.report_data.$wrapper.html(`<p>${__('No Data')}</p>`);
            }
        }
    });
};

function formatReportHTML(data) {
    if (!data || data.length === 0) {
        return `<p>${__('No Transactions')}</p>`;
    }

    let html = "<div class='report table-scroll-container' id='report'>"; // Ajout de la classe de conteneur pour le défilement
    html += "<style>th { white-space: nowrap; }</style>"; // CSS pour empêcher le retour à la ligne dans les <th>
    html += "<table class='table table-bordered'><thead><tr>";
    
    const columns = [
        {"label": __("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 150},
        {"label": __("Item"), "fieldname": "item_code", "fieldtype": "Link", "width": 150},
        {"label": __("Qty Start"), "fieldname": "incoming_qty", "fieldtype": "Float", "width": 100},
        {"label": __("Output Qty"), "fieldname": "outgoing_qty", "fieldtype": "Float", "width": 100},
        {"label": __("Balance of Qty"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 100},
        {"label": __("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "width": 200},
        {"label": __("Transaction Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 180},
        {"label": __("Transaction No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "width": 180},
        {"label": __("Current Qty"), "fieldname": "qty_after_transaction", "fieldtype": "Float", "width": 150},
        {"label": __("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 150},
        {"label": __("Transaction Value"), "fieldname": "transaction_amount", "fieldtype": "Currency", "width": 150},
    ];

    // Créer les en-têtes du tableau
    columns.forEach(col => {
        html += `<th style="width: ${col.width}px">${__(col.label)}</th>`;
    });

    html += "</tr></thead><tbody>";

    // Ajouter les lignes de données dans le tableau
    data.forEach(row => {
        html += "<tr>";
        columns.forEach(col => {
            const value = row[col.fieldname] !== null ? frappe.utils.escape_html(row[col.fieldname]) : "";
            html += `<td>${value}</td>`;
        });
        html += "</tr>";
    });

    html += "</tbody></table></div>"; // Ferme le conteneur
    return html;
};

frappe.help.youtube_id["Item"] = "qXaEwld4_Ps";
