from docxtpl import DocxTemplate
from jinja2 import Environment

def extract_placeholders(docx_path):

    doc = DocxTemplate(docx_path)
    env = Environment()
    placeholders = doc.get_undeclared_template_variables(env)
    return list(placeholders)


# template_path = "app_invoice_1.docx"
# placeholders = extract_placeholders(template_path)
#
# # print("📌 Placeholders found:")
# for name in placeholders:
#     print(name)