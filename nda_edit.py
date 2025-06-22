from docxtpl import DocxTemplate


def nda_edit(input_path, output_path, context):
    # Load the template
    doc = DocxTemplate(input_path)
    # Render the template
    doc.render(context)

    # Save the filled document
    doc.save(output_path)

    print(f"{output_path} has been created!")



# replacements_docx = {
#                 "invoice_date": "22-3-1290",
#                 "client_name": "Diddy",
#                 "company_name": "DAVE",
#                 "client_address":"Ajalejo Street",
#                 "client_email": "example@email.com",
#                 "project_name": "Tabby",
#                 "invoice_no": "987TY345",
#                 "client_no": "0987655678"
#             }
# nda_edit("app_invoice_1.docx", "wowo_2.docx", replacements_docx)

