from docxtpl import DocxTemplate


def relieve_edit(input_path, output_path, context):
    doc = DocxTemplate(input_path)
    # Render the template
    doc.render(context)

    # Save the filled document
    doc.save(output_path)

    print(f"{output_path} has been created!")

# replacements_docx = {
#                 "today_date": "22-3-1290",
#                 "start_date": "22-3-1290",
#                 "end_date": "22-6-1290",
#                 "intern_name": "Diddy",
#                 "designation": "General Manager",
#                 "m": "9",
#             }
# relieve_edit("app_reli_4.docx", "wowo_4.docx", replacements_docx)

