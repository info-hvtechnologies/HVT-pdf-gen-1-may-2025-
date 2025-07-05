import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pycountry
import streamlit as st
from nda_edit import nda_edit
from docx_pdf_converter import main_converter
from edit_proposal_cover_1 import replace_pdf_placeholders
from merge_pdf import Merger
import tempfile
from firebase_conf import auth, rt_db, bucket, firestore_db
import pdfplumber
from firebase_admin import storage
import json
import base64
import random
# import os
# from datetime import datetime
from google.cloud import storage, firestore
from invoice_editor import invoice_edit
from testimonial_page_edit import EditTextFile
from offer_editor import offer_edit
import re
from load_config import LOAD_LOCALLY

# LOAD_LOCALLY = False


def format_currency_amount(raw_price: str) -> str:
    # Extract digits (optionally include decimal point)
    match = re.search(r"\d+(?:\.\d+)?", raw_price)
    if not match:
        return "0"

    number = float(match.group())
    return f"{number:,.2f}" if '.' in match.group() else f"{int(number):,}"


def save_generated_file_to_firebase_2(
        local_file_path,
        doc_type,
        bucket,
        file_type,
        file_details,
        proposal_subdir=None,
        normalized_subdir=None,
):
    try:
        # Get filename from local path
        filename = os.path.basename(local_file_path)

        # Define storage path in Firebase Storage
        storage_path = f"HVT_DOC_Gen/generated/{doc_type}/{filename}"

        # Upload to Firebase Storage
        blob = bucket.blob(storage_path)
        blob.upload_from_filename(local_file_path)

        # Get public URL
        download_url = blob.public_url

        file_details.update(
            {
                "doc_type": doc_type,
                "file_type": file_type,
                "storage_path": storage_path,
            }
        )

        firestore_db.collection("generated_files").add(file_details)

        st.success("✅ File uploaded and metadata saved to Firestore.")
        return storage_path, download_url

    except Exception as e:
        st.error(f"❌ Failed to upload file or save metadata: {e}")
        return None, None


def generate_download_link(file_path, filename, file_type, doc_type):
    with open(file_path, "rb") as f:
        file_bytes = f.read()
        b64 = base64.b64encode(file_bytes).decode()

    href = f'''
    <a href="data:application/pdf;base64,{b64}" download="{filename}"
       style="display: inline-block;
              padding: 12px 24px;
              background: linear-gradient(45deg, #2196F3, #00BCD4);
              color: white;
              text-decoration: none;
              border-radius: 6px;
              font-weight: bold;
              font-family: sans-serif;
              box-shadow: 0 4px 6px rgba(0,0,0,0.1);
              transition: all 0.3s ease;
              border: none;
              cursor: pointer;">
       📥 Download {doc_type} {file_type}
    </a>
    '''
    st.markdown(href, unsafe_allow_html=True)


def pdf_view(file_input):
    try:

        with pdfplumber.open(file_input) as pdf:
            st.subheader("Preview")
            for i, page in enumerate(pdf.pages):
                if LOAD_LOCALLY:
                    st.image(
                        page.to_image(resolution=150).original,
                        caption=f"Page {i + 1}",
                        use_column_width=True
                        #use_container_width
                    )
                else:
                    st.image(
                        page.to_image(resolution=150).original,
                        caption=f"Page {i + 1}",
                        use_container_width=True
                        # use_container_width
                    )
    except Exception as e:
        st.warning(f"Couldn't generate PDF preview: {str(e)}")


from num2words import num2words

def currency_to_words_in_inr(formatted_amount: str) -> str:
    # Remove commas and convert to float
    try:
        amount = float(formatted_amount.replace(',', ''))
    except ValueError:
        return "Invalid amount"

    # Split into rupees and paise
    rupees = int(amount)
    paise = round((amount - rupees) * 100)

    rupees_words = num2words(rupees, lang='en_IN').title() + " Rupees"
    paise_words = f" and {num2words(paise, lang='en_IN').title()} Paise" if paise else ""

    return rupees_words + paise_words


def fetch_and_organize_templates(firestore_db, base_temp_dir=None):
    # Base temp dir
    if not base_temp_dir:
        base_temp_dir = tempfile.mkdtemp()

    # Main collection reference
    collection_ref = firestore_db.collection("HVT_DOC_Gen")

    # Iterate through each document type (e.g., Proposal, NDA, etc.)
    doc_types = collection_ref.stream()
    for doc in doc_types:
        doc_type = doc.id  # e.g., "Proposal", "NDA", etc.
        templates_ref = collection_ref.document(doc_type).collection("templates")
        templates = templates_ref.stream()

        for template in templates:
            data = template.to_dict()
            file_url = data["download_url"]
            file_name = data["name"]

            if doc_type == "Proposal" and "proposal_section_type" in data:
                # Subdir structure for proposals
                subfolder = data["proposal_section_type"].lower() + "_templates"
                target_dir = os.path.join(base_temp_dir, "proposal", subfolder)
            else:
                target_dir = os.path.join(base_temp_dir, doc_type.lower().replace(" ", "_"))

            os.makedirs(target_dir, exist_ok=True)

            file_path = os.path.join(target_dir, file_name)

            try:
                # Download the file
                response = requests.get(file_url)
                if response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                else:
                    print(f"Failed to download {file_name} (HTTP {response.status_code})")
            except Exception as e:
                print(f"Error downloading {file_name}: {str(e)}")

    return base_temp_dir


import json


# def truncate_value(value, max_length=80):
#     from datetime import datetime
#     import collections
#
#     # Recursively handle dictionaries and lists
#     if isinstance(value, dict):
#         return {k: truncate_value(v, max_length) for k, v in value.items()}
#     if isinstance(value, list):
#         return [truncate_value(v, max_length) for v in value]
#
#     # Handle Firestore timestamp and datetime objects
#     if isinstance(value, datetime):
#         return value.isoformat()
#     if hasattr(value, 'isoformat'):
#         return value.isoformat()
#
#     # Truncate long strings
#     if isinstance(value, str) and len(value) > max_length:
#         return value[:max_length] + "..."
#
#     return value


# def truncate_value(value, max_length=80):
#     # Convert datetime-like values to string
#     if isinstance(value, datetime):
#         return value.isoformat()
#     # Firestore timestamps use a custom class
#     if hasattr(value, 'isoformat'):
#         return value.isoformat()
#     # Truncate long strings
#     if isinstance(value, str) and len(value) > max_length:
#         return value[:max_length] + "..."
#     return value


def truncate_value(value, max_length=80):
    from datetime import datetime

    # Recursively handle dictionaries and lists
    if isinstance(value, dict):
        return {k: truncate_value(v, max_length) for k, v in value.items()}
    if isinstance(value, list):
        return [truncate_value(v, max_length) for v in value]

    # Handle datetime-like values
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, 'isoformat'):
        return value.isoformat()

    # Truncate long strings
    if isinstance(value, str) and len(value) > max_length:
        return value[:max_length] + "..."

    return value


def dict_to_colored_html(d, indent=0):
    html = ""
    space = "&nbsp;" * 4 * indent

    for key, value in d.items():
        key_html = f'<span style="color:#00BFFF;">"{key}"</span>'  # sky blue keys

        if isinstance(value, dict):
            html += f"{space}{key_html}: {{<br>{dict_to_colored_html(value, indent + 1)}{space}}},<br>"
        elif isinstance(value, list):
            list_html = ", ".join(
                f'<span style="color:#90EE90;">"{truncate_value(v)}"</span>' if isinstance(v, str)
                else f'<span style="color:#FFD700;">{truncate_value(v)}</span>'
                for v in value
            )
            html += f"{space}{key_html}: [ {list_html} ],<br>"
        else:
            val_color = "#90EE90" if isinstance(value, str) else "#FFD700"  # lightgreen for str, gold for other
            val_display = f'"{value}"' if isinstance(value, str) else value
            html += f'{space}{key_html}: <span style="color:{val_color};">{val_display}</span>,<br>'
    return html



