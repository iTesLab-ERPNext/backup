frappe.listview_settings["Supplier"] = {
	add_fields: ["supplier_name", "supplier_group", "image", "on_hold"],
	get_indicator: function (doc) {
		if (cint(doc.on_hold)) {
			return [__("On Hold"), "red"];
		}
	},
	formatters: {
        name: function(value, doc) {
            const currentUrl = window.location.href; // Full URL of the current page
            const url = new URL(currentUrl); // Create a URL object from the current URL
            const baseUrl = `${url.protocol}//${url.host}`; // Extract the base URL
            const itemUrl = `${baseUrl}/app/query-report/Supplier%20Transactions?supplier=${encodeURIComponent(value)}&valuation_field_type=Currency`;

            // Ajouter un bouton pour afficher les données dans un popup
            return `<a href="javascript:void(0)" 
                        onclick="event.stopPropagation(); openReportPopup('${value}', '${itemUrl}')"
                        style="text-decoration: none;">
                        <i class="fa fa-file" aria-hidden="true" 
                           style="color: rgb(139, 178, 236); font-size: 20px; cursor: pointer;" 
                           title="${__("See supplier transactions")}"></i>
                    </a>`;
        }
    }
};

// Fonction pour ouvrir le popup du rapport
window.openReportPopup = function(supplier_name, reportUrl) {
    const dialog = new frappe.ui.Dialog({
        title: `${__("Supplier Transactions")} : ${supplier_name}`,
        fields: [
            { label: `${__("Report")}`, fieldname: 'report_data', fieldtype: 'HTML' }
        ],
        primary_action_label: 'Fermer',
        primary_action: function() {
            dialog.hide();
        }
    });

    dialog.show();

    // Appel du rapport avec le filtre supplier
    frappe.call({
        method: "frappe.desk.query_report.run",
        args: {
            report_name: "Supplier Transactions",
            filters: { supplier: supplier_name }  // Utilisation du filtre 'supplier'
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

    let html = "<div class='report table-scroll-container'>"; // Ajout de la classe de conteneur pour le défilement
    html += "<style>th { white-space: nowrap; }</style>"; // CSS pour empêcher le retour à la ligne dans les <th>
    html += "<table class='table table-bordered'><thead><tr>";
    
    const columns = [
        { "label": __("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 180 },
        { "label": __("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 200 },
        { "label": __("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "document_type", "width": 200 },
        { "label": __("Purchases"), "fieldname": "credit", "fieldtype": "Currency", "width": 150 },
        { "label": __("Payments"), "fieldname": "debit", "fieldtype": "Currency", "width": 150 },
        { "label": __("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 150 },
        { "label": __("Observation"), "fieldname": "observation", "fieldtype": "Data", "width": 200 },
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
            let value = row[col.fieldname] !== null && row[col.fieldname] !== undefined ? row[col.fieldname] : 0;

            // Appliquer les couleurs uniquement pour les colonnes "Achats", "Paiements" et "Solde"
            if (["credit", "debit", "balance"].includes(col.fieldname)) {
                // Vérifier si la valeur est vide
                let displayValue = (value === null || value === undefined || value === "") ? 0 : value;

                // Formater la valeur comme une devise sans balises HTML
                const formattedValue = frappe.format(displayValue, {
                    fieldtype: "Currency",
                    options: "currency", // Utilise la devise configurée (ex. DA)
                }).replace(/<\/?[^>]+(>|$)/g, ""); // Supprimer toutes les balises HTML

                // Déterminer la couleur selon la valeur
                const color = displayValue > 0 ? "green" : displayValue < 0 ? "red" : "black";

                // Ajouter la cellule formatée
                html += `<td style="color: ${color};">${frappe.utils.escape_html(formattedValue)}</td>`;
            } else {
                // Si la colonne n'est pas concernée par la mise en couleur
                html += `<td>${frappe.utils.escape_html(value)}</td>`;
            }
        });
        html += "</tr>";
    });

    html += "</tbody></table></div>"; // Ferme le conteneur
    return html;
}