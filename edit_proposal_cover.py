import os
import subprocess
from docx import Document
import fitz


class EditTextFile:
    def __init__(self, file_path):
        self.file_path = file_path

    def modify_pdf_fields(self, output_pdf, modifications, y_offset=0):
        input_pdf = self.file_path

        try:
            if not os.path.exists(input_pdf):
                raise FileNotFoundError(f"Input PDF not found: {self.file_path}")

            doc = fitz.open(self.file_path)
            print(f"Processing {len(doc)} pages...")

            for page_num, page in enumerate(doc):
                # print(f"\nAnalyzing page {page_num + 1}...")
                text_instances = page.get_text("words")

                if not text_instances:
                    print("Warning: No text found on this page (may be scanned)")
                    continue

                # print("Text elements found on page:")
                for inst in text_instances:
                    print(".")

                for field, new_value in modifications.items():
                    found = False
                    variations = [
                        field,
                        field.replace(":", ""),
                        field.replace(":", " :"),
                        field.lower(),
                        field.upper(),
                        field.replace(" ", ""),
                        field.replace(" ", "  ")
                    ]

                    for variation in variations:
                        instances = page.search_for(variation)
                        if instances:
                            # print(f"Found potential match for '{variation}' on page {page_num + 1}")
                            for inst in instances:
                                try:
                                    if field == "14 April 2025":
                                        # Redact and replace date field directly using rectangle
                                        # Custom X position — adjust this as needed
                                        custom_x = 45
                                        custom_y = inst.y0 + (inst.y1 - inst.y0) / 2 + y_offset

                                        # Redact original date region
                                        date_area = fitz.Rect(
                                            inst.x0 - 2,
                                            inst.y0 - 2,
                                            inst.x1 + 100,
                                            inst.y1 + 2
                                        )
                                        page.add_redact_annot(date_area, fill=(1, 1, 1))
                                        page.apply_redactions()

                                        # Custom-positioned new date
                                        page.insert_text(
                                            (custom_x, custom_y),
                                            new_value,
                                            fontsize=23,
                                            color=(0, 0, 0),
                                            fontname="helv"
                                        )

                                    else:
                                        value_area = fitz.Rect(
                                            inst.x1,
                                            inst.y0 - 2,
                                            inst.x1 + 250,
                                            inst.y1 + 2
                                        )
                                        page.add_redact_annot(value_area, fill=(1, 1, 1))
                                        page.apply_redactions()

                                        y_pos = inst.y0 + (inst.height / 2) + y_offset
                                        page.insert_text(
                                            (inst.x1 + 2, y_pos),
                                            new_value,
                                            fontsize=23,
                                            color=(0, 0, 0),
                                            fontname="helv"
                                        )

                                    found = True
                                    # print(f"✅ Modified field: {field}")
                                    break

                                except Exception as e:
                                    print(f"❌ Error processing {field}: {str(e)}")
                                    continue

                            if found:
                                break

                    if not found:
                        print(f"⚠️ Warning: Field '{field}' not found on page {page_num + 1}")

            if len(doc) > 0:
                doc.save(output_pdf)
                print(f"\n✅ Successfully saved modified PDF to {output_pdf}")
            else:
                print("❌ Error: No pages processed - output not saved")

        except Exception as e:
            print(f"❌ Critical error: {str(e)}")
        finally:
            if 'doc' in locals():
                doc.close()



