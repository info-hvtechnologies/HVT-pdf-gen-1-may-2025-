import os
import fitz  # PyMuPDF


class EditTextFile:
    def __init__(self, file_path):
        self.file_path = file_path

    def modify_pdf_fields(self, output_pdf, modifications, default_y_offset=0, default_x_offset=0):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Input PDF not found: {self.file_path}")

        doc = fitz.open(self.file_path)
        print(f"📄 Processing {len(doc)} pages...")

        for page_num, page in enumerate(doc):
            text_instances = page.get_text("words")

            for field, mod_value in modifications.items():
                # Handle per-field offsets
                if isinstance(mod_value, tuple):
                    new_value = mod_value[0]
                    x_offset = mod_value[1] if len(mod_value) > 1 else default_x_offset
                    y_offset = mod_value[2] if len(mod_value) > 2 else default_y_offset
                else:
                    new_value = mod_value
                    x_offset = default_x_offset
                    y_offset = default_y_offset

                found = False
                variations = [
                    field,
                    field.strip(),
                    field.replace(" ", ""),
                    field.upper(),
                    field.lower()
                ]

                for variation in variations:
                    instances = page.search_for(variation)
                    if instances:
                        for inst in instances:
                            try:
                                # Redact the placeholder
                                page.add_redact_annot(inst, fill=(1, 1, 1))
                                page.apply_redactions()

                                # Insert replacement text at adjusted position
                                insert_x = inst.x0 + x_offset
                                insert_y = inst.y0 + (inst.y1 - inst.y0) / 2 + y_offset
                                page.insert_text(
                                    (insert_x, insert_y),
                                    new_value,
                                    fontsize=20,
                                    color=(0, 0, 0),
                                    fontname="helv"
                                )
                                found = True
                                print(f"✅ Replaced '{field}' on page {page_num + 1} at ({insert_x:.2f}, {insert_y:.2f})")
                            except Exception as e:
                                print(f"❌ Error replacing '{field}': {e}")
                                continue
                    if found:
                        break

                if not found:
                    print(f"⚠️ Placeholder '{field}' not found on page {page_num + 1}")

        doc.save(output_pdf)
        doc.close()
        print(f"✅ Saved modified PDF to {output_pdf}")



# modifications = {
#     "{ client_name }": ("    Jane Doe", 0, 7),       # y_offset = 10 for client name
#     "{ date }": ("May 17, 2025", -30, 0)           # x_offset = 15 for date
# }
#
# editor = EditTextFile("seven.pdf")
# editor.modify_pdf_fields("sevenified_15.pdf", modifications)



# # Example usage
# input_pdf = "seven.pdf"
# output_pdf = "sevenfied_1.pdf"
# client_name = "John Doe"  # Replace with the actual client name
# date_str = datetime.now().strftime("%Y-%m-%d")  # Current date in YYYY-MM-DD format
#
# replace_placeholders(input_pdf, output_pdf, client_name, date_str)
