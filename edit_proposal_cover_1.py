# import fitz  # PyMuPDF
#
#
# def replace_pdf_placeholders(input_path, output_path, replacements, y_offset=0):
#
#     doc = fitz.open(input_path)
#
#     for page in doc:
#         for placeholder, replacement in replacements.items():
#             text_instances = page.search_for(placeholder)
#             for inst in text_instances:
#                 # Draw a white rectangle over the old text
#                 page.draw_rect(inst, color=(1, 1, 1), fill=(1, 1, 1))
#                 # Insert new text with vertical offset
#                 new_position = fitz.Point(inst.x0, inst.y0 + y_offset)
#                 page.insert_text(new_position, replacement, fontsize=22, color=(0, 0, 0))
#
#     doc.save(output_path)
#     doc.close()
#     print(f"Updated PDF saved to: {output_path}")

import fitz  # PyMuPDF

def replace_pdf_placeholders(input_path, output_path, replacements, y_offset=0, padding=7):
    doc = fitz.open(input_path)

    for page in doc:
        positions = []

        for placeholder, replacement in replacements.items():
            text_instances = page.search_for(placeholder)
            for inst in text_instances:
                # Expand the rectangle to ensure complete redaction
                inst.x0 -= padding
                inst.y0 -= padding
                inst.x1 += padding + 10
                inst.y1 += padding

                positions.append((inst, replacement))
                page.add_redact_annot(inst, fill=(1, 1, 1))

        page.apply_redactions()

        for inst, replacement in positions:
            new_position = fitz.Point(inst.x0, inst.y0 + y_offset)
            page.insert_text(new_position, replacement, fontsize=20, color=(0, 0, 0))

    doc.save(output_path)
    doc.close()
    print(f"Updated PDF saved to: {output_path}")




# replace_pdf_placeholders(
#     input_path="Cover_Page.pdf",
#     output_path="Cover_Page_Edited++++_5.pdf",
#     replacements={
#         "{ client_name }": "John Doe",
#         "{ client_email }": "john@example.com",
#         "{ client_phone }": "+1234567890",
#         "{ client_country }": "USA",
#         "{ date }": "2025-05-18"
#     },
#     y_offset=19
# )





