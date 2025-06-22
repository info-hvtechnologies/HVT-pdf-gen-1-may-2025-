from docxtpl import DocxTemplate


def offer_edit(input_path, output_path, context):

    doc = DocxTemplate(input_path)
    # Render the template
    doc.render(context)

    # Save the filled document
    doc.save(output_path)

    print(f"{output_path} has been created!")


# replacements_docx = {
#                 "date": "22/3/1290",
#                 "start_date": "22/3/1290",
#                 "end_date": "22/6/1290",
#                 "name": "Diddy",
#                 "amount": "6,000",
#                 "amount_in_words": "Six thousand rupees only.",
#                 "valid_date": "22/3/1290",
#                 "designation": "General Manager",
#                 "m": "9",
#             }
# offer_edit("app_off_1.docx", "wowo_2.docx", replacements_docx)

