import fitz  # PyMuPDF


# def fill_pdf_template(
#     input_path,
#     output_path,
#     replacements,
#     y_offset=-1.5  # negative = upward shift, positive = downward shift
# ):
#     import fitz
#     doc = fitz.open(input_path)
#
#     for page in doc:
#         for placeholder, replacement in replacements.items():
#             text_instances = page.search_for(placeholder)
#             for inst in text_instances:
#                 # Redact old text
#                 page.add_redact_annot(inst, fill=(1, 1, 1))
#                 page.apply_redactions()
#                 # Insert new text with vertical adjustment
#                 adjusted_point = fitz.Point(inst.x0, inst.y0 + y_offset)
#                 page.insert_text(adjusted_point, replacement, fontsize=11, fontname="tiro", color=(0, 0, 0))
#
#     doc.save(output_path)
#     doc.close()
#
#
# # _Internship_Duration_ months,
# fill_pdf_template(
#     input_path="Internship Offer Letter Template.pdf",
#     output_path="Filled_Adjusted_11.pdf",
#     replacements={
#         "_Date_": "April 29, 2025",
#         "_Name_,": "John Doe,",
#         "_Position_": "Software Engineering",
#         "_Stipend_/": "15,000",
#         "_Hrs_": "20",
#         "_Internship_Duration_ months,": "Three months,",
#         "_First_Pay_Cheque_Date": "May 1, 2025."
#     },
#     y_offset=11  # You can experiment with this
# )
# "_Position_ Intern with Hv Technologies. In this position, you will report directly to Hardik Vij, starting _Date_."




def fill_pdf_template(
    input_path,
    output_path,
    replacements,
    y_offset=-1.5,
    default_fontsize=11,
    fontname="tiro"
):
    import fitz
    doc = fitz.open(input_path)
    font = fitz.Font(fontname=fontname)

    for page in doc:
        for placeholder, replacement in replacements.items():
            text_instances = page.search_for(placeholder)
            for inst in text_instances:
                # Redact old text
                page.add_redact_annot(inst, fill=(1, 1, 1))
                page.apply_redactions()

                # Adjust only for _Position_
                if placeholder == "an _Position_":
                    vowel_list = ['a', 'e', 'i', 'o', 'u']
                    first_alphabet_ = replacement[0].lower()
                    if first_alphabet_ in vowel_list:
                        replacement = "an " + replacement
                    else:
                        replacement = "a " + replacement
                    print(f"replacement: {replacement[0].lower}")
                    max_width = inst.x1 - inst.x0
                    fontsize = default_fontsize
                    text_width = font.text_length(replacement, fontsize)
                    while text_width > max_width and fontsize > 4:
                        fontsize -= 0.5
                        text_width = font.text_length(replacement, fontsize)
                else:
                    fontsize = default_fontsize

                # Insert text at adjusted position
                adjusted_point = fitz.Point(inst.x0, inst.y0 + y_offset)
                page.insert_text(adjusted_point, replacement, fontsize=fontsize, fontname=fontname, color=(0, 0, 0))

    doc.save(output_path)
    doc.close()



#
# fill_pdf_template(
#     input_path="Internship Offer Letter Template.pdf",
#     output_path="Filled_Adjusted_48.pdf",
#     replacements={
#         "an _Position_": "Software Engineering",
#         "_Date_": "April 29, 2025",
#         "_Name_,": "John Doe,",
#         "_Stipend_/": "15,000",
#         "_Hrs_": "20",
#         "_Internship_Duration_ months,": "Three months,",
#         "_First_Pay_Cheque_Date": "May 1, 2025."
#     },
#     y_offset=11
# )
