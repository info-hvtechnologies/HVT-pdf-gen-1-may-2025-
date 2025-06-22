from docxtpl import DocxTemplate


def internship_edit(input_path, output_path, context):
    vowel_list = ["a", "e", "i", "o", "u"]
    first_letter = context["intern_name"].strip()[0].lower()
    if first_letter in vowel_list:
        a_ = {"a": "an"}
        context.update(a_)
    else:
        a_ = {"a": "a"}
        context.update(a_)
    # Load the template
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
#                 "intern_name": "Diddy",
#                 "amount": "6000",
#                 "amount_in_words": "Six thousand rupees only",
#                 "valid_date": "22/3/1290",
#                 "designation": "General Manager",
#                 "m": "9",
#             }
# internship_edit("app_cert_female_1.docx", "wowo_1.docx", replacements_docx)