def handle_internship_certificate():
    st.title("📄 Internship Certificate Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Internship"
    metadata = regenerate_data.get('metadata', {})

    # Initialize session state for multi-page form
    if 'form_step' not in st.session_state:
        st.session_state.form_step = 1
        st.session_state.offer_data = {}

    # Step 1: Collect information
    if st.session_state.form_step == 1:
        with st.form("internship_offer_form"):
            name = st.text_input("Intern Name", value=metadata.get('intern', ''))

            default_position = metadata.get("position", "")
            json_path = "roles.json"
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                    data_ = data.get("internship_position", [])
            except Exception as e:
                st.error(f"Error loading roles from JSON: {str(e)}")
                data_ = []

            # Find default index for selectbox
            try:
                default_index = data_.index(default_position) if default_position in data_ else 0
            except:
                default_index = 0

            position = st.selectbox("Internship Position", data_, index=default_index if data_ else 0)
            # sex = st.selectbox("Select Intern Sex:", ["Male", "Female", "Other", "Prefer not to say"])
            default_start_date = default_start_date = datetime.strptime(metadata.get("start_date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
            start_date = st.date_input("Start Date", value=default_start_date)
            duration_str = metadata.get("duration", "3")
            match = re.search(r"\d+", duration_str)
            default_duration = int(match.group()) if match else 3
            duration = st.number_input("Internship Duration (In Months)", min_value=1, max_value=24, step=1, value=default_duration)
            default_end_date = datetime.strptime(metadata.get("end_date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
            end_date = st.date_input("End Date", value=default_end_date)

            if st.form_submit_button("Generate Certificate"):
                if not name.strip():
                    st.error("Please enter candidate name")
                    st.stop()

                st.session_state.offer_data = {
                    "name": name.strip(),
                    "position": position,
                    # "sex": sex,
                    "date": datetime.now().date().strftime('%d/%m/%Y'),
                    "start_date": start_date.strftime('%d/%m/%Y'),
                    "duration": duration,
                    "end_date": end_date.strftime('%d/%m/%Y'),
                }
                st.session_state.form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.form_step == 2:
        st.subheader("Select Certificate Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'form_step', 1))

        # Create temp directory
        temp_dir = os.path.join(tempfile.gettempdir(), "as_offer")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Internship Certificate"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose a certificate style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_certificate_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)


                    # pretty_metadata = {
                    #     k: truncate_value(v) for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    #
                    # st.text_area("Metadata", json.dumps(pretty_metadata, indent=2), height=300)



                    # st.code(json.dumps(display_metadata, indent=2), language="json")

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)


            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate Certificate Document"):
            st.session_state.form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


    # Step 3: Preview and download
    elif st.session_state.form_step == 3:
        with st.spinner("Loading template and generating certificate..."):
            st.button("← Back to Template select", on_click=lambda: setattr(st.session_state, 'form_step', 2))
            context = {
                "date": st.session_state.offer_data["date"],
                "start_date": st.session_state.offer_data["start_date"],
                "end_date": st.session_state.offer_data["end_date"],
                "intern_name": st.session_state.offer_data["name"],
                "designation": st.session_state.offer_data["position"],
                "m": st.session_state.offer_data["duration"],

            }


            temp_dir = os.path.join(tempfile.gettempdir(), "as_offer")
            os.makedirs(temp_dir, exist_ok=True)

            template_path = st.session_state.selected_certificate_template_path
            # blob.download_to_filename(template_path)

            docx_output = os.path.join(temp_dir, "cert.docx")
            pdf_output = os.path.join(temp_dir, "cert.pdf")

            from inter_edit import internship_edit
            internship_edit(template_path, docx_output, context)
            main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview Certificate")
            col1, col2 = st.columns(2)

            with col1:
                st.write(f"**Start Date:** {context['date']}")
                st.write(f"**Intern Name:** {context['intern_name']}")
                st.write(f"**Position:** {context['designation']}")


            with col2:
                st.write(f"**Duration:** {st.session_state.offer_data['duration']} months")
                st.write(f"**End Date:** {context['end_date']}")
                # st.write(f"**First Paycheck:** {context['first_paycheque_date']}")

            pdf_view(pdf_output)

            st.subheader("Download Documents")
            col1, col2 = st.columns(2)
            file_prefix = f"{context['intern_name'].replace(' ', ' ')} - {context['designation'].replace(' ', ' ')}"
            file_upload_details = {
                "intern": context['intern_name'],
                "position": context['designation'],
                "start_date": context['start_date'],
                "duration": f"{st.session_state.offer_data['duration']} months",
                "end_date": context['end_date'],
                "date": context['date'],
                # "first_pay_cheque_date": context['first_paycheque_date'],
                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:
                if os.path.exists(pdf_output):

                    if st.button("✅ Confirm and Upload Internship Certificate PDF", key="upload_pdf"):

                        save_generated_file_to_firebase_2(
                            pdf_output,
                            "Internship",
                            bucket,
                            "PDF",
                            file_upload_details
                        )

                        st.success("Now you can download the file:")
                        # Step 2: Show download link only after upload
                        generate_download_link(pdf_output,
                                               f"{file_prefix} - Certificate.pdf",
                                               "PDF", "Internship")

                else:
                    st.warning("PDF file not available")

            with col2:
                if os.path.exists(docx_output):

                    if st.button("✅ Confirm and Upload Internship Certificate DOCX", key="upload_docx"):

                        save_generated_file_to_firebase_2(
                            docx_output,
                            "Internship",
                            bucket,
                            "DOCX",
                            file_upload_details
                        )
                        st.success("Now you can download the file:")
                        # Step 2: Show download link only after upload
                        generate_download_link(docx_output,
                                               f"{file_prefix} - Certificate.docx",
                                               "DOCX", "Internship")

                else:
                    st.warning("DOCX file not available")


    # try:
    #     for file_path in [template_path, docx_output, pdf_output]:
    #         if file_path and os.path.exists(file_path):
    #             os.unlink(file_path)
    # except Exception as e:
    #     st.warning(f"Could not clean up temporary files: {str(e)}")


def handle_internship_offer():
    st.title("📄 Internship Offer Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Internship Offer"
    metadata = regenerate_data.get('metadata', {})

    default_date = default_start_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    default_name = metadata.get("name", "")
    default_position = metadata.get("designation", "")
    default_start_date = datetime.strptime(metadata.get("start_date", datetime.now().strftime('%d/%m/%Y')),
                                           '%d/%m/%Y').date()
    default_end_date = datetime.strptime(metadata.get("end_date", datetime.now().strftime('%d/%m/%Y')),
                                         '%d/%m/%Y').date()
    default_valid_date =datetime.strptime(metadata.get('valid_date', datetime.now().strftime('%d/%m/%Y')),
                                          '%d/%m/%Y').date()
    duration_str = metadata.get("duration", "")
    match = re.search(r"\d+", duration_str)
    default_duration = int(match.group()) if match else 3

    stipend_str = metadata.get("amount", "")
    match = re.search(r"\d+", stipend_str)
    default_stipend = int(match.group()) if match else 0

    # Initialize session state for multi-page form
    if 'internship_offer_form_step' not in st.session_state:
        st.session_state.internship_offer_form_step = 1
        st.session_state.internship_offer_data = {}

    if st.session_state.internship_offer_form_step == 1:
        # Step 1: Collect information
        with st.form("internship_offer_form"):
            date = st.date_input("Offer Date", value=metadata.get('date', default_date))

            intern_name = st.text_input("Name", value=default_name)
            json_path = "roles.json"
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                    data_ = data.get("internship_position", [])
            except Exception as e:
                st.error(f"Error loading roles from JSON: {str(e)}")
                data_ = []

            # Find default index for selectbox
            try:
                default_index = data_.index(default_position) if default_position in data_ else 0
            except:
                default_index = 0

            position = st.selectbox("Internship Position", data_, index=default_index if data_ else 0)


            duration = st.number_input("Internship Duration (In Months)", min_value=1, max_value=24, step=1, value=default_duration)
            start_date = st.date_input("Start Date", value=default_start_date)
            end_date = st.date_input("End Date", value=default_end_date)
            valid_date = st.date_input("Offer Valid Date", value=default_valid_date)
            stipend = st.text_input("Stipend (Figures only)", value=default_stipend)

            if st.form_submit_button("Generate Offer"):
                st.session_state.internship_offer_data = {
                    "date": f"{date.day}/{date.month}/{date.year}",
                    "intern_name": intern_name,
                    "position": position,
                    "duration": duration,
                    "start_date": f"{start_date.day}/{start_date.month}/{start_date.year}",
                    "end_date": f"{end_date.day}/{end_date.month}/{end_date.year}",
                    "valid_date": f"{valid_date.day}/{valid_date.month}/{valid_date.year}",
                    "amount": f"₹ {format_currency_amount(stipend)}",
                    "amount_in_words": currency_to_words_in_inr(format_currency_amount(stipend)),
                }
                st.session_state.internship_offer_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.internship_offer_form_step == 2:
        st.subheader("Select Offer Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'internship_offer_form_step', 1))

        # Create temp directory
        import os
        temp_dir = os.path.join(tempfile.gettempdir(), "as__inter_offer")
        os.makedirs(temp_dir, exist_ok=True)
        temp_dir = os.path.join(tempfile.gettempdir(), "as__inter_offer")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Internship Offer"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose a offer style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_offer_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)

            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate Offer Document"):
            st.session_state.internship_offer_form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


    elif st.session_state.internship_offer_form_step == 3:
        # Step 2: Preview and download
        # st.success("NDA generated successfully!")
        with st.spinner("Generating offer..."):
            st.button("← Back to Template select ", on_click=lambda: setattr(st.session_state, 'internship_offer_form_step', 2))

           # Generate documents
            replacements_docx = {
                "date": st.session_state.internship_offer_data["date"],
                "start_date": st.session_state.internship_offer_data["start_date"],
                "end_date": st.session_state.internship_offer_data["end_date"],
                "name": st.session_state.internship_offer_data["intern_name"],
                "amount": st.session_state.internship_offer_data["amount"],
                "amount_in_words": st.session_state.internship_offer_data["amount_in_words"],
                "valid_date": st.session_state.internship_offer_data["valid_date"],
                "designation": st.session_state.internship_offer_data["position"],
                "m": st.session_state.internship_offer_data["duration"],

            }

            # Get template from Firestore
            doc_type = "Internship Offer"  # Changed to match your collection name
            try:

                    template_path = st.session_state.selected_offer_template_path

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name

                # Use the downloaded template
                offer_edit(template_path, docx_output, replacements_docx)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview")
            st.write(f"**Agreement Date:** {st.session_state.internship_offer_data['date']}")
            st.write(f"**Intern Name:** {st.session_state.internship_offer_data['intern_name']}")
            st.write(f"**Designation:** {st.session_state.internship_offer_data['position']}")
            st.write(f"**Start Date:** {st.session_state.internship_offer_data['date']}")
            st.write(f"**End Date:** {st.session_state.internship_offer_data['end_date']}")
            st.write(f"**Stipend:** {st.session_state.internship_offer_data['amount']}")
            st.write(f"**Amount in words:** {st.session_state.internship_offer_data['amount_in_words']}")
            st.write(f"**Duration:** {st.session_state.internship_offer_data['duration']} months")

            # PDF preview (requires pdfplumber)
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Documents")
            col1, col2 = st.columns(2)

            file_upload_details = {
                "date": st.session_state.internship_offer_data["date"],
                "start_date": st.session_state.internship_offer_data["start_date"],
                "end_date": st.session_state.internship_offer_data["end_date"],
                "name": st.session_state.internship_offer_data["intern_name"],
                "amount": st.session_state.internship_offer_data["amount"],
                "amount_in_words": st.session_state.internship_offer_data["amount_in_words"],
                "valid_date": st.session_state.internship_offer_data["valid_date"],
                "designation": st.session_state.internship_offer_data["position"],
                "duration": st.session_state.internship_offer_data["duration"],
                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:

                if st.button("✅ Confirm and Upload Internship PDF", key="upload_pdf"):

                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "Internship Offer",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{st.session_state.internship_offer_data['intern_name']} - {st.session_state.internship_offer_data['position']} - Offer Letter.pdf",
                                           "PDF", "Internship Offer")


            with col2:

                if st.button("✅ Confirm and Upload Internship DOCX", key="upload_docx"):

                    save_generated_file_to_firebase_2(
                        docx_output,
                        "Internship Offer",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{st.session_state.internship_offer_data['intern_name']} - {st.session_state.internship_offer_data['position']} - Offer Letter.docx",
                                           "DOCX", "Offer")

        # Clean up temp files
        # try:
        #     import os
        #     os.unlink(template_path)
        #     os.unlink(pdf_output)
        #     os.unlink(docx_output)
        # except:
        #     pass


def handle_relieving_letter():
    st.title("📄 Relieving Letter Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Relieving Letter"
    metadata = regenerate_data.get('metadata', {})

    default_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y'
    ).date()
    default_name = metadata.get("name", "")
    default_position = metadata.get("designation", "")
    default_start_date = datetime.strptime(metadata.get("start_date", datetime.now().strftime('%d-%m-%Y')),
                                           '%d-%m-%Y').date()
    default_end_date = datetime.strptime(metadata.get("end_date", datetime.now().strftime('%d-%m-%Y')),
                                         '%d-%m-%Y').date()
    default_valid_date = datetime.strptime(metadata.get('valid_date', datetime.now().strftime('%d-%m-%Y')),
                                           '%d-%m-%Y').date()

    default_duration = metadata.get("duration", "3")
    if isinstance(default_duration, str):
        match = re.search(r"\d+", default_duration)
        default_duration = int(match.group()) if match else 3
    else:
        default_duration = int(default_duration)

    # Initialize session state for multi-page form
    if 'relieving_letter_form_step' not in st.session_state:
        st.session_state.relieving_letter_form_step = 1
        st.session_state.relieving_letter_data = {}

    if st.session_state.relieving_letter_form_step == 1:
        # Step 1: Collect information
        with st.form("relieving_letter_form"):
            date = datetime.now().date()

            intern_name = st.text_input("Name", value=default_name)
            json_path = "roles.json"
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                    data_ = data.get("internship_position", [])
            except Exception as e:
                st.error(f"Error loading roles from JSON: {str(e)}")
                data_ = []

            # Find default index for selectbox
            try:
                default_index = data_.index(default_position) if default_position in data_ else 0
            except:
                default_index = 0

            position = st.selectbox("Internship Position", data_, index=default_index if data_ else 0)

            duration = st.number_input("Internship Duration (In Months)", min_value=1, max_value=24, step=1, value=default_duration)
            start_date = st.date_input("Start Date", value=default_start_date)
            end_date = st.date_input("End Date", value=default_end_date)


            if st.form_submit_button("Generate Letter"):
                st.session_state.relieving_letter_data = {
                    "date": f"{date.day}-{date.month}-{date.year}",
                    "intern_name": intern_name,
                    "position": position,
                    "duration": duration,
                    "start_date": f"{start_date.day}-{start_date.month}-{start_date.year}",
                    "end_date": f"{end_date.day}-{end_date.month}-{end_date.year}",

                }
                st.session_state.relieving_letter_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.relieving_letter_form_step == 2:
        st.subheader("Select Letter Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'relieving_letter_form_step', 1))

        # Create temp directory
        import os
        temp_dir = os.path.join(tempfile.gettempdir(), "as_letter")
        os.makedirs(temp_dir, exist_ok=True)
        temp_dir = os.path.join(tempfile.gettempdir(), "as_letter")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Relieving Letter"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose a letter style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_letter_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)

            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate Letter Documents"):
            st.session_state.relieving_letter_form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.relieving_letter_form_step == 3:
        # st.session_state.selected_letter_template_path
        # Step 2: Preview and download
        with st.spinner("Loading template and generating letter..."):
            st.button("← Back to Select Template", on_click=lambda: setattr(st.session_state, 'relieving_letter_form_step', 2))

            # Generate documents
            replacements_docx = {
                "today_date": st.session_state.relieving_letter_data["date"],
                "start_date": st.session_state.relieving_letter_data["start_date"],
                "end_date": st.session_state.relieving_letter_data["end_date"],
                "intern_name": st.session_state.relieving_letter_data["intern_name"],
                "designation": st.session_state.relieving_letter_data["position"],
                "m": st.session_state.relieving_letter_data["duration"],

            }

            # Get template from Firestore
            doc_type = "Relieving Letter"  # Changed to match your collection name
            try:
                # template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
                # templates = template_ref.collection("templates").order_by("order_number").limit(1).get()
                #
                # if not templates:
                #     st.error("No templates found in the database for Internship Offer")
                #     return
                #
                # # Get the first template (order_number = 1)
                #
                # template_doc = templates[0]
                # template_data = template_doc.to_dict()
                #
                # # Visibility check
                # if template_data.get('visibility', 'Private') != 'Public':
                #     st.error("This Relieving Letter template is not currently available")
                #     return
                #
                # # File type check
                # if template_data.get(
                #         'file_type') != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                #     st.error("Template is not a valid Word document (.docx)")
                #     return
                #
                # # Check if storage_path exists
                # if 'storage_path' not in template_data:
                #     st.error("Template storage path not found in the database")
                #     return
                #
                # # Download the template file from Firebase Storage
                # # bucket = storage.bucket()
                # blob = bucket.blob(template_data['storage_path'])
                #
                # # Create a temporary file for the template
                # with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_template:
                #     blob.download_to_filename(temp_template.name)

                template_path = st.session_state.selected_letter_template_path

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name
                from releive_editor import relieve_edit

                # Use the downloaded template
                relieve_edit(template_path, docx_output, replacements_docx)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview")
            st.write(f"**Date:** {st.session_state.relieving_letter_data['date']}")
            st.write(f"**Intern Name:** {st.session_state.relieving_letter_data['intern_name']}")
            st.write(f"**Designation:** {st.session_state.relieving_letter_data['position']}")
            st.write(f"**Start Date:** {st.session_state.relieving_letter_data['date']}")
            st.write(f"**End Date:** {st.session_state.relieving_letter_data['end_date']}")
            st.write(f"**Duration:** {st.session_state.relieving_letter_data['duration']} months")

            # PDF preview (requires pdfplumber)
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Documents")
            col1, col2 = st.columns(2)

            file_upload_details = {
                "date": st.session_state.relieving_letter_data["date"],
                "start_date": st.session_state.relieving_letter_data["start_date"],
                "end_date": st.session_state.relieving_letter_data["end_date"],
                "name": st.session_state.relieving_letter_data["intern_name"],
                "designation": st.session_state.relieving_letter_data["position"],
                "duration": st.session_state.relieving_letter_data["duration"],
                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:

                if st.button("✅ Confirm and Upload Letter PDF", key="upload_pdf"):
                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "Relieving Letter",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{st.session_state.relieving_letter_data['intern_name']} - {st.session_state.relieving_letter_data['position']} - Relieving Letter.pdf",
                                           "PDF", "Relieving Letter")

            with col2:

                if st.button("✅ Confirm and Upload Letter DOCX", key="upload_docx"):

                    save_generated_file_to_firebase_2(
                        docx_output,
                        "Relieving Letter",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{st.session_state.relieving_letter_data['intern_name']} - {st.session_state.relieving_letter_data['position']} - Relieving Letter.docx",
                                           "DOCX", "Relieving Letter")

    #     # Clean up temp files
    #     try:
    #         import os
    #         os.unlink(template_path)
    #         os.unlink(pdf_output)
    #         os.unlink(docx_output)
    #     except:
    #         pass


def handle_contract():
    st.title("📄 Contract Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Contract"
    metadata = regenerate_data.get('metadata', {})

    default_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    default_name = metadata.get("client_name", "")
    default_client_company_name = metadata.get("client_company_name", "")
    # default_start_date = datetime.strptime(metadata.get("start_date", datetime.now().strftime('%d/%m/%Y')),
    #                                        '%d/%m/%Y').date()
    default_contract_end = datetime.strptime(metadata.get("contract_end", datetime.now().strftime('%d/%m/%Y')),
                                         '%d/%m/%Y').date()
    default_client_address = metadata.get("client_address", "")

    # Initialize session state for multi-page form
    if 'contract_form_step' not in st.session_state:
        st.session_state.contract_form_step = 1
        st.session_state.contract_data = {}

    if st.session_state.contract_form_step == 1:
        # Step 1: Collect information
        with st.form("contract_form"):
            date = st.date_input("Contract Date", value=default_date)
            client_company_name = st.text_input("Client Company Name", value=default_client_company_name)
            client_name = st.text_input("Client Name", value=default_name)
            client_company_address = st.text_area("Client Company Address", value=default_client_address)
            contract_end = st.date_input("Contract End Date", default_contract_end)

            if st.form_submit_button("Select Contract Template"):
                st.session_state.contract_data = {
                    "date": f"{date.day}/{date.month}/{date.year}",
                    "client_company_name": client_company_name,
                    "client_name": client_name,
                    "client_company_address": client_company_address,
                    "contract_end": f"{contract_end.day}/{contract_end.month}/{contract_end.year}"
                }
                st.session_state.contract_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.contract_form_step == 2:
        st.subheader("Select Contract Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'contract_form_step', 1))

        # Create temp directory
        import os
        temp_dir = os.path.join(tempfile.gettempdir(), "as_contract")
        os.makedirs(temp_dir, exist_ok=True)
        temp_dir = os.path.join(tempfile.gettempdir(), "as_contract")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Project Contract"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose a contract style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_contract_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)

            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate Contract Documents"):
            st.session_state.contract_form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.contract_form_step == 3:
        # Step 2: Preview and download
        # st.success("NDA generated successfully!")
        # st.session_state.selected_contract_template_path
        with st.spinner("Generating contract..."):
            st.button("← Back to Template Select", on_click=lambda: setattr(st.session_state, 'contract_form_step', 2))

            space_ = " "
            the_name = st.session_state.contract_data['client_name']
            if len(the_name) > 14:
                new_text = the_name
            elif len(the_name) < 14:
                if len(the_name) < 8:
                    lenght_dif = 11 - len(the_name)
                    new_text = f"{space_ * lenght_dif}{the_name}"
                else:
                    lenght_dif = 14 - len(the_name)
                    new_text = f"{space_ * lenght_dif}{the_name}"
            else:
                new_text = the_name

            date_str = st.session_state.contract_data["contract_end"]
            contract_end = datetime.strptime(date_str, "%d/%m/%Y")
            formatted_date = contract_end.strftime("%-d %B, %Y")
           # Generate documents
            replacements_docx = {
                "date": st.session_state.contract_data["date"],
                "client_company_name": st.session_state.contract_data["client_company_name"],
                # "client_name": f"        {st.session_state.contract_data['client_name']}",
                "client_name": new_text,
                "client_company_address": st.session_state.contract_data["client_company_address"],
                # "contract_end": st.session_state.contract_data["contract_end"],
                "contract_end": formatted_date,
            }

            # Get template from Firestore
            doc_type = "Project Contract"  # Changed to match your collection name
            try:
                template_path = st.session_state.selected_contract_template_path

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name

                # Use the downloaded template
                # offer_edit(template_path, docx_output, replacements_docx)
                nda_edit(template_path, docx_output, replacements_docx)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview")
            st.write(f"**Agreement Date:** {st.session_state.contract_data['date']}")
            st.write(f"**Client Name:** {st.session_state.contract_data['client_name']}")
            st.write(f"**Company Name:** {st.session_state.contract_data['client_company_name']}")
            st.write(f"**Company Address:** {st.session_state.contract_data['client_company_address']}")
            st.write(f"**Contract End Date:** {st.session_state.contract_data['contract_end']}")

            # PDF preview (requires pdfplumber)
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Documents")
            col1, col2 = st.columns(2)

            file_upload_details = {
                "date": st.session_state.contract_data["date"],
                "client_company_name": st.session_state.contract_data["client_company_name"],
                "client_name": st.session_state.contract_data['client_name'],
                "client_address": st.session_state.contract_data["client_company_address"],
                "contract_end": st.session_state.contract_data["contract_end"],

                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:

                if st.button("✅ Confirm and Upload Contract PDF", key="upload_pdf"):

                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "Contract",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{st.session_state.contract_data['client_name']} - {st.session_state.contract_data['client_company_name']} - Contract.pdf",
                                           "PDF", "Contract")


            with col2:

                if st.button("✅ Confirm and Upload Contract DOCX", key="upload_docx"):

                    save_generated_file_to_firebase_2(
                        docx_output,
                        "Contract",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{st.session_state.contract_data['client_name']} - {st.session_state.contract_data['client_company_name']} - Contract.docx",
                                           "DOCX", "Contract")
    #
    #     # Clean up temp files
    #     try:
    #         import os
    #         os.unlink(template_path)
    #         os.unlink(pdf_output)
    #         os.unlink(docx_output)
    #     except:
    #         pass


def handle_nda():
    st.title("📄 NDA Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "NDA"
    metadata = regenerate_data.get('metadata', {})

    default_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    default_name = metadata.get("client_name", "")
    default_client_company_name = metadata.get("client_company_name", "")
    default_client_address = metadata.get("client_address", "")


    # Initialize session state for multi-page form
    if 'nda_form_step' not in st.session_state:
        st.session_state.nda_form_step = 1
        st.session_state.nda_data = {}

    if st.session_state.nda_form_step == 1:
        # Step 1: Collect information
        with st.form("nda_form"):
            date = st.date_input("Agreement Date", value=default_date)
            client_name = st.text_input("Client Name", value=default_name)
            client_company_name = st.text_input("Client Company Name", value=default_client_company_name)
            client_company_address = st.text_area("Client Company Address", value=default_client_address)

            if st.form_submit_button("Generate NDA"):
                st.session_state.nda_data = {
                    "date": f"{date.day}/{date.month}/{date.year}",
                    "client_company_name": client_company_name,
                    "client_name": client_name,
                    "client_company_address": client_company_address,
                }
                st.session_state.nda_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.nda_form_step == 2:
        st.subheader("Select NDA Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'nda_form_step', 1))

        # Create temp directory
        import os
        temp_dir = os.path.join(tempfile.gettempdir(), "as_nda")
        os.makedirs(temp_dir, exist_ok=True)
        temp_dir = os.path.join(tempfile.gettempdir(), "as_nda")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Project NDA"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose a nda style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_nda_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)

            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate NDA Documents"):
            st.session_state.nda_form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.nda_form_step == 3:
        # Step 2: Preview and download
        # st.success("NDA generated successfully!")
        with st.spinner("Generating agreement..."):
            st.button("← Back to Template Select", on_click=lambda: setattr(st.session_state, 'nda_form_step', 2))

            the_name = st.session_state.nda_data['client_name']
            space_ = " "
            if len(the_name) >= 9:
                lenght_dif = len(the_name) - 9
                new_text = f"{space_ * lenght_dif}      {the_name}"
            elif len(the_name) < 9:
                lenght_dif = 9 - len(the_name)
                new_text = f"{space_ * lenght_dif}      {the_name}"
            else:
                new_text = the_name
            # Generate documents
            replacements_docx = {
                "date": st.session_state.nda_data["date"],
                # "client_name": f" {st.session_state.nda_data['client_name']}",
                "client_name": new_text,
                "client_company_name": st.session_state.nda_data["client_company_name"],
                "client_company_address": st.session_state.nda_data["client_company_address"]
            }


            # Get template from Firestore
            doc_type = "Project NDA"  # Changed to match your collection name
            try:
                # template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
                # templates = template_ref.collection("templates").order_by("order_number").limit(1).get()
                #
                # if not templates:
                #     st.error("No templates found in the database for Internship Offer")
                #     return
                #
                # # Get the first template (order_number = 1)
                #
                # template_doc = templates[0]
                # template_data = template_doc.to_dict()
                #
                # # Visibility check
                # if template_data.get('visibility', 'Private') != 'Public':
                #     st.error("This Offer template is not currently available")
                #     return
                #
                # # File type check
                # if template_data.get(
                #         'file_type') != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                #     st.error("Template is not a valid Word document (.docx)")
                #     return
                #
                # # Check if storage_path exists
                # if 'storage_path' not in template_data:
                #     st.error("Template storage path not found in the database")
                #     return
                #
                # # Download the template file from Firebase Storage
                # # bucket = storage.bucket()
                # blob = bucket.blob(template_data['storage_path'])
                #
                # # Create a temporary file for the template
                # with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_template:
                #     blob.download_to_filename(temp_template.name)

                template_path = st.session_state.selected_nda_template_path

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name

                # Use the downloaded template
                # offer_edit(template_path, docx_output, replacements_docx)
                nda_edit(template_path, docx_output, replacements_docx)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview")
            st.write(f"**Agreement Date:** {st.session_state.nda_data['date']}")
            st.write(f"**Client Name:** {st.session_state.nda_data['client_name']}")
            st.write(f"**Company Name:** {st.session_state.nda_data['client_company_name']}")
            st.write(f"**Company Address:** {st.session_state.nda_data['client_company_address']}")

            # PDF preview (requires pdfplumber)
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Documents")
            col1, col2 = st.columns(2)

            file_upload_details = {
                "date": st.session_state.nda_data["date"],
                "client_company_name": st.session_state.nda_data["client_company_name"],
                "client_name": st.session_state.nda_data['client_name'],
                "client_address": st.session_state.nda_data["client_company_address"],

                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:

                if st.button("✅ Confirm and Upload NDA PDF", key="upload_pdf"):
                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "NDA",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{st.session_state.nda_data['client_name']} - {st.session_state.nda_data['client_company_name']} - NDA.pdf",
                                           "PDF", "NDA")

            with col2:

                if st.button("✅ Confirm and Upload NDA DOCX", key="upload_docx"):
                    save_generated_file_to_firebase_2(
                        docx_output,
                        "NDA",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{st.session_state.nda_data['client_name']} - {st.session_state.nda_data['client_company_name']} - NDA.docx",
                                           "DOCX", "Project NDA")

    #
    #     # Clean up temp files
    #     try:
    #         import os
    #         os.unlink(template_path)
    #         os.unlink(pdf_output)
    #         os.unlink(docx_output)
    #     except:
    #         pass


def handle_invoice():
    st.title("📄 Invoice Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Invoice"
    metadata = regenerate_data.get('metadata', {})

    default_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d/%m/%Y')), '%d/%m/%Y').date()
    default_invoice_no = metadata.get("invoice_no", "")
    default_name = metadata.get("client_name", "")
    default_email = metadata.get("client_email", "")
    default_client_company_name = metadata.get("client_company_name", "")
    default_client_address = metadata.get("client_address", "")
    default_project_name = metadata.get("project_name", "")
    default_client_no = metadata.get("client_no", "")


    # Initialize session state for multi-page form
    if 'invoice_form_step' not in st.session_state:
        st.session_state.invoice_form_step = 1
        st.session_state.invoice_data = {}
        st.session_state.amounts_input = {}

    if st.session_state.invoice_form_step == 1:
        # Step 1: Collect information
        with st.form("invoice_form"):
            date = st.date_input("Invoice Date", value=default_date)
            invoice_no = st.text_input("Invoice Number", value=default_name)
            project_name = st.text_input("Project Name", value=default_project_name)
            client_name = st.text_input("Client Name", value=default_name)
            client_email = st.text_input("Email", value=default_email)
            client_no = st.text_input("Client Phone Number", value=default_client_no)
            client_company_name = st.text_input("Client Company Name", value=default_client_company_name)
            client_address = st.text_area("Client Company Address", value=default_client_address)

            st.subheader("Amount Entries")


            # Display Amount 1 to 7 in rows of 3 columns
            # Row 1: Amounts 1–3
            cols = st.columns(3)
            amount_inputs = {}
            for i in range(3):
                amount_inputs[f"amt{i + 1}"] = cols[i].number_input(
                    f"Amount {i + 1}", min_value=0, step=1
                )

            # Row 2: Amounts 4–6
            cols = st.columns(3)
            for i in range(3):
                amount_inputs[f"amt{i + 4}"] = cols[i].number_input(
                    f"Amount {i + 4}", min_value=0, step=1
                )

            # Row 3: Amount 7
            col = st.columns(1)[0]
            amount_inputs["amt7"] = col.number_input("Amount 7", min_value=0, step=1)
            st.session_state.amounts_input = amount_inputs

            if st.form_submit_button("Generate Invoice"):
                # print("Amounts Input:", st.session_state.amounts_input)
                st.session_state.invoice_data = {
                    "date": f"{date.day}-{date.month}-{date.year}",
                    "invoice_no": invoice_no,
                    "client_company_name": client_company_name,
                    "client_email": client_email,
                    "client_name": client_name,
                    "client_no": client_no,
                    "client_address": client_address,
                    "project_name": project_name,
                }
                st.session_state.invoice_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.invoice_form_step == 2:
        st.subheader("Select Invoice Template")

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'invoice_form_step', 1))

        # Create temp directory
        import os
        temp_dir = os.path.join(tempfile.gettempdir(), "as_invoice")
        os.makedirs(temp_dir, exist_ok=True)
        temp_dir = os.path.join(tempfile.gettempdir(), "as_invoice")
        os.makedirs(temp_dir, exist_ok=True)

        doc_type = "Project Invoice"
        template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)
        # templates = template_ref.collection("templates").order_by("upload_timestamp", direction="DESCENDING").get()
        templates = template_ref.collection("templates").order_by("order", direction="ASCENDING").get()

        available_templates = []
        for t in templates:
            t_data = t.to_dict()
            if (
                    t_data.get("visibility") == "Public" and
                    t_data.get(
                        "file_type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and
                    t_data.get("storage_path")
            ):
                blob = bucket.blob(t_data["storage_path"])
                if blob.exists():
                    available_templates.append({"doc": t, "metadata": t_data})
                else:
                    print(f"❌ Skipping missing file: {t_data['storage_path']}")

        if not available_templates:
            st.error("No valid public templates available.")
            st.stop()

        # Build selection options using display_name as primary, falling back to original_name
        certificate_options = {
            tpl["metadata"].get("display_name") or tpl["metadata"].get("original_name", f"Template {i + 1}"): tpl
            for i, tpl in enumerate(available_templates)
        }

        st.markdown("""
            <style>
                div[data-baseweb="select"] > div {
                    width: 100% !important;
                }
                .custom-select-container {
                    max-width: 600px;
                    margin-bottom: 1rem;
                }
                .metadata-container {
                    border: 1px solid #e1e4e8;
                    border-radius: 6px;
                    padding: 16px;
                    margin-top: 16px;
                    background-color: #f6f8fa;
                }
                .metadata-row {
                    display: flex;
                    margin-bottom: 8px;
                }
                .metadata-label {
                    font-weight: 600;
                    min-width: 120px;
                }
            </style>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([5, 1])

        with col1:
            selected_name = st.selectbox(
                "Choose an invoice style:",
                options=list(certificate_options.keys()),
                index=0,
                key="certificate_template_select"
            )

            selected_template = certificate_options[selected_name]
            selected_metadata = selected_template["metadata"]
            selected_storage_path = selected_metadata["storage_path"]

            # Download the selected template
            template_path = os.path.join(temp_dir, "selected_template.docx")
            blob = bucket.blob(selected_storage_path)
            blob.download_to_filename(template_path)

            # Store for later use
            st.session_state.selected_invoice_template_path = template_path

            # Enhanced metadata display
            with st.expander("📄 Template Details", expanded=True):
                tab1, tab2 = st.tabs(["Overview", "Full Metadata"])

                with tab1:
                    st.markdown(f"**Display Name:** `{selected_metadata.get('display_name', 'Not specified')}`")
                    st.markdown(f"**Original Filename:** `{selected_metadata.get('original_name', 'Unknown')}`")
                    st.markdown(f"**Upload Date:** `{selected_metadata.get('upload_date', 'Unknown')}`")
                    st.markdown(f"**File Size:** `{selected_metadata.get('size_kb', 'Unknown')} KB`")
                    st.markdown(f"**Description:** `{selected_metadata.get('description', 'Unknown')} `")

                with tab2:
                    from streamlit.components.v1 import html as st_html

                    pretty_metadata = {
                        k: truncate_value(v) for k, v in selected_metadata.items()
                        if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    }

                    html_output = "<div style='font-family: monospace; font-size: 14px;'>{</br>" + dict_to_colored_html(
                        pretty_metadata) + "}</div>"

                    st_html(html_output, height=400, scrolling=True)

                    # display_metadata = {
                    #     k: v for k, v in selected_metadata.items()
                    #     if k not in ['download_url', 'storage_path', 'upload_timestamp']
                    # }
                    # st.json(display_metadata)

            # Show PDF preview if available
            if selected_metadata.get('has_pdf_preview', False):
                # if st.button("👁️ Show Preview"):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        pdf_blob = bucket.blob(selected_metadata['pdf_storage_path'])
                        pdf_blob.download_to_filename(tmp_file.name)
                        # pdf_view()
                        pdf_view(tmp_file.name)
                except Exception as e:
                    st.error(f"Failed to load preview: {str(e)}")
            else:
                st.write(f"Preview file unavailable.")

        if st.button("Generate Invoice Documents"):
            st.session_state.invoice_form_step = 3
            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    elif st.session_state.invoice_form_step == 3:
        # Step 2: Preview and download
        # st.success("NDA generated successfully!")
        with st.spinner("Generating invoice..."):
            st.button("← Back to Template Select", on_click=lambda: setattr(st.session_state, 'invoice_form_step', 2))


            # Generate documents
            replacements_docx = {
                "invoice_date": st.session_state.invoice_data["date"],
                "client_name": f" {st.session_state.invoice_data['client_name']}",
                # "client_name": new_text,
                "company_name": st.session_state.invoice_data["client_company_name"],
                "client_no": st.session_state.invoice_data["client_no"],
                "client_address": st.session_state.invoice_data["client_address"],
                "project_name": st.session_state.invoice_data["project_name"],
                "client_email": st.session_state.invoice_data["client_email"],
                "invoice_no": st.session_state.invoice_data["invoice_no"],
            }
            replacements_docx = replacements_docx | st.session_state.amounts_input
            # print("full dict", replacements_docx)

            # Get template from Firestore
            doc_type = "Project Invoice"  # Changed to match your collection name
            try:
                # template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
                # templates = template_ref.collection("templates").order_by("order_number").limit(1).get()
                #
                # if not templates:
                #     st.error("No templates found in the database for Internship Offer")
                #     return
                #
                # # Get the first template (order_number = 1)
                #
                # template_doc = templates[0]
                # template_data = template_doc.to_dict()
                #
                # # Visibility check
                # if template_data.get('visibility', 'Private') != 'Public':
                #     st.error("This Offer template is not currently available")
                #     return
                #
                # # File type check
                # if template_data.get(
                #         'file_type') != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                #     st.error("Template is not a valid Word document (.docx)")
                #     return
                #
                # # Check if storage_path exists
                # if 'storage_path' not in template_data:
                #     st.error("Template storage path not found in the database")
                #     return
                #
                # # Download the template file from Firebase Storage
                # # bucket = storage.bucket()
                # blob = bucket.blob(template_data['storage_path'])
                #
                # # Create a temporary file for the template
                # with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_template:
                #     blob.download_to_filename(temp_template.name)

                template_path = st.session_state.selected_invoice_template_path

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name

                # Use the downloaded template
                # offer_edit(template_path, docx_output, replacements_docx)
                nda_edit(template_path, docx_output, replacements_docx)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Preview")
            st.write(f"**Invoice Date:** {st.session_state.invoice_data['date']}")
            st.write(f"**Invoice No:** {st.session_state.invoice_data['invoice_no']}")
            st.write(f"**Client Name:** {st.session_state.invoice_data['client_name']}")
            st.write(f"**Company Name:** {st.session_state.invoice_data['client_company_name']}")
            st.write(f"**Phone Number:** {st.session_state.invoice_data['client_no']}")
            st.write(f"**Email:** {st.session_state.invoice_data['client_email']}")
            st.write(f"**Company Address:** {st.session_state.invoice_data['client_address']}")
            st.write(f"**Project Name:** {st.session_state.invoice_data['project_name']}")

            # PDF preview (requires pdfplumber)
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Documents")
            col1, col2 = st.columns(2)

            file_upload_details = {
                "date": st.session_state.invoice_data["date"],
                "client_company_name": st.session_state.invoice_data["client_company_name"],
                "client_name": st.session_state.invoice_data['client_name'],
                "client_address": st.session_state.invoice_data["client_address"],
                "client_email": st.session_state.invoice_data["client_email"],
                "client_no": st.session_state.invoice_data["client_no"],
                "project_name": st.session_state.invoice_data["project_name"],
                "invoice_no": st.session_state.invoice_data["invoice_no"],

                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:

                if st.button("✅ Confirm and Upload Invoice PDF", key="upload_pdf"):
                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "Project Invoice",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{st.session_state.invoice_data['client_name']} - {st.session_state.invoice_data['client_company_name']} - Invoice.pdf",
                                           "PDF", "Project Invoice")

            with col2:

                if st.button("✅ Confirm and Upload Invoice DOCX", key="upload_docx"):
                    save_generated_file_to_firebase_2(
                        docx_output,
                        "Project Invoice",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{st.session_state.invoice_data['client_name']} - {st.session_state.invoice_data['client_company_name']} - Invoice.docx",
                                           "DOCX", "Project Invoice")

    #
    #     # Clean up temp files
    #     try:
    #         import os
    #         os.unlink(template_path)
    #         os.unlink(pdf_output)
    #         os.unlink(docx_output)
    #     except:
    #         pass


def handle_invoice_old():
    st.title("📄 Invoice Generator")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Internship"
    metadata = regenerate_data.get('metadata', {})

    # Initialize session state for multi-page form
    if 'invoice_form_step' not in st.session_state:
        st.session_state.invoice_form_step = 1
        st.session_state.invoice_data = {}

        st.session_state.payment_items = []
        st.session_state.show_description = False

    # Currency options
    currency_options = {
        "USD": {"label": "USD – US Dollar", "sign": "$", "name": "US Dollar"},
        "EUR": {"label": "EUR – Euro", "sign": "€", "name": "Euro"},
        "GBP": {"label": "GBP – British Pound", "sign": "£", "name": "British Pound"},
        "INR": {"label": "INR – Indian Rupee", "sign": "₹", "name": "Indian Rupee"},
        "NGN": {"label": "NGN – Nigerian Naira", "sign": "₦", "name": "Nigerian Naira"},
        "CAD": {"label": "CAD – Canadian Dollar", "sign": "CA$", "name": "Canadian Dollar"},
        "AUD": {"label": "AUD – Australian Dollar", "sign": "A$", "name": "Australian Dollar"},
        "JPY": {"label": "JPY – Japanese Yen", "sign": "¥", "name": "Japanese Yen"},
    }
    if "invoice_currency" not in st.session_state:
        st.session_state.invoice_currency = {}

    # Step 1: Client and Company Information
    if st.session_state.invoice_form_step == 1:
        with st.form("invoice_form_step1"):
            st.subheader("Client & Company Information")

            col1, col2 = st.columns(2)
            with col1:
                invoice_no = st.text_input("Invoice Number", placeholder="12234")
                date = st.date_input("Invoice Date", value=datetime.now().date())
                client_name = st.text_input("Client Name", placeholder="Ojo Alaba")
                client_company_name = st.text_input("Client Company Name", placeholder="Yoruba Ltd")
                client_phone = st.text_input("Client Phone", placeholder="+1 234 56000")
                client_email = st.text_input("Client Email", placeholder="unfresh@email.com")

            with col2:
                company_number = st.text_input("Your Company Phone", placeholder="+1 234 56000")
                company_gst = st.text_input("Your Company GST", placeholder="9000")
                client_address = st.text_area("Client Address",
                                              placeholder="Lead Developer Street, Anthony, Riyah Turkey")
                project_name = st.text_input("Project Name", placeholder="Tolu Scrapper")

            currency_shortcode = st.selectbox(
                "Currency Code",
                options=list(currency_options.keys()),
                format_func=lambda code: currency_options[code]["label"],  # Show full name
                index=0
            )

            currency_sign = currency_options[currency_shortcode]["sign"]
            currency_name = currency_options[currency_shortcode]["name"]
            currency_data = {
                "currency_code": currency_shortcode,
                "currency_sign": currency_sign,
                "currency_name": currency_name
            }
            print("here")
            print(f"currency data {currency_data}")
            print(f"currency data {currency_data}")
            print(f"currency data {currency_data}")
            st.session_state.invoice_currency = currency_data

            if st.form_submit_button("Continue to Items"):

                print(f"Invoice currency session state: {st.session_state.invoice_currency}")
                if not client_name.strip():
                    st.error("Please enter client name")
                    st.stop()

                st.session_state.invoice_data = {
                    "date": date.strftime("%B %d, %Y"),
                    "client_name": client_name.strip(),
                    "client_company_name": client_company_name.strip(),
                    "client_phone": client_phone.strip(),
                    "company_number": company_number.strip(),
                    "company_gst": company_gst.strip(),
                    "client_address": client_address.strip(),
                    "client_email": client_email.strip(),
                    "project_name": project_name.strip(),
                    "invoice_no": invoice_no,
                    "payment_currency": f""
                                        f"{st.session_state.invoice_currency['currency_code']} "
                                        f"{st.session_state.invoice_currency['currency_sign']}"

                }
                st.session_state.invoice_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    # Step 2
    elif st.session_state.invoice_form_step == 2:

        st.button("← Back", on_click=lambda: setattr(st.session_state, 'invoice_form_step', 1))

        if 'show_schedule' not in st.session_state:
            st.session_state.show_schedule = False

        # Display payment items
        if st.session_state.payment_items:
            st.markdown("### 💰 Current Payment Items")
            for idx, item in enumerate(st.session_state.payment_items):
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([1, 3, 2, 2, 1])
                    with col1:
                        st.markdown(f"**{item['s_no']}.**")

                    with col2:
                        st.markdown(f"**{item['description']}.**")

                    with col3:
                        st.markdown(f"**{item['hns_code']}.**")

                    with col4:
                        st.markdown(f"**{item['price']}.**")

                    with col5:
                        if st.button("❌", key=f"remove_{idx}"):
                            st.session_state.payment_items.pop(idx)
                            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

        # Add new item form
        with st.form("invoice_form_step2"):
            st.subheader("➕ Add New Payment Description")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                s_no = st.number_input("S.No", min_value=1, value=len(st.session_state.payment_items) + 1)
            with col2:
                description = st.text_input("Description", placeholder="Project Setup Fee")
            with col3:
                price = st.text_input("Amount", placeholder="10000")

            hns_code = st.text_input("HSN Code", placeholder="2345666")

            col1, col2 = st.columns(2)
            with col1:
                add_btn = st.form_submit_button("➕ Add")
            with col2:
                schedule_toggle = st.form_submit_button(
                    "📅 Add Payment Schedule" if not st.session_state.show_schedule else "❌ Cancel Payment Schedule")

            if add_btn:
                if not description.strip():
                    st.error("Please enter item description.")
                    st.stop()
                if not price.strip():
                    st.error("Please enter item price.")
                    st.stop()
                new_item = {
                    "s_no": str(s_no),
                    "description": description.strip(),
                    "hns_code": hns_code.strip(),
                    "price": f"{st.session_state.invoice_currency['currency_sign']}{price.strip()}",
                    "additional_desc": ""
                }
                st.session_state.payment_items.append(new_item)
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

            if schedule_toggle:
                st.session_state.show_schedule = not st.session_state.show_schedule
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

        # Payment Schedule Section
        if st.session_state.show_schedule:
            st.subheader("📅 Payment Schedule")

            if 'payment_schedule' not in st.session_state:
                st.session_state.payment_schedule = []

            if st.session_state.payment_schedule:
                st.markdown("#### Current Schedule")
                for idx, item in enumerate(st.session_state.payment_schedule):
                    with st.container():
                        col1, col2, col3, col4 = st.columns([1, 3, 2, 1])
                        with col1:
                            st.markdown(f"**{item['s_no']}.**")
                        with col2:
                            st.markdown(f"**{item['schedule']}**")
                        with col3:
                            st.markdown(f"**{item['price']}**")
                        with col4:
                            if st.button("❌", key=f"remove_schedule_{idx}"):
                                st.session_state.payment_schedule.pop(idx)
                                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

            with st.form("payment_schedule_form"):
                col1, col2, col3 = st.columns([1, 3, 1])
                with col1:
                    schedule_s_no = st.number_input("S.No.", min_value=1,
                                                    value=len(st.session_state.payment_schedule) + 1, key="schedule_no")
                with col2:
                    schedule_desc = st.text_input("Schedule Description", placeholder="Upon signing",
                                                  key="schedule_desc")
                with col3:
                    schedule_price = st.text_input("Amount", placeholder="10000", key="schedule_price")

                col1, col2 = st.columns(2)
                with col1:
                    add_schedule_btn = st.form_submit_button("➕ Add")
                with col2:
                    done_btn = st.form_submit_button("✅ Done with Schedule")

                if add_schedule_btn:
                    if not schedule_desc.strip():
                        st.error("Please enter schedule description.")
                        st.stop()
                    if not schedule_price.strip():
                        st.error("Please enter schedule amount.")
                        st.stop()
                    new_schedule = {
                        "s_no": str(schedule_s_no),
                        "schedule": schedule_desc.strip(),
                        "price": f"{st.session_state.invoice_currency['currency_sign']}{format_currency_amount(schedule_price.strip())}"
                    }
                    st.session_state.payment_schedule.append(new_schedule)
                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                if done_btn:
                    st.session_state.show_schedule = False
                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

        # Proceed to Preview
        if st.session_state.payment_items:
            if st.button("➡ Continue to Preview"):
                st.session_state.invoice_data["payment_description"] = st.session_state.payment_items
                if hasattr(st.session_state, 'payment_schedule') and st.session_state.payment_schedule:
                    st.session_state.invoice_data["payment_schedule"] = st.session_state.payment_schedule
                st.session_state.invoice_form_step = 3
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        else:
            st.warning("⚠️ Add at least one Payment Description before continuing.")

    # Step 3: Preview and Download
    elif st.session_state.invoice_form_step == 3:
        st.button("← Back to Items", on_click=lambda: setattr(st.session_state, 'invoice_form_step', 2))

        with st.spinner("Generating invoice..."):
            # Prepare context for template
            import re
            total = sum(
                float(re.sub(r"[^\d.]", "", item["price"]))
                for item in st.session_state.payment_items
                if re.search(r"\d", item["price"])
            )
            context = {
                **st.session_state.invoice_data,
                "payment_description": st.session_state.payment_items,
                "sum": f"{st.session_state.invoice_currency['currency_sign']}{'{:,}'.format(total)}"
            }

            # Add amount in words
            from num2words import num2words
            def extract_numeric(price_str):
                match = re.search(r"[\d,]+(?:\.\d+)?", price_str)
                if not match:
                    return 0.0
                number_str = match.group().replace(",", "")
                return float(number_str)

            total_amount = sum(extract_numeric(item['price']) for item in st.session_state.payment_items)

            # total_amount = sum(float(item['price'].replace(',', '')) for item in st.session_state.payment_items)
            context[
                "sum_to_word"] = f"{num2words(abs(total_amount), to='currency').title()} {st.session_state.invoice_currency['currency_name']} only."

            # Get template from Firestore
            doc_type = "Invoice"
            try:
                template_ref = firestore_db.collection("hvt_generator").document(doc_type)
                templates = template_ref.collection("templates").order_by("order_number").limit(1).get()

                if not templates:
                    st.error("No invoice templates found in the database")
                    return

                template_doc = templates[0]
                template_data = template_doc.to_dict()

                if template_data.get('visibility', 'Private') != 'Public':
                    st.error("This invoice template is not currently available")
                    return

                if template_data.get(
                        'file_type') != 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                    st.error("Template is not a valid Word document (.docx)")
                    return

                if 'storage_path' not in template_data:
                    st.error("Template storage path not found in the database")
                    return

                # Download the template
                blob = bucket.blob(template_data['storage_path'])

                with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_template:
                    blob.download_to_filename(temp_template.name)
                    template_path = temp_template.name

            except Exception as e:
                st.error(f"Error fetching template: {str(e)}")
                return

            # Generate temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf, \
                    tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_docx:

                pdf_output = temp_pdf.name
                docx_output = temp_docx.name

                # Use the downloaded template
                invoice_edit(template_path, docx_output, context)
                main_converter(docx_output, pdf_output)

            # Preview section
            st.subheader("Invoice Preview")

            # Client info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Client Name:** {context['client_name']}")
                st.write(f"**Company:** {context['client_company_name']}")
                st.write(f"**Address:** {context['client_address']}")
                st.write(f"**Phone:** {context['client_phone']}")
                st.write(f"**Email:** {context['client_email']}")

            with col2:
                st.write(f"**Invoice #:** {context['invoice_no']}")
                st.write(f"**Date:** {context['date']}")
                st.write(f"**Project:** {context['project_name']}")
                st.write(f"**GST:** {context['company_gst']}")
                st.write(f"**Currency:** {context['payment_currency']} ")

            with col3:
                with st.expander("View Invoice Data (JSON)", expanded=True):
                    st.json(st.session_state.invoice_data)

            # Total
            # st.write(f"**Total Amount:** {context['payment_currency']['sign']}{context['sum']:,.2f}")
            st.write(f"**Amount in Words:** {context['sum_to_word']}")

            # PDF preview
            pdf_view(pdf_output)

            # Download buttons
            st.subheader("Download Invoice")
            col1, col2 = st.columns(2)
            file_prefix = f"Invoice {context['client_name']} {context['invoice_no']}"

            file_upload_details = {
                "invoice_no": context['invoice_no'],
                "client_name": context['client_name'],
                "company_name": context['client_company_name'],
                "address": context['client_address'],
                "phone": context['client_phone'],
                "email": context['client_email'],
                "invoice_date": context['date'],
                "project_name": context['project_name'],
                "gst": context['company_gst'],
                "currency": context['payment_currency'],
                "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "upload_timestamp": firestore.SERVER_TIMESTAMP,
            }

            with col1:
                if st.button("✅ Confirm and Upload Contract PDF", key="upload_pdf"):
                    storage_path, public_url = save_generated_file_to_firebase(pdf_output, doc_type="Invoice",
                                                                               bucket=bucket)
                    save_generated_file_to_firebase_2(
                        pdf_output,
                        "Invoice",
                        bucket,
                        "PDF",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(pdf_output,
                                           f"{file_prefix}.pdf",
                                           "PDF", "Invoice")

            with col2:
                # generate_download_link(
                #     docx_output,
                #     f"{file_prefix}.docx",
                #     "DOCX", "Invoice"
                # )
                if st.button("✅ Confirm and Upload Contract DOCX", key="upload_docx"):
                    # storage_path, public_url = save_generated_file_to_firebase(docx_output, doc_type="Invoice",
                    #                                                            bucket=bucket)
                    save_generated_file_to_firebase_2(
                        docx_output,
                        "Invoice",
                        bucket,
                        "DOCX",
                        file_upload_details
                    )

                    st.success("Now you can download the file:")
                    # Step 2: Show download link only after upload
                    generate_download_link(docx_output,
                                           f"{file_prefix}.docx",
                                           "DOCX", "Invoice")

        # Clean up temp files
        try:
            os.unlink(template_path)
            os.unlink(pdf_output)
            os.unlink(docx_output)
        except:
            pass


def fetch_proposal_templates_to_temp_dir(firestore_db, bucket):
    base_temp_dir = tempfile.mkdtemp(prefix="proposal_templates_")

    # Mapping section labels to their Firestore subcollection names
    section_map = {
        "cover_page": "Cover Page",
        "table_of_contents": "Table of Contents",
        "business_requirement": "Business Requirement",
        "page_3_6": "Page 3 to 6",
        "testimonials": "Testimonials"
    }

    folder_paths = {}

    for section_key, section_label in section_map.items():
        target_dir = os.path.join(base_temp_dir, section_key)
        os.makedirs(target_dir, exist_ok=True)
        folder_paths[section_key] = target_dir

        try:
            templates_ref = firestore_db.collection("HVT_DOC_Gen").document("Proposal").collection(section_key)
            templates = templates_ref.stream()

            for doc in templates:
                data = doc.to_dict()

                if not data.get("storage_path"):
                    continue

                filename = data.get("original_name", doc.id)
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"

                target_path = os.path.join(target_dir, filename)

                try:
                    blob = bucket.blob(data["storage_path"])
                    blob.download_to_filename(target_path)
                except Exception as e:
                    print(f"❌ Failed to download {data['storage_path']}: {e}")

        except Exception as e:
            print(f"⚠️ Failed to fetch templates from section {section_key}: {e}")

    return folder_paths


def fetch_path_from_temp_dir(sub_folder, selected_template, folder_paths):
    try:
        # Ensure required input
        if not selected_template or "original_name" not in selected_template:
            st.error("Invalid template data provided.")
            return None

        the_temp_dir = folder_paths.get(sub_folder)
        if not the_temp_dir:
            st.error(f"❌ Templates folder for '{sub_folder}' not found in folder_paths.")
            return None

        # Construct expected file name
        expected_filename = selected_template["original_name"]
        if not expected_filename.lower().endswith(".pdf"):
            expected_filename += ".pdf"

        template_path = os.path.join(the_temp_dir, expected_filename)

        # Check if file exists
        if not os.path.isfile(template_path):
            st.error(f"❌ Template file not found: `{template_path}`")
            return None

        return template_path

    except Exception as e:
        st.error(f"❌ An error occurred while fetching the template path: {str(e)}")
        return None


def get_proposal_template_details(firestore_db):
    doc_type = "Proposal"
    proposal_doc_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)

    # Subcollections map
    section_keys = [
        "cover_page",
        "table_of_contents",
        "business_requirement",
        "page_3_6",
        "testimonials"
    ]

    all_templates = []

    for section_key in section_keys:
        templates = proposal_doc_ref.collection(section_key).stream()

        for doc in templates:
            data = doc.to_dict()
            if not data:
                continue

            file_details = {
                "name": data.get("name"),
                "original_name": data.get("original_name"),
                "doc_type": data.get("doc_type", "Proposal"),
                "file_type": data.get("file_type"),
                "size_kb": data.get("size_kb"),
                "size_bytes": data.get("size_bytes"),
                "upload_date": data.get("upload_date"),
                "upload_timestamp": data.get("upload_timestamp"),
                "download_url": data.get("download_url"),
                "storage_path": data.get("storage_path"),
                "visibility": data.get("visibility"),
                "description": data.get("description"),
                "order_number": data.get("order_number"),
                "is_active": data.get("is_active", True),
                "template_part": data.get("template_part"),
                "proposal_section_type": data.get("proposal_section_type"),
                "pdf_name": data.get("pdf_name"),
                "num_pages": data.get("num_pages"),
                "section_key": section_key,
                "document_id": doc.id  # Include Firestore document ID for edit/delete
            }

            all_templates.append(file_details)

    return all_templates


def get_specific_templates(all_templates, number_of_pages):
    # Filter for table_of_contents and testimonials with exactly 8 pages
    filtered_templates = [
        tpl for tpl in all_templates
        if tpl["section_key"] in ["table_of_contents", "testimonials"]
           and tpl.get("num_pages") == number_of_pages
    ]

    # Group by section and get first match from each
    result = {}
    for tpl in filtered_templates:
        if tpl["section_key"] not in result:  # Only take first match per section
            result[tpl["section_key"]] = tpl

    return result


def align_text_fixed_width(text, total_char_width=12, alignment='center'):
    text_length = len(text)
    if text_length >= total_char_width:
        return text  # no padding needed or text is too long

    space_count = total_char_width - text_length

    if alignment == 'left':
        return text + ' ' * space_count
    elif alignment == 'right':
        return ' ' * space_count + text
    elif alignment == 'center':
        left_spaces = space_count // 2
        right_spaces = space_count - left_spaces
        return ' ' * left_spaces + text + ' ' * right_spaces
    else:
        raise ValueError("alignment must be 'left', 'center', or 'right'")
    return text


# def handle_proposal():
#     st.title("📄 Proposal Form")
#     regenerate_data = st.session_state.get('regenerate_data', {})
#     is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Proposal"
#     metadata = regenerate_data.get('metadata', {})
#
#     default_date = datetime.strptime(
#         metadata.get("date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#     default_name = metadata.get("client_name", "")
#     default_company_name = metadata.get("company_name", "")
#     default_email = metadata.get("email", "")
#     default_phone = metadata.get("phone", "")
#     default_country = metadata.get("country", "")
#     default_client_address = metadata.get("client_address", "")
#     default_proposal_date = datetime.strptime(
#         metadata.get("proposal_date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#
#     st.session_state.setdefault("proposal_data", {})
#     st.session_state.setdefault("proposal_form_step", 1)
#     space_ = " "
#
#     # if 'proposal_data' not in st.session_state:
#     #     st.session_state.proposal_data = {}
#     #
#     # # Initialize session state for multi-page form
#     # if 'proposal_form_step' not in st.session_state:
#     #     st.session_state.proposal_form_step = 1
#     # st.session_state.proposal_data = {}
#
#     all_templates = get_proposal_template_details(firestore_db)
#     folder_paths = fetch_proposal_templates_to_temp_dir(firestore_db, bucket)
#
#     # Step 1: Basic Information
#     if st.session_state.proposal_form_step == 1:
#         with st.form("proposal_form_step1"):
#             st.subheader("Client Information")
#             name = st.text_input("Client Name", value=default_name)
#             company = st.text_input("Company Name", value=default_company_name)
#             email = st.text_input("Email", value=default_email)
#             phone = st.text_input("Phone", value=default_phone, placeholder="+1 234 5678")
#             countries = sorted([country.name for country in pycountry.countries])
#             country = st.selectbox("Select Country", countries,)
#             proposal_date = st.date_input("Proposal Date", value=default_proposal_date)
#
#             if st.form_submit_button("Next: Select Cover Page"):
#                 st.session_state.proposal_data = {
#                     "client_name": name,
#                     "company_name": company,
#                     "email": email,
#                     "phone": phone,
#                     "country": country,
#                     "proposal_date": proposal_date.strftime("%B %d, %Y")
#                 }
#                 if not st.session_state.proposal_data:
#                     print("Proposal data not available")
#                     # st.write("Proposal data not available")
#                     st.error("Proposal data not available")
#                 else:
#
#                     st.session_state.proposal_form_step = 2
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     elif st.session_state.proposal_form_step == 2:
#         st.subheader("Select Cover page")
#         print(f"st.session_state.proposal_data: {st.session_state.proposal_data}")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 1))
#
#         cover_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "cover_page"]
#
#         # Build options with pdf_name as label
#         cover_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in cover_templates
#         }
#
#         if not cover_options:
#             st.error("No valid cover templates available. Cannot proceed.")
#             st.stop()
#
#
#
#         col1, col2 = st.columns([1, 2])
#
#         with col1:
#             with st.container():
#                 st.markdown('<div class="custom-select-container">', unsafe_allow_html=True)
#
#                 selected_cover_name = st.selectbox(
#                     "Choose a cover page style:",
#                     options=list(cover_options.keys()),
#                     index=0,
#                     key="cover_template_select"
#                 )
#
#                 st.markdown('</div>', unsafe_allow_html=True)
#
#             # selected_cover_name = st.selectbox(
#             #     "Choose a cover page style:",
#             #     options=list(cover_options.keys()),
#             #     index=0,
#             #     key="cover_template_select"
#             # )
#
#             selected_template = cover_options[selected_cover_name]
#             template_path = fetch_path_from_temp_dir("cover_page", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Cover page template file not found.")
#                 return
#
#             # Ensure output path is valid in Streamlit Cloud
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
#                 temp_img_path = temp_img.name
#             # temp_dir = tempfile.gettempdir()
#             # output_pdf = os.path.join(temp_dir, "modified_cover.pdf")
#
#             # pdf_editor = EditTextFile(template_path)
#             #
#             # modifications = {
#             #     "Name :": f": {st.session_state.proposal_data['client_name']}",
#             #     "Email :": f": {st.session_state.proposal_data['email']}",
#             #     "Phone :": f": {st.session_state.proposal_data['phone']}",
#             #     "Country: ": f": {st.session_state.proposal_data['country']}",
#             #     "Date": f"{st.session_state.proposal_data['proposal_date']}"
#             # }
#
#             replace_pdf_placeholders(
#                 input_path=template_path,
#                 output_path=temp_img_path,
#                 replacements={
#                     "{ client_name }": f"{st.session_state.proposal_data['client_name']}",
#                     # "{ client_name }": (
#                     #     align_text_fixed_width(st.session_state.proposal_data['client_name'], 12, 'center'), 0, 7),
#                     "{ client_email }": f"{st.session_state.proposal_data['email']}",
#                     "{ client_phone }": f"{st.session_state.proposal_data['phone']}",
#                     "{ client_country }": f"{st.session_state.proposal_data['country']}",
#                     "{ date }": f" {st.session_state.proposal_data['proposal_date']}"
#                 },
#                 y_offset=20
#             )
#
#             # print(f"modifications: {modifications}")
#             #
#             # pdf_editor.modify_pdf_fields(temp_img_path, modifications, 8)
#
#             # Preview
#             if os.path.exists(temp_img_path):
#                 pdf_view(temp_img_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step2"):
#             if st.form_submit_button("Next: Select Business Requirement Page"):
#                 st.session_state.proposal_data["cover_template"] = temp_img_path
#                 st.session_state.proposal_form_step = 3
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     elif st.session_state.proposal_form_step == 3:
#         st.subheader("Select Business Requirement page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 2))
#
#         br_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "business_requirement"]
#
#         # Build options with pdf_name as label
#         br_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in br_templates
#         }
#
#         if not br_options:
#             st.error("No valid BR templates available. Cannot proceed.")
#             st.stop()
#
#         if 'selected_br' not in st.session_state:
#             st.session_state.selected_br = None
#
#         br_options_list = list(br_options.keys())
#
#         if (
#                 st.session_state.selected_br is not None
#                 and st.session_state.selected_br in br_options_list
#         ):
#             initial_br = br_options_list.index(st.session_state.selected_br)
#         else:
#             initial_br = 0
#
#         col1, col2 = st.columns([1, 2])
#
#         with col1:
#
#             selected_br_name = st.selectbox(
#                 "Choose a business requirements page style:",
#                 options=list(br_options.keys()),
#                 index=0,
#                 key="br_template_select"
#             )
#
#             selected_br_template = br_options[selected_br_name]
#             # st.session_state.selected_br = selected_br_name
#         br_temp_dir = folder_paths.get("business_requirement")
#         if br_temp_dir:
#             # Find the matching file in the temp directory
#             expected_filename = selected_br_template["original_name"]
#             if not expected_filename.lower().endswith(".pdf"):
#                 expected_filename += ".pdf"
#
#             template_path = os.path.join(br_temp_dir, expected_filename)
#
#             if os.path.exists(template_path):
#                 the_name = st.session_state.proposal_data['client_name']
#                 if len(the_name) > 14:
#                     # lenght_dif = len(the_name) - 5
#                     # new_text = f"{space_ * lenght_dif}      {the_name}"
#                     new_text = the_name
#                 elif len(the_name) < 14:
#                     if len(the_name) < 8:
#                         lenght_dif = 11 - len(the_name)
#                         new_text = f"{space_ * lenght_dif}{the_name}"
#                     else:
#                         lenght_dif = 14 - len(the_name)
#                         new_text = f"{space_ * lenght_dif}{the_name}"
#                 else:
#                     new_text = the_name
#                 modifications = {
#                     "{ client_name }": (f"{new_text}", 0, 7),
#                     # "{ client_name }": (f"      {st.session_state.proposal_data['client_name']}", 0, 7),
#                     # "{ client_name }": (
#                     #     align_text_fixed_width(st.session_state.proposal_data['client_name'], 12, 'center'), 0, 7),
#                     "{ date }": (f"{st.session_state.proposal_data['proposal_date']}", -30, 0)
#                 }
#                 with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_br:
#                     temp_br_path = temp_br.name
#                 # temp_dir = tempfile.gettempdir()
#                 # output_pdf = os.path.join(temp_dir, "modified_testimonials.pdf")
#                 editor = EditTextFile(template_path)
#                 editor.modify_pdf_fields(temp_br_path, modifications)
#
#                 st.session_state.selected_br = temp_br_path
#                 st.session_state.proposal_data["br_template"] = st.session_state.selected_br
#                 try:
#                     br_num_pages = selected_br_template.get("num_pages")
#                     st.write(f"This BR template has {br_num_pages} page(s)")
#                 except Exception as e:
#                     st.warning(f"⚠️ Could not read number of pages of Template: {str(e)}")
#                     st.stop()
#
#                 specific_templates = get_specific_templates(all_templates, br_num_pages)
#
#                 pdf_view(temp_br_path)
#             else:
#                 st.error(f"Template file not found: {template_path}")
#         else:
#             st.error("Business requirement templates directory not found")
#
#         with st.form("proposal_form_step4"):
#             if st.form_submit_button("Next: Preview Proposal"):
#
#                 section_dir = folder_paths.get("page_3_6")
#                 p3_p6_templates = [
#                     os.path.join(section_dir, f)
#                     for f in os.listdir(section_dir)
#                     if f.lower().endswith(".pdf")
#                 ]
#                 st.session_state.proposal_data["p3_p6_template"] = p3_p6_templates
#                 st.session_state.proposal_data["br_template"] = st.session_state.selected_br
#                 table_of_contents = specific_templates.get("table_of_contents")
#                 testimonial = specific_templates.get("testimonials")
#
#                 selected_table_of_content = fetch_path_from_temp_dir("table_of_contents", table_of_contents,
#                                                                      folder_paths)
#                 selected_testimonial = fetch_path_from_temp_dir("testimonials", testimonial, folder_paths)
#                 st.session_state.proposal_data["table_of_contents"] = selected_table_of_content
#                 st.session_state.proposal_data["testimonials"] = selected_testimonial
#
#                 merger_files = []
#
#                 # Cover page
#                 cover = st.session_state.proposal_data.get("cover_template")
#                 if cover and os.path.exists(cover):
#                     merger_files.append(cover)
#                 else:
#                     st.info("Cover Template not available.")
#
#                 # Table of Contents
#                 toc = st.session_state.proposal_data.get("table_of_contents")
#                 if toc and os.path.exists(toc):
#                     merger_files.append(toc)
#                 else:
#                     st.info("Table of Contents Template for the selected BR page count is unavailable.")
#
#                 # Page 3 to 6
#                 p3_p6_list = st.session_state.proposal_data.get("p3_p6_template", [])
#                 if p3_p6_list:
#                     available_p3_p6 = [p for p in p3_p6_list if os.path.exists(p)]
#                     if available_p3_p6:
#                         merger_files.extend(available_p3_p6)
#                     else:
#                         st.info("Page 3 to 6 Templates are missing.")
#                 else:
#                     st.info("No Page 3 to 6 Templates found.")
#
#                 # Business Requirement
#                 br = st.session_state.proposal_data.get("br_template")
#                 if br and os.path.exists(br):
#                     merger_files.append(br)
#                 else:
#                     st.info("Business Requirement Template unavailable.")
#
#                 # Testimonials
#                 testimonials = st.session_state.proposal_data.get("testimonials")
#                 if testimonials and os.path.exists(testimonials):
#
#                     merger_files.append(testimonials)
#                 else:
#                     st.info("Testimonial Template for the selected BR page count is unavailable.")
#
#                 for file_path in merger_files:
#                     print(file_path)
#                     if file_path is None:
#                         continue
#                     if not os.path.exists(file_path):
#                         st.error(f"File not found: {file_path}")
#                         return
#
#                 merger = Merger(merger_files)
#                 merger.merge_pdf_files("merged_output.pdf")
#
#                 st.session_state.proposal_form_step = 4
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#     # Page 4: Final Preview and Download
#     elif st.session_state.proposal_form_step == 4:
#         st.subheader("📄 Final Proposal Preview")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 3))
#
#         st.markdown("""
#             <style>
#                 .download-col > div {
#                     text-align: center;
#                 }
#             </style>
#         """, unsafe_allow_html=True)
#
#         # Proposal metadata summary
#         st.markdown("#### 🧾 Proposal Details")
#         col1, col2 = st.columns(2)
#
#         with col1:
#             st.write(f"**Client Name:** {st.session_state.proposal_data['client_name']}")
#             st.write(f"**Company:** {st.session_state.proposal_data['company_name']}")
#             st.write(f"**Email:** {st.session_state.proposal_data['email']}")
#             st.write(f"**Phone:** {st.session_state.proposal_data['phone']}")
#
#         with col2:
#             st.write(f"**Country:** {st.session_state.proposal_data['country']}")
#             st.write(f"**Proposal Date:** {st.session_state.proposal_data['proposal_date']}")
#
#         # st.divider()
#         st.markdown("---")
#
#         # PDF Preview
#         if os.path.exists("merged_output.pdf"):
#             st.markdown("#### 📑 Preview of Merged Proposal")
#             pdf_view("merged_output.pdf")
#         else:
#             st.error("Merged proposal file not found.")
#             st.stop()
#
#         # st.divider()
#         st.markdown("---")
#         st.write(f"**Client Name:** {st.session_state.proposal_data['client_name']}")
#         st.write(f"**Company:** {st.session_state.proposal_data['company_name']}")
#         st.write(f"**Email:** {st.session_state.proposal_data['email']}")
#         st.write(f"**Phone:** {st.session_state.proposal_data['phone']}")
#         st.write(f"**Country:** {st.session_state.proposal_data['country']}")
#         st.write(f"**Proposal Date:** {st.session_state.proposal_data['proposal_date']}")
#         file_upload_details = {
#             "client_name": st.session_state.proposal_data['client_name'],
#             "company_name": st.session_state.proposal_data['company_name'],
#             "email": st.session_state.proposal_data['email'],
#             "phone": st.session_state.proposal_data['phone'],
#             "country": st.session_state.proposal_data['country'],
#             "proposal_date": st.session_state.proposal_data['proposal_date'],
#             "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "upload_timestamp": firestore.SERVER_TIMESTAMP,
#         }
#
#         # Download section
#         st.markdown("#### ⬇️ Download Final Proposal")
#         download_col1, download_col2 = st.columns([2, 1], gap="medium")
#
#         with download_col1:
#             default_filename = f"{st.session_state.proposal_data['client_name'].replace(' ', '_')} Proposal.pdf"
#
#             # Step 1: Confirm and upload
#             if st.button("✅ Confirm and Upload Proposal"):
#                 # storage_path, public_url = save_generated_file_to_firebase("merged_output.pdf", doc_type="Proposal",
#                 #                                                            bucket=bucket)
#                 save_generated_file_to_firebase_2(
#                     "merged_output.pdf",
#                     "Proposal",
#                     bucket,
#                     "PDF",
#                     file_upload_details
#                 )
#
#                 st.success("Now you can download the file:")
#                 # Step 2: Show download link only after upload
#                 generate_download_link("merged_output.pdf", default_filename, "PDF", "Proposal")
#
#         with download_col2:
#             if st.button("🔁 Start Over"):
#                 for key in [
#                     'proposal_form_step', 'proposal_data', 'selected_br'
#                 ]:
#                     if key in st.session_state:
#                         del st.session_state[key]
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


# def handle_proposal():
#     st.title("📄 Proposal Form")
#     regenerate_data = st.session_state.get('regenerate_data', {})
#     is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Proposal"
#     metadata = regenerate_data.get('metadata', {})
#
#     default_date = datetime.strptime(
#         metadata.get("date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#     default_name = metadata.get("client_name", "")
#     default_company_name = metadata.get("company_name", "")
#     default_email = metadata.get("email", "")
#     default_phone = metadata.get("phone", "")
#     default_country = metadata.get("country", "")
#     default_client_address = metadata.get("client_address", "")
#     default_proposal_date = datetime.strptime(
#         metadata.get("proposal_date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#
#     st.session_state.setdefault("proposal_data", {})
#     st.session_state.setdefault("proposal_form_step", 1)
#     space_ = " "
#
#     all_templates = get_proposal_template_details(firestore_db)
#     folder_paths = fetch_proposal_templates_to_temp_dir(firestore_db, bucket)
#
#     # Step 1: Basic Information
#     if st.session_state.proposal_form_step == 1:
#         with st.form("proposal_form_step1"):
#             st.subheader("Client Information")
#             name = st.text_input("Client Name", value=default_name)
#             company = st.text_input("Company Name", value=default_company_name)
#             email = st.text_input("Email", value=default_email)
#             phone = st.text_input("Phone", value=default_phone, placeholder="+1 234 5678")
#             countries = sorted([country.name for country in pycountry.countries])
#             country = st.selectbox("Select Country", countries)
#             proposal_date = st.date_input("Proposal Date", value=default_proposal_date)
#
#             if st.form_submit_button("Next: Select Cover Page"):
#                 st.session_state.proposal_data = {
#                     "client_name": name,
#                     "company_name": company,
#                     "email": email,
#                     "phone": phone,
#                     "country": country,
#                     "proposal_date": proposal_date.strftime("%B %d, %Y")
#                 }
#                 st.session_state.proposal_form_step = 2
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 2: Cover Page Selection
#     elif st.session_state.proposal_form_step == 2:
#         st.subheader("Select Cover Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 1))
#
#         cover_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "cover_page"]
#         cover_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in cover_templates
#         }
#
#         if not cover_options:
#             st.error("No valid cover templates available. Cannot proceed.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_cover_name = st.selectbox(
#                 "Choose a cover page style:",
#                 options=list(cover_options.keys()),
#                 index=0,
#                 key="cover_template_select"
#             )
#             selected_template = cover_options[selected_cover_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("cover_page", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Cover page template file not found.")
#                 return
#
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
#                 temp_img_path = temp_img.name
#
#             replace_pdf_placeholders(
#                 input_path=template_path,
#                 output_path=temp_img_path,
#                 replacements={
#                     "{ client_name }": f"{st.session_state.proposal_data['client_name']}",
#                     "{ client_email }": f"{st.session_state.proposal_data['email']}",
#                     "{ client_phone }": f"{st.session_state.proposal_data['phone']}",
#                     "{ client_country }": f"{st.session_state.proposal_data['country']}",
#                     "{ date }": f" {st.session_state.proposal_data['proposal_date']}"
#                 },
#                 y_offset=25
#             )
#
#             if os.path.exists(temp_img_path):
#                 pdf_view(temp_img_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step2"):
#             if st.form_submit_button("Next: Select Table of Contents"):
#                 st.session_state.proposal_data["cover_template"] = temp_img_path
#                 st.session_state.proposal_form_step = 3
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 3: Table of Contents Selection
#     elif st.session_state.proposal_form_step == 3:
#         st.subheader("Select Table of Contents")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 2))
#
#         toc_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "table_of_contents"]
#         toc_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in toc_templates
#         }
#
#         if not toc_options:
#             st.error("No valid table of contents templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_toc_name = st.selectbox(
#                 "Choose a table of contents style:",
#                 options=list(toc_options.keys()),
#                 index=0,
#                 key="toc_template_select"
#             )
#             selected_template = toc_options[selected_toc_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("table_of_contents", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Table of contents template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_toc:
#             #     temp_toc_path = temp_toc.name
#
#             # Apply any necessary modifications to the TOC template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step3"):
#             if st.form_submit_button("Next: Select Pages 3-6"):
#                 st.session_state.proposal_data["table_of_contents"] = template_path
#                 st.session_state.proposal_form_step = 4
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 4: Pages 3-6 Selection
#     elif st.session_state.proposal_form_step == 4:
#         st.subheader("Select Pages 3-6")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 3))
#
#         p3_p6_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "page_3_6"]
#         p3_p6_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in p3_p6_templates
#         }
#
#         if not p3_p6_options:
#             st.error("No valid page 3-6 templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_p3_p6_name = st.selectbox(
#                 "Choose pages 3-6 style:",
#                 options=list(p3_p6_options.keys()),
#                 index=0,
#                 key="p3_p6_template_select"
#             )
#             selected_template = p3_p6_options[selected_p3_p6_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("page_3_6", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Pages 3-6 template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_p3_p6:
#             #     temp_p3_p6_path = temp_p3_p6.name
#
#             # Apply any necessary modifications to the pages 3-6 template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step4"):
#             if st.form_submit_button("Next: Select Business Requirements"):
#                 st.session_state.proposal_data["p3_p6_template"] = template_path  # Storing as list for consistency
#                 st.session_state.proposal_form_step = 5
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 5: Business Requirements Selection
#     elif st.session_state.proposal_form_step == 5:
#         st.subheader("Select Business Requirements Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 4))
#
#         br_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "business_requirement"]
#         br_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in br_templates
#         }
#
#         if not br_options:
#             st.error("No valid business requirements templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_br_name = st.selectbox(
#                 "Choose a business requirements style:",
#                 options=list(br_options.keys()),
#                 index=0,
#                 key="br_template_select"
#             )
#             selected_template = br_options[selected_br_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("business_requirement", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Business requirements template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_br:
#             #     temp_br_path = temp_br.name
#
#             # Apply modifications to BR template
#             the_name = st.session_state.proposal_data['client_name']
#             if len(the_name) > 14:
#                 new_text = the_name
#             elif len(the_name) < 14:
#                 if len(the_name) < 8:
#                     lenght_dif = 11 - len(the_name)
#                     new_text = f"{space_ * lenght_dif}{the_name}"
#                 else:
#                     lenght_dif = 14 - len(the_name)
#                     new_text = f"{space_ * lenght_dif}{the_name}"
#             else:
#                 new_text = the_name
#
#             modifications = {
#                 "{ client_name }": (f"{new_text}", 0, 7),
#                 "{ date }": (f"{st.session_state.proposal_data['proposal_date']}", -30, 0)
#             }
#             editor = EditTextFile(template_path)
#             editor.modify_pdf_fields(temp_br_path, modifications)
#
#             if os.path.exists(temp_br_path):
#                 pdf_view(temp_br_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step5"):
#             if st.form_submit_button("Next: Select Testimonials"):
#                 st.session_state.proposal_data["br_template"] = temp_br_path
#                 st.session_state.proposal_form_step = 6
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 6: Testimonials Selection
#     elif st.session_state.proposal_form_step == 6:
#         st.subheader("Select Testimonials Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 5))
#
#         testimonial_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "testimonials"]
#         testimonial_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in testimonial_templates
#         }
#
#         if not testimonial_options:
#             st.error("No valid testimonial templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_testimonial_name = st.selectbox(
#                 "Choose a testimonials style:",
#                 options=list(testimonial_options.keys()),
#                 index=0,
#                 key="testimonial_template_select"
#             )
#             selected_template = testimonial_options[selected_testimonial_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("testimonials", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Testimonials template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_testimonial:
#             #     temp_testimonial_path = temp_testimonial.name
#
#             # Apply any necessary modifications to the testimonials template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step6"):
#             if st.form_submit_button("Next: Preview Proposal"):
#                 st.session_state.proposal_data["testimonials"] = template_path
#                 st.session_state.proposal_form_step = 7
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 7: Final Preview and Download
#     elif st.session_state.proposal_form_step == 7:
#         st.subheader("📄 Final Proposal Preview")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 6))
#
#         st.markdown("""
#             <style>
#                 .download-col > div {
#                     text-align: center;
#                 }
#             </style>
#         """, unsafe_allow_html=True)
#
#         # Proposal metadata summary
#         st.markdown("#### 🧾 Proposal Details")
#         col1, col2 = st.columns(2)
#
#         with col1:
#             st.write(f"**Client Name:** {st.session_state.proposal_data['client_name']}")
#             st.write(f"**Company:** {st.session_state.proposal_data['company_name']}")
#             st.write(f"**Email:** {st.session_state.proposal_data['email']}")
#             st.write(f"**Phone:** {st.session_state.proposal_data['phone']}")
#
#         with col2:
#             st.write(f"**Country:** {st.session_state.proposal_data['country']}")
#             st.write(f"**Proposal Date:** {st.session_state.proposal_data['proposal_date']}")
#
#         st.markdown("---")
#
#         # Merge all selected templates
#         merger_files = []
#
#         # Cover page
#         cover = st.session_state.proposal_data.get("cover_template")
#         if cover and os.path.exists(cover):
#             merger_files.append(cover)
#         else:
#             st.info("Cover Template not available.")
#
#         # Table of Contents
#         toc = st.session_state.proposal_data.get("table_of_contents")
#         if toc and os.path.exists(toc):
#             merger_files.append(toc)
#         else:
#             st.info("Table of Contents Template is unavailable.")
#
#         # Page 3 to 6
#         p3_p6_list = st.session_state.proposal_data.get("p3_p6_template", [])
#         if p3_p6_list:
#             available_p3_p6 = [p for p in p3_p6_list if os.path.exists(p)]
#             if available_p3_p6:
#                 merger_files.extend(available_p3_p6)
#             else:
#                 st.info("Page 3 to 6 Templates are missing.")
#         else:
#             st.info("No Page 3 to 6 Templates found.")
#
#         # Business Requirement
#         br = st.session_state.proposal_data.get("br_template")
#         if br and os.path.exists(br):
#             merger_files.append(br)
#         else:
#             st.info("Business Requirement Template unavailable.")
#
#         # Testimonials
#         testimonials = st.session_state.proposal_data.get("testimonials")
#         if testimonials and os.path.exists(testimonials):
#             merger_files.append(testimonials)
#         else:
#             st.info("Testimonial Template is unavailable.")
#
#         # Validate all files exist before merging
#         for file_path in merger_files:
#             if file_path is None:
#                 continue
#             if not os.path.exists(file_path):
#                 st.error(f"File not found: {file_path}")
#                 return
#
#         # Merge and preview
#         merger = Merger(merger_files)
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_merger:
#             temp_merger_path = temp_merger.name
#
#         merger.merge_pdf_files(temp_merger_path)
#
#         # PDF Preview
#         if os.path.exists(temp_merger_path):
#             st.markdown("#### 📑 Preview of Merged Proposal")
#             pdf_view(temp_merger_path)
#         else:
#             st.error("Merged proposal file not found.")
#             st.stop()
#
#         st.markdown("---")
#
#         # Prepare metadata for upload
#         file_upload_details = {
#             "client_name": st.session_state.proposal_data['client_name'],
#             "company_name": st.session_state.proposal_data['company_name'],
#             "email": st.session_state.proposal_data['email'],
#             "phone": st.session_state.proposal_data['phone'],
#             "country": st.session_state.proposal_data['country'],
#             "proposal_date": st.session_state.proposal_data['proposal_date'],
#             "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "upload_timestamp": firestore.SERVER_TIMESTAMP,
#         }
#
#         # Download section
#         st.markdown("#### ⬇️ Download Final Proposal")
#         download_col1, download_col2 = st.columns([2, 1], gap="medium")
#
#         with download_col1:
#             default_filename = f"{st.session_state.proposal_data['client_name'].replace(' ', '_')}_Proposal.pdf"
#
#             if st.button("✅ Confirm and Upload Proposal"):
#                 save_generated_file_to_firebase_2(
#                     temp_merger_path,
#                     "Proposal",
#                     bucket,
#                     "PDF",
#                     file_upload_details
#                 )
#                 st.success("Now you can download the file:")
#                 generate_download_link(temp_merger_path, default_filename, "PDF", "Proposal")
#
#         with download_col2:
#             if st.button("🔁 Start Over"):
#                 for key in ['proposal_form_step', 'proposal_data', 'selected_br']:
#                     if key in st.session_state:
#                         del st.session_state[key]
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()



# def handle_proposal():
#     st.title("📄 Proposal Form")
#     regenerate_data = st.session_state.get('regenerate_data', {})
#     is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Proposal"
#     metadata = regenerate_data.get('metadata', {})
#
#     default_date = datetime.strptime(
#         metadata.get("date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#     default_name = metadata.get("client_name", "")
#     default_company_name = metadata.get("company_name", "")
#     default_email = metadata.get("email", "")
#     default_phone = metadata.get("phone", "")
#     default_country = metadata.get("country", "")
#     default_client_address = metadata.get("client_address", "")
#     default_proposal_date = datetime.strptime(
#         metadata.get("proposal_date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
#
#     st.session_state.setdefault("proposal_data", {})
#     st.session_state.setdefault("proposal_form_step", 1)
#     space_ = " "
#
#     all_templates = get_proposal_template_details(firestore_db)
#     folder_paths = fetch_proposal_templates_to_temp_dir(firestore_db, bucket)
#
#     # Step 1: Basic Information
#     if st.session_state.proposal_form_step == 1:
#         with st.form("proposal_form_step1"):
#             st.subheader("Client Information")
#             name = st.text_input("Client Name", value=default_name)
#             company = st.text_input("Company Name", value=default_company_name)
#             email = st.text_input("Email", value=default_email)
#             phone = st.text_input("Phone", value=default_phone)
#             countries = sorted([country.name for country in pycountry.countries])
#             country = st.selectbox("Select Country", countries)
#             proposal_date = st.date_input("Proposal Date", value=default_proposal_date)
#
#             if st.form_submit_button("Next: Select Cover Page"):
#                 st.session_state.proposal_data = {
#                     "client_name": name,
#                     "company_name": company,
#                     "email": email,
#                     "phone": phone,
#                     "country": country,
#                     "proposal_date": proposal_date.strftime("%B %d, %Y")
#                 }
#                 st.session_state.proposal_form_step = 2
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 2: Cover Page Selection
#     elif st.session_state.proposal_form_step == 2:
#         st.subheader("Select Cover Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 1))
#
#         cover_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "cover_page"]
#         cover_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in cover_templates
#         }
#
#         if not cover_options:
#             st.error("No valid cover templates available. Cannot proceed.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_cover_name = st.selectbox(
#                 "Choose a cover page style:",
#                 options=list(cover_options.keys()),
#                 index=0,
#                 key="cover_template_select"
#             )
#             selected_template = cover_options[selected_cover_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("cover_page", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Cover page template file not found.")
#                 return
#
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
#                 temp_img_path = temp_img.name
#
#             replace_pdf_placeholders(
#                 input_path=template_path,
#                 output_path=temp_img_path,
#                 replacements={
#                     "{ client_name }": f"{st.session_state.proposal_data['client_name']}",
#                     "{ client_email }": f"{st.session_state.proposal_data['email']}",
#                     "{ client_phone }": f"{st.session_state.proposal_data['phone']}",
#                     "{ client_country }": f"{st.session_state.proposal_data['country']}",
#                     "{ date }": f" {st.session_state.proposal_data['proposal_date']}"
#                 },
#                 y_offset=25
#             )
#
#             if os.path.exists(temp_img_path):
#                 pdf_view(temp_img_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step2"):
#             if st.form_submit_button("Next: Select Table of Contents"):
#                 st.session_state.proposal_data["cover_template"] = temp_img_path
#                 st.session_state.proposal_form_step = 3
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 3: Table of Contents Selection
#     elif st.session_state.proposal_form_step == 3:
#         st.subheader("Select Table of Contents")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 2))
#
#         toc_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "table_of_contents"]
#         toc_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in toc_templates
#         }
#
#         if not toc_options:
#             st.error("No valid table of contents templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_toc_name = st.selectbox(
#                 "Choose a table of contents style:",
#                 options=list(toc_options.keys()),
#                 index=0,
#                 key="toc_template_select"
#             )
#             selected_template = toc_options[selected_toc_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("table_of_contents", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Table of contents template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_toc:
#             #     temp_toc_path = temp_toc.name
#
#             # Apply any necessary modifications to the TOC template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step3"):
#             if st.form_submit_button("Next: Select Pages 3-6"):
#                 st.session_state.proposal_data["table_of_contents"] = template_path
#                 st.session_state.proposal_form_step = 4
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 4: Pages 3-6 Selection
#     elif st.session_state.proposal_form_step == 4:
#         st.subheader("Select Pages 3-6")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 3))
#
#         p3_p6_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "page_3_6"]
#         p3_p6_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in p3_p6_templates
#         }
#
#         if not p3_p6_options:
#             st.error("No valid page 3-6 templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_p3_p6_name = st.selectbox(
#                 "Choose pages 3-6 style:",
#                 options=list(p3_p6_options.keys()),
#                 index=0,
#                 key="p3_p6_template_select"
#             )
#             selected_template = p3_p6_options[selected_p3_p6_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("page_3_6", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Pages 3-6 template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_p3_p6:
#             #     temp_p3_p6_path = temp_p3_p6.name
#
#             # Apply any necessary modifications to the pages 3-6 template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step4"):
#             if st.form_submit_button("Next: Select Business Requirements"):
#                 st.session_state.proposal_data["p3_p6_template"] = template_path  # Storing as list for consistency
#                 st.session_state.proposal_form_step = 5
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 5: Business Requirements Selection
#     elif st.session_state.proposal_form_step == 5:
#         st.subheader("Select Business Requirements Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 4))
#
#         br_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "business_requirement"]
#         br_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in br_templates
#         }
#
#         if not br_options:
#             st.error("No valid business requirements templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_br_name = st.selectbox(
#                 "Choose a business requirements style:",
#                 options=list(br_options.keys()),
#                 index=0,
#                 key="br_template_select"
#             )
#             selected_template = br_options[selected_br_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("business_requirement", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Business requirements template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_br:
#             #     temp_br_path = temp_br.name
#
#             # Apply modifications to BR template
#             the_name = st.session_state.proposal_data['client_name']
#             if len(the_name) > 14:
#                 new_text = the_name
#             elif len(the_name) < 14:
#                 if len(the_name) < 8:
#                     lenght_dif = 11 - len(the_name)
#                     new_text = f"{space_ * lenght_dif}{the_name}"
#                 else:
#                     lenght_dif = 14 - len(the_name)
#                     new_text = f"{space_ * lenght_dif}{the_name}"
#             else:
#                 new_text = the_name
#
#             modifications = {
#                 "{ client_name }": (f"{new_text}", 0, 7),
#                 "{ date }": (f"{st.session_state.proposal_data['proposal_date']}", -30, 0)
#             }
#             editor = EditTextFile(template_path)
#             editor.modify_pdf_fields(temp_br_path, modifications)
#
#             if os.path.exists(temp_br_path):
#                 pdf_view(temp_br_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step5"):
#             if st.form_submit_button("Next: Select Testimonials"):
#                 st.session_state.proposal_data["br_template"] = temp_br_path
#                 st.session_state.proposal_form_step = 6
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 6: Testimonials Selection
#     elif st.session_state.proposal_form_step == 6:
#         st.subheader("Select Testimonials Page")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 5))
#
#         testimonial_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "testimonials"]
#         testimonial_options = {
#             tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in testimonial_templates
#         }
#
#         if not testimonial_options:
#             st.error("No valid testimonial templates available.")
#             st.stop()
#
#         col1, col2 = st.columns([5, 1])
#         with col1:
#             selected_testimonial_name = st.selectbox(
#                 "Choose a testimonials style:",
#                 options=list(testimonial_options.keys()),
#                 index=0,
#                 key="testimonial_template_select"
#             )
#             selected_template = testimonial_options[selected_testimonial_name]
#
#             st.subheader("Template Details")
#             st.json({
#                 "Name": selected_template["name"],
#                 "Original Name": selected_template["original_name"],
#                 "File Type": selected_template["file_type"],
#                 "Size (KB)": selected_template["size_kb"],
#                 "Upload Date": selected_template["upload_date"],
#                 "Pages": selected_template["num_pages"],
#                 "Description": selected_template["description"],
#                 "Order Number": selected_template["order_number"],
#                 "Active": selected_template["is_active"]
#             })
#
#             template_path = fetch_path_from_temp_dir("testimonials", selected_template, folder_paths)
#
#             if not template_path:
#                 st.warning("Testimonials template file not found.")
#                 return
#
#             # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_testimonial:
#             #     temp_testimonial_path = temp_testimonial.name
#
#             # Apply any necessary modifications to the testimonials template
#             # (Add your modification logic here if needed)
#
#             if os.path.exists(template_path):
#                 pdf_view(template_path)
#             else:
#                 st.warning("Preview not available")
#
#         with st.form("proposal_form_step6"):
#             if st.form_submit_button("Next: Preview Proposal"):
#                 st.session_state.proposal_data["testimonials"] = template_path
#                 st.session_state.proposal_form_step = 7
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
#
#     # Step 7: Final Preview and Download
#     elif st.session_state.proposal_form_step == 7:
#         st.subheader("📄 Final Proposal Preview")
#         st.button("← Back", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 6))
#
#         st.markdown("""
#             <style>
#                 .download-col > div {
#                     text-align: center;
#                 }
#             </style>
#         """, unsafe_allow_html=True)
#
#         # Proposal metadata summary
#         st.markdown("#### 🧾 Proposal Details")
#         col1, col2 = st.columns(2)
#
#         with col1:
#             st.write(f"**Client Name:** {st.session_state.proposal_data['client_name']}")
#             st.write(f"**Company:** {st.session_state.proposal_data['company_name']}")
#             st.write(f"**Email:** {st.session_state.proposal_data['email']}")
#             st.write(f"**Phone:** {st.session_state.proposal_data['phone']}")
#
#         with col2:
#             st.write(f"**Country:** {st.session_state.proposal_data['country']}")
#             st.write(f"**Proposal Date:** {st.session_state.proposal_data['proposal_date']}")
#
#         st.markdown("---")
#
#         # Merge all selected templates
#         merger_files = []
#
#         # Cover page
#         cover = st.session_state.proposal_data.get("cover_template")
#         if cover and os.path.exists(cover):
#             merger_files.append(cover)
#         else:
#             st.info("Cover Template not available.")
#
#         # Table of Contents
#         toc = st.session_state.proposal_data.get("table_of_contents")
#         if toc and os.path.exists(toc):
#             merger_files.append(toc)
#         else:
#             st.info("Table of Contents Template is unavailable.")
#
#         # Page 3 to 6
#         p3_p6_list = st.session_state.proposal_data.get("p3_p6_template", [])
#         if p3_p6_list:
#             available_p3_p6 = [p for p in p3_p6_list if os.path.exists(p)]
#             if available_p3_p6:
#                 merger_files.extend(available_p3_p6)
#             else:
#                 st.info("Page 3 to 6 Templates are missing.")
#         else:
#             st.info("No Page 3 to 6 Templates found.")
#
#         # Business Requirement
#         br = st.session_state.proposal_data.get("br_template")
#         if br and os.path.exists(br):
#             merger_files.append(br)
#         else:
#             st.info("Business Requirement Template unavailable.")
#
#         # Testimonials
#         testimonials = st.session_state.proposal_data.get("testimonials")
#         if testimonials and os.path.exists(testimonials):
#             merger_files.append(testimonials)
#         else:
#             st.info("Testimonial Template is unavailable.")
#
#         # Validate all files exist before merging
#         for file_path in merger_files:
#             if file_path is None:
#                 continue
#             if not os.path.exists(file_path):
#                 st.error(f"File not found: {file_path}")
#                 return
#
#         # Merge and preview
#         merger = Merger(merger_files)
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_merger:
#             temp_merger_path = temp_merger.name
#
#         merger.merge_pdf_files(temp_merger_path)
#
#         # PDF Preview
#         if os.path.exists(temp_merger_path):
#             st.markdown("#### 📑 Preview of Merged Proposal")
#             pdf_view(temp_merger_path)
#         else:
#             st.error("Merged proposal file not found.")
#             st.stop()
#
#         st.markdown("---")
#
#         # Prepare metadata for upload
#         file_upload_details = {
#             "client_name": st.session_state.proposal_data['client_name'],
#             "company_name": st.session_state.proposal_data['company_name'],
#             "email": st.session_state.proposal_data['email'],
#             "phone": st.session_state.proposal_data['phone'],
#             "country": st.session_state.proposal_data['country'],
#             "proposal_date": st.session_state.proposal_data['proposal_date'],
#             "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "upload_timestamp": firestore.SERVER_TIMESTAMP,
#         }
#
#         # Download section
#         st.markdown("#### ⬇️ Download Final Proposal")
#         download_col1, download_col2 = st.columns([2, 1], gap="medium")
#
#         with download_col1:
#             default_filename = f"{st.session_state.proposal_data['client_name'].replace(' ', '_')}_Proposal.pdf"
#
#             if st.button("✅ Confirm and Upload Proposal"):
#                 save_generated_file_to_firebase_2(
#                     temp_merger_path,
#                     "Proposal",
#                     bucket,
#                     "PDF",
#                     file_upload_details
#                 )
#                 st.success("Now you can download the file:")
#                 generate_download_link(temp_merger_path, default_filename, "PDF", "Proposal")
#
#         with download_col2:
#             if st.button("🔁 Start Over"):
#                 for key in ['proposal_form_step', 'proposal_data', 'selected_br']:
#                     if key in st.session_state:
#                         del st.session_state[key]
#                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


def handle_proposal():
    st.title("📄 Proposal Form")
    regenerate_data = st.session_state.get('regenerate_data', {})
    is_regeneration = regenerate_data.get('source') == 'history' and regenerate_data.get('doc_type') == "Proposal"
    metadata = regenerate_data.get('metadata', {})

    default_date = datetime.strptime(
        metadata.get("date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()
    default_name = metadata.get("client_name", "")
    default_company_name = metadata.get("company_name", "")
    default_email = metadata.get("email", "")
    default_phone = metadata.get("phone", "")
    default_country = metadata.get("country", "")
    default_client_address = metadata.get("client_address", "")
    default_proposal_date = datetime.strptime(
        metadata.get("proposal_date", datetime.now().strftime('%d-%m-%Y')), '%d-%m-%Y').date()

    st.session_state.setdefault("proposal_data", {})
    st.session_state.setdefault("proposal_form_step", 1)
    space_ = " "

    all_templates = get_proposal_template_details(firestore_db)
    folder_paths = fetch_proposal_templates_to_temp_dir(firestore_db, bucket)

    # Step 1: Basic Information
    if st.session_state.proposal_form_step == 1:
        with st.form("proposal_form_step1"):
            st.subheader("Client Information")
            name = st.text_input("Client Name", value=default_name)
            company = st.text_input("Company Name", value=default_company_name)
            email = st.text_input("Email", value=default_email)
            phone = st.text_input("Phone", value=default_phone)
            countries = sorted([country.name for country in pycountry.countries])
            country = st.selectbox("Select Country", countries)
            proposal_date = st.date_input("Proposal Date", value=default_proposal_date)

            if st.form_submit_button("Next: Select Cover Page"):
                st.session_state.proposal_data = {
                    "client_name": name,
                    "company_name": company,
                    "email": email,
                    "phone": phone,
                    "country": country,
                    "proposal_date": proposal_date.strftime("%B %d, %Y")
                }
                st.session_state.proposal_form_step = 2
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    # Step 2: Cover Page Selection
    elif st.session_state.proposal_form_step == 2:
        st.subheader("Select Cover Page")
        st.button("← Back to Form", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 1))

        cover_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "cover_page"]
        cover_options = {
            tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in cover_templates
        }

        if not cover_options:
            st.error("No valid cover templates available. Cannot proceed.")
            st.stop()

        col1, col2 = st.columns([5, 1])
        with col1:
            selected_cover_name = st.selectbox(
                "Choose a cover page style:",
                options=list(cover_options.keys()),
                index=0,
                key="cover_template_select"
            )
            selected_template = cover_options[selected_cover_name]

            st.subheader("Template Details")
            st.json({
                "Name": selected_template["name"],
                "Original Name": selected_template["original_name"],
                "File Type": selected_template["file_type"],
                "Size (KB)": selected_template["size_kb"],
                "Upload Date": selected_template["upload_date"],
                "Pages": selected_template["num_pages"],
                "Description": selected_template["description"],
                "Order Number": selected_template["order_number"],
                "Active": selected_template["is_active"]
            })

            template_path = fetch_path_from_temp_dir("cover_page", selected_template, folder_paths)

            if not template_path:
                st.warning("Cover page template file not found.")
                return

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_img:
                temp_img_path = temp_img.name

            replace_pdf_placeholders(
                input_path=template_path,
                output_path=temp_img_path,
                replacements={
                    "{ client_name }": f"{st.session_state.proposal_data['client_name']}",
                    "{ client_email }": f"{st.session_state.proposal_data['email']}",
                    "{ client_phone }": f"{st.session_state.proposal_data['phone']}",
                    "{ client_country }": f"{st.session_state.proposal_data['country']}",
                    "{ date }": f" {st.session_state.proposal_data['proposal_date']}"
                },
                y_offset=25
            )

            if os.path.exists(temp_img_path):
                pdf_view(temp_img_path)
            else:
                st.warning("Preview not available")

        with st.form("proposal_form_step2"):
            if st.form_submit_button("Next: Select Business Requirements"):
                st.session_state.proposal_data["cover_template"] = temp_img_path
                st.session_state.proposal_data["cover_template_name"] = selected_template["original_name"]
                st.session_state.proposal_form_step = 3
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    # Step 3: Business Requirements Selection
    elif st.session_state.proposal_form_step == 3:
        st.subheader("Select Business Requirements Page")
        st.button("← Back to Cover Page", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 2))

        # st.subheader("Selected Templates")
        st.markdown("Selected Templates")
        # st.session_state.proposal_data["cover_template_name"]
        st.markdown(f"**Cover Template:** {st.session_state.proposal_data['cover_template_name']}")

        br_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "business_requirement"]
        br_options = {
            tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in br_templates
        }

        if not br_options:
            st.error("No valid business requirements templates available.")
            st.stop()

        col1, col2 = st.columns([5, 1])
        with col1:
            selected_br_name = st.selectbox(
                "Choose a business requirements style:",
                options=list(br_options.keys()),
                index=0,
                key="br_template_select"
            )
            selected_template = br_options[selected_br_name]

            st.subheader("Template Details")
            st.json({
                "Name": selected_template["name"],
                "Original Name": selected_template["original_name"],
                "File Type": selected_template["file_type"],
                "Size (KB)": selected_template["size_kb"],
                "Upload Date": selected_template["upload_date"],
                "Pages": selected_template["num_pages"],
                "Description": selected_template["description"],
                "Order Number": selected_template["order_number"],
                "Active": selected_template["is_active"]
            })

            template_path = fetch_path_from_temp_dir("business_requirement", selected_template, folder_paths)

            if not template_path:
                st.warning("Business requirements template file not found.")
                return

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_br:
                temp_br_path = temp_br.name

            # Apply modifications to BR template
            the_name = st.session_state.proposal_data['client_name']
            if len(the_name) > 14:
                new_text = the_name
            elif len(the_name) < 14:
                if len(the_name) < 8:
                    lenght_dif = 11 - len(the_name)
                    new_text = f"{space_ * lenght_dif}{the_name}"
                else:
                    lenght_dif = 14 - len(the_name)
                    new_text = f"{space_ * lenght_dif}{the_name}"
            else:
                new_text = the_name

            modifications = {
                "{ client_name }": (f"{new_text}", 0, 7),
                "{ date }": (f"{st.session_state.proposal_data['proposal_date']}", -30, 0)
            }
            editor = EditTextFile(template_path)
            editor.modify_pdf_fields(temp_br_path, modifications)

            if os.path.exists(temp_br_path):
                pdf_view(temp_br_path)
            else:
                st.warning("Preview not available")

        with st.form("proposal_form_step3"):
            if st.form_submit_button("Next: Select Table of Contents"):
                st.session_state.proposal_data["br_template"] = temp_br_path
                st.session_state.proposal_data["br_template_name"] = selected_template["original_name"]
                st.session_state.proposal_form_step = 4
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


    # Step 4: Table of Contents Selection
    elif st.session_state.proposal_form_step == 4:
        st.subheader("Select Table of Contents")
        st.button("← Back to Business Requirements Page", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 3))

        st.markdown("Selected Templates")
        # st.session_state.proposal_data["cover_template_name"]
        st.markdown(f"**Cover Template:** {st.session_state.proposal_data['cover_template_name']}")
        st.markdown(f"**BR Template:** {st.session_state.proposal_data['br_template_name']}")


        toc_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "table_of_contents"]
        toc_options = {
            tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in toc_templates
        }

        if not toc_options:
            st.error("No valid table of contents templates available.")
            st.stop()

        col1, col2 = st.columns([5, 1])
        with col1:
            selected_toc_name = st.selectbox(
                "Choose a table of contents style:",
                options=list(toc_options.keys()),
                index=0,
                key="toc_template_select"
            )
            selected_template = toc_options[selected_toc_name]

            st.subheader("Template Details")
            st.json({
                "Name": selected_template["name"],
                "Original Name": selected_template["original_name"],
                "File Type": selected_template["file_type"],
                "Size (KB)": selected_template["size_kb"],
                "Upload Date": selected_template["upload_date"],
                "Pages": selected_template["num_pages"],
                "Description": selected_template["description"],
                "Order Number": selected_template["order_number"],
                "Active": selected_template["is_active"]
            })

            template_path = fetch_path_from_temp_dir("table_of_contents", selected_template, folder_paths)

            if not template_path:
                st.warning("Table of contents template file not found.")
                return

            # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_toc:
            #     temp_toc_path = temp_toc.name

            # Apply any necessary modifications to the TOC template
            # (Add your modification logic here if needed)

            if os.path.exists(template_path):
                pdf_view(template_path)
            else:
                st.warning("Preview not available")

        with st.form("proposal_form_step4"):
            if st.form_submit_button("Next: Select Testimonials Page"):
                st.session_state.proposal_data["table_of_contents"] = template_path
                st.session_state.proposal_data["table_of_contents_name"] = selected_template["original_name"]
                st.session_state.proposal_form_step = 5
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


    # Step 5: Testimonials Selection
    elif st.session_state.proposal_form_step == 5:
        st.subheader("Select Testimonials Page")
        st.button("← Back to Table of Contents Page", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 4))

        st.markdown("Selected Templates")
        # st.session_state.proposal_data["cover_template_name"]
        st.markdown(f"**Cover Template:** {st.session_state.proposal_data['cover_template_name']}")
        st.markdown(f"**BR Template:** {st.session_state.proposal_data['br_template_name']}")
        st.markdown(f"**Table of Content Template:** {st.session_state.proposal_data['table_of_contents_name']}")

        testimonial_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "testimonials"]
        testimonial_options = {
            tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in testimonial_templates
        }

        if not testimonial_options:
            st.error("No valid testimonial templates available.")
            st.stop()

        col1, col2 = st.columns([5, 1])
        with col1:
            selected_testimonial_name = st.selectbox(
                "Choose a testimonials style:",
                options=list(testimonial_options.keys()),
                index=0,
                key="testimonial_template_select"
            )
            selected_template = testimonial_options[selected_testimonial_name]

            st.subheader("Template Details")
            st.json({
                "Name": selected_template["name"],
                "Original Name": selected_template["original_name"],
                "File Type": selected_template["file_type"],
                "Size (KB)": selected_template["size_kb"],
                "Upload Date": selected_template["upload_date"],
                "Pages": selected_template["num_pages"],
                "Description": selected_template["description"],
                "Order Number": selected_template["order_number"],
                "Active": selected_template["is_active"]
            })

            template_path = fetch_path_from_temp_dir("testimonials", selected_template, folder_paths)

            if not template_path:
                st.warning("Testimonials template file not found.")
                return

            # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_testimonial:
            #     temp_testimonial_path = temp_testimonial.name

            # Apply any necessary modifications to the testimonials template
            # (Add your modification logic here if needed)

            if os.path.exists(template_path):
                pdf_view(template_path)
            else:
                st.warning("Preview not available")

        with st.form("proposal_form_step5"):
            if st.form_submit_button("Next: Select Pages 3-6"):
                # st.session_state.proposal_data["table_of_contents"] = template_path
                st.session_state.proposal_data["testimonials"] = template_path
                st.session_state.proposal_data["testimonials_name"] = selected_template["original_name"]
                st.session_state.proposal_form_step = 6
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

    # Step 6: Pages 3-6 Selection
    elif st.session_state.proposal_form_step == 6:
        st.subheader("Select Pages 3-6")
        st.button("← Back to Testimonials Page", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 5))

        st.markdown("Selected Templates")
        # st.session_state.proposal_data["cover_template_name"]
        st.markdown(f"**Cover Template:** {st.session_state.proposal_data['cover_template_name']}")
        st.markdown(f"**BR Template:** {st.session_state.proposal_data['br_template_name']}")
        st.markdown(f"**Table of Content Template:** {st.session_state.proposal_data['table_of_contents_name']}")
        st.markdown(f"**Testimonial Template:** {st.session_state.proposal_data['testimonials_name']}")

        p3_p6_templates = [tpl for tpl in all_templates if tpl["proposal_section_type"] == "page_3_6"]
        p3_p6_options = {
            tpl["pdf_name"] or tpl["original_name"]: tpl for tpl in p3_p6_templates
        }

        if not p3_p6_options:
            st.error("No valid page 3-6 templates available.")
            st.stop()

        col1, col2 = st.columns([5, 1])
        with col1:
            selected_p3_p6_name = st.selectbox(
                "Choose pages 3-6 style:",
                options=list(p3_p6_options.keys()),
                index=0,
                key="p3_p6_template_select"
            )
            selected_template = p3_p6_options[selected_p3_p6_name]

            st.subheader("Template Details")
            st.json({
                "Name": selected_template["name"],
                "Original Name": selected_template["original_name"],
                "File Type": selected_template["file_type"],
                "Size (KB)": selected_template["size_kb"],
                "Upload Date": selected_template["upload_date"],
                "Pages": selected_template["num_pages"],
                "Description": selected_template["description"],
                "Order Number": selected_template["order_number"],
                "Active": selected_template["is_active"]
            })

            template_path = fetch_path_from_temp_dir("page_3_6", selected_template, folder_paths)

            if not template_path:
                st.warning("Pages 3-6 template file not found.")
                return

            # with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_p3_p6:
            #     temp_p3_p6_path = temp_p3_p6.name

            # Apply any necessary modifications to the pages 3-6 template
            # (Add your modification logic here if needed)

            if os.path.exists(template_path):
                pdf_view(template_path)
            else:
                st.warning("Preview not available")

        with st.form("proposal_form_step6"):
            if st.form_submit_button("Next: Preview Proposal"):
                st.session_state.proposal_data["p3_p6_template"] = template_path  # Storing as list for consistency
                print(st.session_state.proposal_data["p3_p6_template"])
                st.session_state.proposal_data["p3_p6_template_name"] = selected_template["original_name"]
                st.session_state.proposal_form_step = 7
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()



    # Step 7: Final Preview and Download
    elif st.session_state.proposal_form_step == 7:


        st.subheader("📄 Final Proposal Preview")
        st.button("← Back to Pages 3-6", on_click=lambda: setattr(st.session_state, 'proposal_form_step', 6))

        st.markdown("Selected Templates")
        # st.session_state.proposal_data["cover_template_name"]
        st.markdown(f"**Cover Template:** {st.session_state.proposal_data['cover_template_name']}")
        st.markdown(f"**BR Template:** {st.session_state.proposal_data['br_template_name']}")
        st.markdown(f"**Table of Content Template:** {st.session_state.proposal_data['table_of_contents_name']}")
        st.markdown(f"**Testimonial Template:** {st.session_state.proposal_data['testimonials_name']}")
        st.markdown(f"**Page 3-6  Template:** {st.session_state.proposal_data['p3_p6_template_name']}")
        st.write("PROPOSAL Metadata", st.session_state.proposal_data)

        st.markdown("""
            <style>
                .download-col > div {
                    text-align: center;
                }
            </style>
        """, unsafe_allow_html=True)

        # Proposal metadata summary
        st.markdown("#### 🧾 Proposal Details")
        col1, col2 = st.columns(2)

        with col1:
            st.write(f"**Client Name:** {st.session_state.proposal_data['client_name']}")
            st.write(f"**Company:** {st.session_state.proposal_data['company_name']}")
            st.write(f"**Email:** {st.session_state.proposal_data['email']}")
            st.write(f"**Phone:** {st.session_state.proposal_data['phone']}")

        with col2:
            st.write(f"**Country:** {st.session_state.proposal_data['country']}")
            st.write(f"**Proposal Date:** {st.session_state.proposal_data['proposal_date']}")

        st.markdown("---")

        # Merge all selected templates
        merger_files = []

        # Cover page
        cover = st.session_state.proposal_data.get("cover_template")
        if cover and os.path.exists(cover):
            merger_files.append(cover)
        else:
            st.info("Cover Template not available.")

        # Table of Contents
        toc = st.session_state.proposal_data.get("table_of_contents")
        if toc and os.path.exists(toc):
            merger_files.append(toc)
        else:
            st.info("Table of Contents Template is unavailable.")

        # Page 3 to 6
        # p3_p6_list = st.session_state.proposal_data.get("p3_p6_template", [])
        # if p3_p6_list:
        #     available_p3_p6 = [p for p in p3_p6_list if os.path.exists(p)]
        #     if available_p3_p6:
        #         merger_files.extend(available_p3_p6)
        #     else:
        #         st.info("Page 3 to 6 Templates are missing.")
        # else:
        #     st.info("No Page 3 to 6 Templates found.")

        p3_p6 = st.session_state.proposal_data.get("p3_p6_template")
        if p3_p6 and os.path.exists(p3_p6):
            merger_files.append(p3_p6)
        else:
            st.info("Page 3 to 6 Templates are missing.")

        # Business Requirement
        br = st.session_state.proposal_data.get("br_template")
        if br and os.path.exists(br):
            merger_files.append(br)
        else:
            st.info("Business Requirement Template unavailable.")

        # Testimonials
        testimonials = st.session_state.proposal_data.get("testimonials")
        if testimonials and os.path.exists(testimonials):
            merger_files.append(testimonials)
        else:
            st.info("Testimonial Template is unavailable.")

        if not merger_files:
            st.error("No templates were selected or all file paths are missing.")
            st.stop()

        # Validate all files exist before merging
        for file_path in merger_files:
            print("---------------------------------")
            print(file_path)
            if file_path is None:

                continue
            if not os.path.exists(file_path):
                st.error(f"File not found: {file_path}")
                return

        # Merge and preview
        merger = Merger(merger_files)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_merger:
            temp_merger_path = temp_merger.name

        merger.merge_pdf_files(temp_merger_path)

        # PDF Preview
        if os.path.exists(temp_merger_path):
            st.markdown("#### 📑 Preview of Merged Proposal")
            pdf_view(temp_merger_path)
        else:
            st.error("Merged proposal file not found.")
            st.stop()

        st.markdown("---")

        # Prepare metadata for upload
        file_upload_details = {
            "client_name": st.session_state.proposal_data['client_name'],
            "company_name": st.session_state.proposal_data['company_name'],
            "email": st.session_state.proposal_data['email'],
            "phone": st.session_state.proposal_data['phone'],
            "country": st.session_state.proposal_data['country'],
            "proposal_date": st.session_state.proposal_data['proposal_date'],
            "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "upload_timestamp": firestore.SERVER_TIMESTAMP,
        }

        # Download section
        st.markdown("#### ⬇️ Download Final Proposal")
        download_col1, download_col2 = st.columns([2, 1], gap="medium")

        # with download_col1:
        #     default_filename = f"{st.session_state.proposal_data['client_name'].replace(' ', '_')}_Proposal.pdf"
        #
        #     if st.button("✅ Confirm and Upload Proposal"):
        #         save_generated_file_to_firebase_2(
        #             temp_merger_path,
        #             "Proposal",
        #             bucket,
        #             "PDF",
        #             file_upload_details
        #         )
        #         st.success("Now you can download the file:")
        #         # generate_download_link(temp_merger_path, default_filename, "PDF", "Proposal")
        #         with open(temp_merger_path, "rb") as f:
        #             file_bytes = f.read()
        #
        #         st.download_button(
        #             label="📥 Download",
        #             data=file_bytes,
        #             file_name=default_filename,
        #             mime="application/pdf",
        #             use_container_width=True
        #         )

        with download_col1:
            default_filename = f"{st.session_state.proposal_data['client_name'].replace(' ', '_')}_Proposal.pdf"

            if "proposal_uploaded" not in st.session_state:
                st.session_state.proposal_uploaded = False

            if not st.session_state.proposal_uploaded:
                if st.button("✅ Confirm and Upload Proposal"):
                    save_generated_file_to_firebase_2(
                        temp_merger_path,
                        "Proposal",
                        bucket,
                        "PDF",
                        file_upload_details
                    )
                    st.session_state.proposal_uploaded = True
                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
            else:
                st.success("Proposal uploaded successfully. You can download it below:")

                with open(temp_merger_path, "rb") as f:
                    file_bytes = f.read()

                st.download_button(
                    label="📥 Download Proposal",
                    data=file_bytes,
                    file_name=default_filename,
                    mime="application/pdf",
                    use_container_width=True
                )

        with download_col2:
            if st.button("🔁 Start Over"):
                for key in ['proposal_form_step', 'proposal_data', 'selected_br']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


