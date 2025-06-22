import time
import os
from datetime import datetime, timedelta
import streamlit as st
from dotenv import load_dotenv
from firebase_conf import auth, rt_db, bucket, firestore_db
from document_handlers import (handle_internship_certificate, handle_internship_offer, handle_relieving_letter,
                               handle_nda,
                               handle_contract, handle_proposal, handle_invoice)
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
import tempfile
import pdfplumber
from apscheduler.schedulers.background import BackgroundScheduler
from manage_internship_roles_tab import manage_internship_roles_tab
from docx_pdf_converter import main_converter
from load_config import LOAD_LOCALLY

load_dotenv()

# LOAD_LOCALLY = False


def cleanup_broken_metadata():
    """Check for and remove Firestore documents that reference non-existent storage blobs"""
    try:
        # Get all document types (e.g., Proposal, NDA, etc.)
        doc_types = firestore_db.collection("HVT_DOC_Gen").stream()

        for doc_type in doc_types:
            # Get all templates for this document type
            templates_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type.id).collection("templates")
            docs = templates_ref.stream()

            for doc in docs:
                data = doc.to_dict()
                if 'storage_path' in data:
                    blob = bucket.blob(data['storage_path'])
                    if not blob.exists():
                        st.warning(f"Deleting broken Firestore doc: {data.get('original_name', doc.id)}")
                        templates_ref.document(doc.id).delete()

    except Exception as e:
        st.error(f"Error during metadata cleanup: {str(e)}")


# Set up scheduled cleanup (runs daily at 2 AM)
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_broken_metadata, 'cron', hour=2)
scheduler.start()

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False


def logout():
    st.session_state.user = None
    st.session_state.is_admin = False
    st.sidebar.success("Logged out successfully!")
    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()


def admin_login(email, password):
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        user_info = auth.get_account_info(user['idToken'])

        if user_info['users'][0]['email'] in st.secrets["custom"]["ADMIN_EMAILS"]:
            st.session_state.user = user
            st.session_state.is_admin = True
            st.success("Admin login successful!")
            return True
        else:
            st.error("Access denied. Not an admin account.")
            return False
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return False


# Document types
DOCUMENT_TYPES = [
    "Internship Certificate",
    "Internship Offer",
    "Relieving Letter",
    # "NDA",
    # "Contract",
    "Project Invoice",
    "Project Contract",
    "Project NDA",
    "Proposal",
    "Admin Panel"
]

# Sidebar - Navigation and logout
# Add "History" to the list if admin is logged in
if st.session_state.get('is_admin', False):
    DOCUMENT_TYPES.insert(-1, "History")

# st.sidebar.title("📑 Navigation")
st.sidebar.title("📑 Menu")
if 'pending_redirect' in st.session_state:
    st.session_state['selected_option'] = st.session_state.pop('pending_redirect')

# selected_option = st.sidebar.radio("Choose a document type or Admin Panel", DOCUMENT_TYPES)
selected_option = st.sidebar.radio("Choose a document type or Admin Panel", DOCUMENT_TYPES, key="selected_option")

# Show logout button if logged in
if st.session_state.user:
    if st.sidebar.button("🚪 Logout"):
        logout()

# Admin panel
if selected_option == "Admin Panel":
    st.title("🔐 Admin Panel")

    if not st.session_state.is_admin:
        # Login form
        with st.form("admin_login_form"):
            admin_user = st.text_input("Admin Email")
            admin_pass = st.text_input("Password", type="password")
            # # twitter_like_password_field("Password")
            # password = streamlit_style_password_input("Enter your password")

            login = st.form_submit_button("Login")

            if login:
                if admin_login(admin_user, admin_pass):
                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
    else:
        # Admin dashboard
        st.success(f"Welcome Admin! ({st.session_state.user['email']})")

        # Admin panel content
        st.header("📁 Template Management")
        st.subheader("Upload New Templates")

        # Template upload section
        with st.expander("➕ Upload Template", expanded=True):

            doc_type = st.selectbox(
                "Select Document Type",
                ["Internship Certificate", "Internship Offer", "Relieving Letter", "Project Invoice", "Project Contract",
                 "Project NDA", "Proposal"],
                key="doc_type_select"
            )

            uploaded_file = st.file_uploader(
                f"Upload {doc_type} Template",
                type=["docx", "pdf"],
                key=f"upload_{doc_type}"
            )

            if uploaded_file:
                # Additional fields for all templates
                with st.form("template_details_form"):
                    display_name = st.text_input(
                        "Template Display Name",
                        placeholder="Enter a name for this template (will be shown in UI)",
                        help="This name will be used for previews and displays in the application"
                    )

                    visibility = st.radio(
                        "Visibility",
                        ["Public", "Private"],
                        help="Public templates can be accessed by all users"
                    )

                    order = st.number_input("Template Order", min_value=1, value=1)

                    description = st.text_area("Template Description",
                                               placeholder="Enter a detailed description of the template including its purpose and usage")

                    # Additional fields for Proposal
                    if doc_type == "Proposal":
                        proposal_subdir = st.selectbox(
                            "Proposal Template Category",
                            ["Cover Page", "Table of Contents", "Business Requirement", "Page 3 to 6", "Testimonials"],
                            help="Choose which part of the proposal this template belongs to"
                        )

                        subdir_map = {
                            "Cover Page": "cover_page",
                            "Table of Contents": "table_of_contents",
                            "Business Requirement": "business_requirement",
                            "Page 3 to 6": "page_3_6",
                            "Testimonials": "testimonials"
                        }
                        normalized_subdir = subdir_map[proposal_subdir]

                        # Additional fields for Proposal templates
                        pdf_name = st.text_input("Name of PDF (if applicable)")
                        num_pages = st.number_input("BR Pages Number", min_value=1, value=1)

                    if st.form_submit_button("Save Template"):
                        if not display_name:
                            st.error("Please provide a display name for the template")
                        else:
                            try:
                                # Get reference to the new database
                                template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)

                                # Generate unique filename
                                file_extension = uploaded_file.name.split('.')[-1]
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                new_filename = f"{display_name.lower().replace(' ', '_')}_{timestamp}.{file_extension}"

                                # Define storage paths
                                if doc_type == "Proposal":
                                    storage_path = f"HVT_DOC_Gen/Proposal/{normalized_subdir}/{new_filename}"
                                else:
                                    storage_path = f"HVT_DOC_Gen/{doc_type.lower().replace(' ', '_')}/templates/{new_filename}"

                                # Upload to Firebase Storage
                                blob = bucket.blob(storage_path)
                                blob.upload_from_string(
                                    uploaded_file.getvalue(),
                                    content_type=uploaded_file.type
                                )

                                # Generate download URL
                                download_url = blob.generate_signed_url(
                                    expiration=datetime.timedelta(days=365 * 10),  # 10 year expiration
                                    version="v4"
                                ) if visibility == "Private" else blob.public_url

                                # Prepare base metadata
                                file_details = {
                                    "display_name": display_name,
                                    "original_name": uploaded_file.name,
                                    "doc_type": doc_type,
                                    "order": order,
                                    "file_type": uploaded_file.type,
                                    "size_kb": f"{len(uploaded_file.getvalue()) / 1024:.1f}",
                                    "size_bytes": len(uploaded_file.getvalue()),
                                    "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "upload_timestamp": firestore.SERVER_TIMESTAMP,
                                    "download_url": download_url,
                                    "storage_path": storage_path,
                                    "visibility": visibility,
                                    "description": description,
                                    "is_active": True,
                                    "last_updated": firestore.SERVER_TIMESTAMP
                                }

                                # Add proposal-specific fields if needed
                                if doc_type == "Proposal":
                                    file_details.update({
                                        "template_part": proposal_subdir,
                                        "proposal_section_type": normalized_subdir,
                                        "pdf_name": pdf_name,
                                        "num_pages": num_pages
                                    })
                                else:
                                    if file_extension.lower() == 'docx':
                                        try:
                                            # Create temporary directory if it doesn't exist
                                            temp_dir = os.path.join(tempfile.gettempdir(), "as_docgen")
                                            os.makedirs(temp_dir, exist_ok=True)

                                            # Create unique temp file paths
                                            temp_docx = os.path.join(temp_dir, f"upload_{timestamp}.docx")
                                            temp_pdf = os.path.join(temp_dir, f"preview_{timestamp}.pdf")

                                            # Write the uploaded file to temp location
                                            with open(temp_docx, 'wb') as f:
                                                f.write(uploaded_file.getvalue())

                                            # Convert to PDF
                                            main_converter(temp_docx, temp_pdf)

                                            # Upload PDF version
                                            pdf_storage_path = f"HVT_DOC_Gen/{doc_type.lower().replace(' ', '_')}/pdf_previews/{display_name.replace(' ', '_')}.pdf"

                                            pdf_blob = bucket.blob(pdf_storage_path)
                                            with open(temp_pdf, 'rb') as pdf_file:
                                                pdf_blob.upload_from_file(pdf_file, content_type='application/pdf')

                                            # Set the correct ACL based on visibility
                                            if visibility == "Public":
                                                pdf_blob.make_public()  # This sets the object to be publicly readable
                                                pdf_url = pdf_blob.public_url
                                            else:
                                                # For private objects, we need to ensure we have proper permissions
                                                try:
                                                    pdf_url = pdf_blob.generate_signed_url(
                                                        expiration=datetime.timedelta(days=365 * 10),
                                                        version="v4",
                                                        method='GET'
                                                    )
                                                except Exception as e:
                                                    st.error(f"Failed to generate signed URL: {str(e)}")
                                                    # Fallback to using the blob path if URL generation fails
                                                    pdf_url = f"gs://{bucket.name}/{pdf_blob.name}"

                                            # Add PDF metadata
                                            file_details.update({
                                                "pdf_preview_url": pdf_url,
                                                "pdf_storage_path": pdf_storage_path,
                                                "has_pdf_preview": True,
                                                "pdf_visibility": visibility  # Store visibility setting for the PDF
                                            })

                                        except Exception as e:
                                            st.error(f"PDF conversion failed: {str(e)}")
                                            raise  # Re-raise the exception to stop the process
                                        finally:
                                            # Clean up temp files if they exist
                                            if os.path.exists(temp_docx):
                                                os.remove(temp_docx)
                                            if os.path.exists(temp_pdf):
                                                os.remove(temp_pdf)

                                # Save to Firestore
                                if doc_type == "Proposal":
                                    template_ref.collection(normalized_subdir).add(file_details)
                                else:
                                    template_ref.collection("templates").add(file_details)

                                st.success(f"Template '{display_name}' saved successfully!")
                                # st.markdown(f"**Download Link:** [Click here]({download_url})")
                                # if 'pdf_preview_url' in file_details:
                                #     st.markdown(f"**PDF Preview:** [View PDF]({file_details['pdf_preview_url']})")

                            except Exception as e:
                                st.error(f"Error saving template: {str(e)}")
                                st.exception(e)

            # if uploaded_file:
            #     # Additional fields for all templates
            #     with st.form("template_details_form"):
            #         visibility = st.radio(
            #             "Visibility",
            #             ["Public", "Private"],
            #             help="Public templates can be accessed by all users"
            #         )
            #
            #         description = st.text_area("Template Description",
            #                                    placeholder="Enter a detailed description of the template including its purpose and usage")
            #
            #         # Additional fields for Proposal
            #         if doc_type == "Proposal":
            #             proposal_subdir = st.selectbox(
            #                 "Proposal Template Category",
            #                 ["Cover Page", "Table of Contents", "Business Requirement", "Page 3 to 6", "Testimonials"],
            #                 help="Choose which part of the proposal this template belongs to"
            #             )
            #
            #             subdir_map = {
            #                 "Cover Page": "cover_page",
            #                 "Table of Contents": "table_of_contents",
            #                 "Business Requirement": "business_requirement",
            #                 "Page 3 to 6": "page_3_6",
            #                 "Testimonials": "testimonials"
            #             }
            #             normalized_subdir = subdir_map[proposal_subdir]
            #
            #             # Additional fields for Proposal templates
            #             pdf_name = st.text_input("Name of PDF (if applicable)")
            #             num_pages = st.number_input("BR Pages Number", min_value=1, value=1)
            #
            #         if st.form_submit_button("Save Template"):
            #             try:
            #                 # Get reference to the new database
            #                 template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
            #
            #                 # Generate unique filename
            #                 file_extension = uploaded_file.name.split('.')[-1]
            #                 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            #                 new_filename = f"{doc_type.lower()}_{timestamp}.{file_extension}"
            #                 clean_filename = uploaded_file.name.split('.')[0]  # For display purposes
            #
            #                 # Define storage paths
            #                 if doc_type == "Proposal":
            #                     storage_path = f"AS_DOC_Gen/Proposal/{normalized_subdir}/{new_filename}"
            #                 else:
            #                     storage_path = f"AS_DOC_Gen/{doc_type.lower().replace(' ', '_')}/templates/{new_filename}"
            #
            #                 # Upload to Firebase Storage
            #                 blob = bucket.blob(storage_path)
            #                 blob.upload_from_string(
            #                     uploaded_file.getvalue(),
            #                     content_type=uploaded_file.type
            #                 )
            #
            #                 # Generate download URL
            #                 download_url = blob.generate_signed_url(
            #                     expiration=datetime.timedelta(days=365 * 10),  # 10 year expiration
            #                     version="v4"
            #                 ) if visibility == "Private" else blob.public_url
            #
            #                 # Prepare base metadata
            #                 file_details = {
            #                     "display_name": clean_filename,
            #                     "original_name": uploaded_file.name,
            #                     "doc_type": doc_type,
            #                     "file_type": uploaded_file.type,
            #                     "size_kb": f"{len(uploaded_file.getvalue()) / 1024:.1f}",
            #                     "size_bytes": len(uploaded_file.getvalue()),
            #                     "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            #                     "upload_timestamp": firestore.SERVER_TIMESTAMP,
            #                     "download_url": download_url,
            #                     "storage_path": storage_path,
            #                     "visibility": visibility,
            #                     "description": description,
            #                     "is_active": True,
            #                     "last_updated": firestore.SERVER_TIMESTAMP
            #                 }
            #
            #                 # Add proposal-specific fields if needed
            #                 if doc_type == "Proposal":
            #                     file_details.update({
            #                         "template_part": proposal_subdir,
            #                         "proposal_section_type": normalized_subdir,
            #                         "pdf_name": pdf_name,
            #                         "num_pages": num_pages
            #                     })
            #                 else:
            #                     # For non-Proposal docs, convert to PDF and store both versions
            #                     if file_extension.lower() == 'docx':
            #                         # Create temporary files
            #                         temp_docx = f"/tmp/{new_filename}"
            #                         temp_pdf = f"/tmp/{clean_filename}.pdf"
            #
            #                         with open(temp_docx, 'wb') as f:
            #                             f.write(uploaded_file.getvalue())
            #
            #                         # Convert to PDF
            #                         main_converter(temp_docx, temp_pdf)
            #
            #                         # Upload PDF version
            #                         pdf_storage_path = f"AS_DOC_Gen/{doc_type.lower().replace(' ', '_')}/pdf_previews/{clean_filename}.pdf"
            #                         pdf_blob = bucket.blob(pdf_storage_path)
            #                         with open(temp_pdf, 'rb') as pdf_file:
            #                             pdf_blob.upload_from_file(pdf_file, content_type='application/pdf')
            #
            #                         # Generate PDF URL
            #                         pdf_url = pdf_blob.generate_signed_url(
            #                             expiration=datetime.timedelta(days=365 * 10),
            #                             version="v4"
            #                         ) if visibility == "Private" else pdf_blob.public_url
            #
            #                         # Add PDF metadata
            #                         file_details.update({
            #                             "pdf_preview_url": pdf_url,
            #                             "pdf_storage_path": pdf_storage_path,
            #                             "has_pdf_preview": True
            #                         })
            #
            #                         # Clean up temp files
            #                         os.remove(temp_docx)
            #                         os.remove(temp_pdf)
            #
            #                 # Save to Firestore
            #                 if doc_type == "Proposal":
            #                     template_ref.collection(normalized_subdir).add(file_details)
            #                 else:
            #                     template_ref.collection("templates").add(file_details)
            #
            #                 st.success(f"Template saved successfully as {clean_filename}!")
            #                 st.markdown(f"**Download Link:** [Click here]({download_url})")
            #                 if 'pdf_preview_url' in file_details:
            #                     st.markdown(f"**PDF Preview:** [View PDF]({file_details['pdf_preview_url']})")
            #
            #             except Exception as e:
            #                 st.error(f"Error saving template: {str(e)}")
            #                 st.exception(e)

            # if uploaded_file:
            #     # Additional fields for all templates
            #     with st.form("template_details_form"):
            #
            #         visibility = st.radio(
            #             "Visibility",
            #             ["Public", "Private"],
            #             help="Public templates can be accessed by all users"
            #         )
            #
            #         description = st.text_area("Template Description",
            #                                    placeholder="Name of Template and Keyword(e.g "
            #                                                "Internship Certificate Template Male)")
            #
            #         # Additional fields for Proposal
            #         if doc_type == "Proposal":
            #             proposal_subdir = st.selectbox(
            #                 "Proposal Template Category",
            #                 ["Cover Page", "Table of Contents", "Business Requirement", "Page 3 to 6", "Testimonials"],
            #                 help="Choose which part of the proposal this template belongs to"
            #             )
            #
            #             subdir_map = {
            #                 "Cover Page": "cover_page",
            #                 "Table of Contents": "table_of_contents",
            #                 "Business Requirement": "business_requirement",
            #                 "Page 3 to 6": "page_3_6",
            #                 "Testimonials": "testimonials"
            #             }
            #             normalized_subdir = subdir_map[proposal_subdir]
            #
            #             # Additional fields for Proposal templates
            #             pdf_name = st.text_input("Name of PDF (if applicable)")
            #             num_pages = st.number_input("BR Pages Number", min_value=1, value=1)
            #
            #         if st.form_submit_button("Save Template"):
            #             try:
            #                 # Get reference to the new database
            #                 template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
            #
            #                 count = len([doc.id for doc in template_ref.collection(
            #                     normalized_subdir if doc_type == "Proposal" else "templates").get()])
            #
            #                 order_number = count + 1
            #                 file_extension = uploaded_file.name.split('.')[-1]
            #                 new_filename = f"template{order_number}.{file_extension}"
            #
            #                 # Define storage paths
            #                 if doc_type == "Proposal":
            #                     storage_path = f"AS_DOC_Gen/Proposal/{normalized_subdir}/{new_filename}"
            #                 else:
            #                     storage_path = f"AS_DOC_Gen/{doc_type.lower().replace(' ', '_')}/templates/{new_filename}"
            #
            #                 # Upload to Firebase Storage
            #                 blob = bucket.blob(storage_path)
            #                 blob.upload_from_string(
            #                     uploaded_file.getvalue(),
            #                     content_type=uploaded_file.type
            #                 )
            #
            #                 # Generate download URL
            #                 download_url = blob.generate_signed_url(
            #                     expiration=datetime.timedelta(days=365 * 10),  # 10 year expiration
            #                     version="v4"
            #                 ) if visibility == "Private" else blob.public_url
            #
            #                 # Prepare metadata
            #                 file_details = {
            #                     "name": new_filename,
            #                     "original_name": uploaded_file.name,
            #                     "doc_type": doc_type,
            #                     "file_type": uploaded_file.type,
            #                     "size_kb": f"{len(uploaded_file.getvalue()) / 1024:.1f}",
            #                     "size_bytes": len(uploaded_file.getvalue()),
            #                     "upload_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            #                     "upload_timestamp": firestore.SERVER_TIMESTAMP,
            #                     "download_url": download_url,
            #                     "storage_path": storage_path,
            #                     "visibility": visibility,
            #                     "description": description,
            #                     "order_number": order_number,
            #                     "is_active": True
            #                 }
            #
            #                 # Add proposal-specific fields if needed
            #                 if doc_type == "Proposal":
            #                     file_details.update({
            #                         "template_part": proposal_subdir,
            #                         "proposal_section_type": normalized_subdir,
            #                         "pdf_name": pdf_name,
            #                         "num_pages": num_pages
            #                     })
            #
            #                 # Save to Firestore
            #                 if doc_type == "Proposal":
            #                     template_ref.collection(normalized_subdir).add(file_details)
            #                 else:
            #                     template_ref.collection("templates").add(file_details)
            #
            #                 # Update the document count
            #                 template_ref.set({
            #                     "template_count": order_number,
            #                     "last_updated": firestore.SERVER_TIMESTAMP
            #                 }, merge=True)
            #
            #                 st.success(f"Template saved successfully as {new_filename}!")
            #                 st.markdown(f"**Download Link:** [Click here]({download_url})")
            #
            #             except Exception as e:
            #                 st.error(f"Error saving template: {str(e)}")
            #                 st.exception(e)

        # Template management in tabs
        st.subheader("Manage Templates")
        from streamlit_sortables import sort_items
        import streamlit as st
        import pdfplumber


        def preview_pdf_all_pages(pdf_path: str):
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        preview_image = page.to_image(resolution=100)
                        if LOAD_LOCALLY:
                            st.image(
                                preview_image.original,
                                caption=f"Page {i + 1}",
                                use_column_width=True
                            )
                        else:
                            st.image(
                                preview_image.original,
                                caption=f"Page {i + 1}",
                                use_container_width=True
                            )
            except Exception as e:
                st.warning(f"Could not preview PDF: {str(e)}")


        from google.cloud import storage
        from datetime import timedelta


        def generate_signed_url(bucket_name, blob_name, expiration_minutes=60):
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
            )
            return url


        def show_templates_tab(doc_type):
            st.subheader(f"{doc_type} Templates")
            template_ref = firestore_db.collection("HVT_DOC_Gen").document(doc_type)

            if doc_type == "Proposal":
                # Use section names as Firestore subcollections
                section_map = {
                    "Cover Page": "cover_page",
                    "Table of Contents": "table_of_contents",
                    "Business Requirement": "business_requirement",
                    "Page 3 to 6": "page_3_6",
                    "Testimonials": "testimonials"
                }

                for section_label, section_key in section_map.items():
                    st.markdown(f"### 📂 {section_label}")
                    # templates = template_ref.collection(section_key).order_by("upload_timestamp",
                    #                                                           direction="DESCENDING").get()
                    # templates = template_ref.collection(section_key).order_by("order",
                    #                                                           direction="DESCENDING").get()

                    docs = template_ref.collection(section_key).get()

                    # Sort manually: if 'order' exists, use it; otherwise, fallback to 'upload_timestamp'
                    templates = sorted(
                        docs,
                        key=lambda doc: (
                            -(doc.to_dict().get("order", float('-inf')) if "order" in doc.to_dict() else 0),
                            doc.to_dict().get("upload_timestamp")
                        ),
                        reverse=True
                    )

                    if not templates:
                        st.info(f"No templates in {section_label}")
                        continue

                    for template_doc in templates:
                        template_data = template_doc.to_dict()
                        doc_id = template_doc.id

                        # Initialize session state for edit mode and preview
                        if f"edit_mode_{doc_id}" not in st.session_state:
                            st.session_state[f"edit_mode_{doc_id}"] = False
                        if f"show_preview_{doc_id}" not in st.session_state:
                            st.session_state[f"show_preview_{doc_id}"] = False

                        with st.expander(
                                f"📄 {template_data.get('display_name', template_data.get('original_name', 'Unnamed'))}"):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                # Disabled fields by default, enabled when edit mode is on
                                new_display_name = st.text_input(
                                    "Display Name",
                                    value=template_data.get("display_name", ""),
                                    key=f"display_name_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )
                                new_name = st.text_input(
                                    "PDF Name",
                                    value=template_data.get("pdf_name", ""),
                                    key=f"pdf_name_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )
                                new_order = st.number_input(
                                    "Order",
                                    min_value=0,
                                    value=int(template_data.get("order", 0)),
                                    key=f"order_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )
                                new_num_pages = st.number_input(
                                    "BR pages number",
                                    min_value=1,
                                    value=int(template_data.get("num_pages", 1)),
                                    key=f"num_pages_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )
                                new_desc = st.text_area(
                                    "Description",
                                    value=template_data.get("description", ""),
                                    key=f"desc_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )
                                new_vis = st.selectbox(
                                    "Visibility",
                                    ["Public", "Private"],
                                    index=["Public", "Private"].index(template_data.get("visibility", "Public")),
                                    key=f"vis_{doc_id}",
                                    disabled=not st.session_state[f"edit_mode_{doc_id}"]
                                )

                            with col2:
                                # Delete button
                                if st.button("🗑️ Delete Template", key=f"delete_{doc_id}"):
                                    try:
                                        # Delete both the original file and PDF preview if exists
                                        blob = bucket.blob(template_data['storage_path'])
                                        blob.delete()
                                        if 'pdf_storage_path' in template_data:
                                            pdf_blob = bucket.blob(template_data['pdf_storage_path'])
                                            pdf_blob.delete()
                                        template_ref.collection(section_key).document(doc_id).delete()
                                        st.success("Template deleted successfully")
                                        st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
                                    except Exception as e:
                                        st.error(f"Error deleting: {e}")

                                # Edit toggle button
                                edit_button_label = "✏️ Edit" if not st.session_state[
                                    f"edit_mode_{doc_id}"] else "✏️ Editing"
                                if st.button(edit_button_label, key=f"edit_toggle_{doc_id}"):
                                    st.session_state[f"edit_mode_{doc_id}"] = not st.session_state[
                                        f"edit_mode_{doc_id}"]
                                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                                # Save button (only shown in edit mode)
                                if st.session_state[f"edit_mode_{doc_id}"]:
                                    if st.button("💾 Save Changes", key=f"save_{doc_id}"):
                                        update_data = {
                                            "display_name": new_display_name,
                                            "description": new_desc,
                                            "order": new_order,
                                            "visibility": new_vis,
                                            "pdf_name": new_name,
                                            "num_pages": new_num_pages,
                                            "last_updated": firestore.SERVER_TIMESTAMP
                                        }

                                        # Check if we need to generate PDF preview
                                        if (doc_type != "Proposal" and
                                                template_data[
                                                    'file_type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' and
                                                not template_data.get('has_pdf_preview', False)):

                                            try:
                                                with st.spinner("Generating PDF preview..."):
                                                    # Create temp directory
                                                    temp_dir = os.path.join(tempfile.gettempdir(), "as_docgen")
                                                    os.makedirs(temp_dir, exist_ok=True)

                                                    # Create temp file paths
                                                    temp_docx = os.path.join(temp_dir, f"regenerate_{doc_id}.docx")
                                                    temp_pdf = os.path.join(temp_dir, f"preview_{doc_id}.pdf")

                                                    # Download original DOCX
                                                    blob = bucket.blob(template_data['storage_path'])
                                                    blob.download_to_filename(temp_docx)

                                                    # Convert to PDF
                                                    main_converter(temp_docx, temp_pdf)

                                                    # Upload PDF version
                                                    clean_name = new_display_name or template_data.get('display_name',
                                                                                                       'preview')
                                                    pdf_storage_path = f"HVT_DOC_Gen/{doc_type.lower().replace(' ', '_')}/pdf_previews/{clean_name.replace(' ', '_')}_{doc_id}.pdf"
                                                    pdf_blob = bucket.blob(pdf_storage_path)

                                                    with open(temp_pdf, 'rb') as pdf_file:
                                                        pdf_blob.upload_from_file(pdf_file,
                                                                                  content_type='application/pdf')

                                                    # Generate PDF URL
                                                    pdf_url = pdf_blob.generate_signed_url(
                                                        expiration=datetime.timedelta(days=365 * 10),
                                                        version="v4"
                                                    ) if new_vis == "Private" else pdf_blob.public_url

                                                    # Add PDF metadata to update
                                                    update_data.update({
                                                        "pdf_preview_url": pdf_url,
                                                        "pdf_storage_path": pdf_storage_path,
                                                        "has_pdf_preview": True
                                                    })

                                                    st.success("PDF preview generated successfully")

                                            except Exception as e:
                                                st.error(f"Failed to generate PDF preview: {str(e)}")
                                                st.exception(e)
                                            finally:
                                                # Clean up temp files if they exist
                                                if os.path.exists(temp_docx):
                                                    os.remove(temp_docx)
                                                if os.path.exists(temp_pdf):
                                                    os.remove(temp_pdf)

                                        # Update Firestore document
                                        try:
                                            template_ref.collection(section_key).document(doc_id).update(update_data)
                                            st.session_state[f"edit_mode_{doc_id}"] = False
                                            st.success("Metadata updated successfully")
                                            st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed to update template: {str(e)}")
                                # if st.session_state[f"edit_mode_{doc_id}"]:
                                #     if st.button("💾 Save Changes", key=f"save_{doc_id}"):
                                #         update_data = {
                                #             "display_name": new_display_name,
                                #             "description": new_desc,
                                #             "visibility": new_vis,
                                #             "pdf_name": new_name,
                                #             "num_pages": new_num_pages,
                                #             "last_updated": firestore.SERVER_TIMESTAMP
                                #         }
                                #         template_ref.collection(section_key).document(doc_id).update(update_data)
                                #         st.session_state[f"edit_mode_{doc_id}"] = False
                                #         st.success("Metadata updated successfully")
                                #         st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                                # Preview toggle button
                                preview_button_label = "👁️ Show Preview" if not st.session_state[
                                    f"show_preview_{doc_id}"] else "👁️ Hide Preview"
                                if st.button(preview_button_label, key=f"preview_toggle_{doc_id}"):
                                    st.session_state[f"show_preview_{doc_id}"] = not st.session_state[
                                        f"show_preview_{doc_id}"]
                                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                            # Preview section (conditionally shown)
                            if st.session_state[f"show_preview_{doc_id}"]:
                                preview_url = None
                                if template_data.get('has_pdf_preview', False):
                                    preview_url = template_data.get('pdf_preview_url')
                                elif template_data['file_type'] == 'application/pdf' and template_data[
                                    'visibility'] == 'Public':
                                    preview_url = template_data['download_url']

                                if preview_url:
                                    try:
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                                            blob = bucket.blob(template_data[
                                                                   'pdf_storage_path'] if 'pdf_storage_path' in template_data else
                                                               template_data['storage_path'])
                                            blob.download_to_filename(tmp_file.name)
                                            preview_pdf_all_pages(tmp_file.name)
                                    except Exception as e:
                                        st.warning(f"❌ Could not load preview: {str(e)}")
                                else:
                                    st.warning("No preview available for this template")

                            st.markdown(f"**Uploaded:** {template_data.get('upload_date', 'Unknown')}")
                            st.markdown(
                                f"**Download:** [{template_data['original_name']}]({template_data['download_url']})")

            else:
                # templates = template_ref.collection("templates").order_by("upload_timestamp",
                #                                                           direction="DESCENDING").get()

                docs = template_ref.collection("templates").get()
                templates = sorted(
                    docs,
                    key=lambda doc: (
                        -(doc.to_dict().get("order", float('-inf')) if "order" in doc.to_dict() else 0),
                        doc.to_dict().get("upload_timestamp")
                    ),
                    reverse=True
                )

                if not templates:
                    st.info("No templates found.")
                    return

                for template_doc in templates:
                    template_data = template_doc.to_dict()
                    doc_id = template_doc.id

                    # Initialize session state for this template
                    if f"edit_mode_{doc_id}" not in st.session_state:
                        st.session_state[f"edit_mode_{doc_id}"] = False
                    if f"show_preview_{doc_id}" not in st.session_state:
                        st.session_state[f"show_preview_{doc_id}"] = False

                    with st.expander(
                            f"📄 {template_data.get('display_name', template_data.get('original_name', 'Unnamed'))}"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            new_display_name = st.text_input(
                                "Display Name",
                                value=template_data.get("display_name", ""),
                                key=f"display_name_{doc_id}",
                                disabled=not st.session_state[f"edit_mode_{doc_id}"]
                            )
                            new_order = st.number_input(
                                "Order",
                                min_value=0,
                                value=int(template_data.get("order", 0)),
                                key=f"order_{doc_id}",
                                disabled=not st.session_state[f"edit_mode_{doc_id}"]
                            )
                            new_desc = st.text_area(
                                "Description",
                                value=template_data.get("description", ""),
                                key=f"desc_{doc_id}",
                                disabled=not st.session_state[f"edit_mode_{doc_id}"]
                            )
                            new_vis = st.selectbox(
                                "Visibility",
                                ["Public", "Private"],
                                index=["Public", "Private"].index(template_data.get("visibility", "Public")),
                                key=f"vis_{doc_id}",
                                disabled=not st.session_state[f"edit_mode_{doc_id}"]
                            )

                        with col2:
                            # Delete button
                            if st.button("🗑️ Delete Template", key=f"delete_{doc_id}"):
                                try:
                                    # Delete both the original file and PDF preview if exists
                                    blob = bucket.blob(template_data['storage_path'])
                                    blob.delete()
                                    if 'pdf_storage_path' in template_data:
                                        pdf_blob = bucket.blob(template_data['pdf_storage_path'])
                                        pdf_blob.delete()
                                    template_ref.collection("templates").document(doc_id).delete()
                                    st.success("Template deleted successfully")
                                    st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
                                except Exception as e:
                                    st.error(f"Error deleting: {e}")

                            # Edit toggle button
                            edit_button_label = "✏️ Edit" if not st.session_state[
                                f"edit_mode_{doc_id}"] else "✏️ Editing"
                            if st.button(edit_button_label, key=f"edit_toggle_{doc_id}"):
                                st.session_state[f"edit_mode_{doc_id}"] = not st.session_state[f"edit_mode_{doc_id}"]
                                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                            # Save button (only shown in edit mode)
                            if st.session_state[f"edit_mode_{doc_id}"]:
                                if st.button("💾 Save Changes", key=f"save_{doc_id}"):
                                    update_data = {
                                        "display_name": new_display_name,
                                        "order": new_order,
                                        "description": new_desc,
                                        "visibility": new_vis,
                                        "last_updated": firestore.SERVER_TIMESTAMP
                                    }
                                    if (doc_type != "Proposal" and
                                            template_data[
                                                'file_type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' and
                                            not template_data.get('has_pdf_preview', False)):

                                        try:
                                            with st.spinner("Generating PDF preview..."):
                                                # Create temp directory
                                                temp_dir = os.path.join(tempfile.gettempdir(), "as_docgen")
                                                os.makedirs(temp_dir, exist_ok=True)

                                                # Create temp file paths
                                                temp_docx = os.path.join(temp_dir, f"regenerate_{doc_id}.docx")
                                                temp_pdf = os.path.join(temp_dir, f"preview_{doc_id}.pdf")

                                                # Download original DOCX
                                                blob = bucket.blob(template_data['storage_path'])
                                                blob.download_to_filename(temp_docx)

                                                # Convert to PDF
                                                main_converter(temp_docx, temp_pdf)

                                                # Upload PDF version
                                                clean_name = new_display_name or template_data.get('display_name',
                                                                                                   'preview')
                                                pdf_storage_path = f"HVT_DOC_Gen/{doc_type.lower().replace(' ', '_')}/pdf_previews/{clean_name.replace(' ', '_')}_{doc_id}.pdf"
                                                pdf_blob = bucket.blob(pdf_storage_path)

                                                with open(temp_pdf, 'rb') as pdf_file:
                                                    pdf_blob.upload_from_file(pdf_file,
                                                                              content_type='application/pdf')

                                                # Generate PDF URL
                                                pdf_url = pdf_blob.generate_signed_url(
                                                    expiration=datetime.timedelta(days=365 * 10),
                                                    version="v4"
                                                ) if new_vis == "Private" else pdf_blob.public_url

                                                # Add PDF metadata to update
                                                update_data.update({
                                                    "pdf_preview_url": pdf_url,
                                                    "pdf_storage_path": pdf_storage_path,
                                                    "has_pdf_preview": True
                                                })

                                                st.success("PDF preview generated successfully")

                                        except Exception as e:
                                            st.error(f"Failed to generate PDF preview: {str(e)}")
                                            st.exception(e)
                                        finally:
                                            # Clean up temp files if they exist
                                            if os.path.exists(temp_docx):
                                                os.remove(temp_docx)
                                            if os.path.exists(temp_pdf):
                                                os.remove(temp_pdf)

                                    # Update Firestore document
                                    try:
                                        template_ref.collection("templates").document(doc_id).update(update_data)
                                        st.session_state[f"edit_mode_{doc_id}"] = False
                                        st.success("Metadata updated successfully")
                                        st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to update template: {str(e)}")

                                    # template_ref.collection("templates").document(doc_id).update(update_data)
                                    # st.session_state[f"edit_mode_{doc_id}"] = False
                                    # st.success("Metadata updated successfully")
                                    # st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                            # Preview toggle button
                            preview_button_label = "👁️ Show Preview" if not st.session_state[
                                f"show_preview_{doc_id}"] else "👁️ Hide Preview"
                            if st.button(preview_button_label, key=f"preview_toggle_{doc_id}"):
                                st.session_state[f"show_preview_{doc_id}"] = not st.session_state[
                                    f"show_preview_{doc_id}"]
                                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                        # Preview section (conditionally shown)
                        if st.session_state[f"show_preview_{doc_id}"]:
                            preview_url = None
                            if template_data.get('has_pdf_preview', False):
                                preview_url = template_data.get('pdf_preview_url')
                            elif template_data['file_type'] == 'application/pdf' and template_data[
                                'visibility'] == 'Public':
                                preview_url = template_data['download_url']

                            if preview_url:
                                try:
                                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                                        blob = bucket.blob(template_data[
                                                               'pdf_storage_path'] if 'pdf_storage_path' in template_data else
                                                           template_data['storage_path'])
                                        blob.download_to_filename(tmp_file.name)
                                        preview_pdf_all_pages(tmp_file.name)
                                except Exception as e:
                                    st.warning(f"❌ Could not load preview: {str(e)}")
                            else:
                                st.warning("No preview available for this template")

                        st.markdown(f"**Uploaded:** {template_data.get('upload_date', 'Unknown')}")
                        st.markdown(f"**File Type:** {template_data.get('file_type', 'Unknown')}")
                        # st.markdown(
                        #     f"**Download:** [{template_data['original_name']}]({template_data['download_url']})")
                        blob = bucket.blob(template_data['storage_path'])
                        blob.make_public()
                        public_url = blob.public_url
                        st.markdown(f"**Download:** [{template_data['original_name']}]({public_url})")


        # def show_templates_tab(doc_type):
        #     st.subheader(f"{doc_type} Templates")
        #     template_ref = firestore_db.collection("AS_DOC_Gen").document(doc_type)
        #
        #     if doc_type == "Proposal":
        #         # Use section names as Firestore subcollections
        #         section_map = {
        #             "Cover Page": "cover_page",
        #             "Table of Contents": "table_of_contents",
        #             "Business Requirement": "business_requirement",
        #             "Page 3 to 6": "page_3_6",
        #             "Testimonials": "testimonials"
        #         }
        #
        #         for section_label, section_key in section_map.items():
        #             st.markdown(f"### 📂 {section_label}")
        #             templates = template_ref.collection(section_key).order_by("order_number").get()
        #
        #             if not templates:
        #                 st.info(f"No templates in {section_label}")
        #                 continue
        #
        #             for template_doc in templates:
        #                 template_data = template_doc.to_dict()
        #                 doc_id = template_doc.id
        #
        #                 # Initialize session state for edit mode and preview
        #                 if f"edit_mode_{doc_id}" not in st.session_state:
        #                     st.session_state[f"edit_mode_{doc_id}"] = False
        #                 if f"show_preview_{doc_id}" not in st.session_state:
        #                     st.session_state[f"show_preview_{doc_id}"] = False
        #
        #                 with st.expander(
        #                         f"📄 {template_data.get('original_name', 'Unnamed')} (Order: {template_data['order_number']})"):
        #                     col1, col2 = st.columns([3, 1])
        #                     with col1:
        #                         # Disabled fields by default, enabled when edit mode is on
        #                         new_name = st.text_area(
        #                             "PDF Name",
        #                             value=template_data.get("pdf_name", ""),
        #                             key=f"pdf_name_{doc_id}",
        #                             disabled=not st.session_state[f"edit_mode_{doc_id}"]
        #                         )
        #                         new_num_pages = st.number_input(
        #                             "BR pages number",
        #                             min_value=1,
        #                             value=int(template_data.get("num_pages", 1)),
        #                             key=f"num_pages_{doc_id}",
        #                             disabled=not st.session_state[f"edit_mode_{doc_id}"]
        #                         )
        #                         new_desc = st.text_area(
        #                             "Description",
        #                             value=template_data.get("description", ""),
        #                             key=f"desc_{doc_id}",
        #                             disabled=not st.session_state[f"edit_mode_{doc_id}"]
        #                         )
        #                         new_vis = st.selectbox(
        #                             "Visibility",
        #                             ["Public", "Private"],
        #                             index=["Public", "Private"].index(template_data.get("visibility", "Public")),
        #                             key=f"vis_{doc_id}",
        #                             disabled=not st.session_state[f"edit_mode_{doc_id}"]
        #                         )
        #
        #                     with col2:
        #                         # Delete button
        #                         if st.button("🗑️ Delete Template", key=f"delete_{doc_id}"):
        #                             try:
        #                                 blob = bucket.blob(template_data['storage_path'])
        #                                 blob.delete()
        #                                 template_ref.collection(section_key).document(doc_id).delete()
        #                                 st.success("Template deleted successfully")
        #                                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #                             except Exception as e:
        #                                 st.error(f"Error deleting: {e}")
        #
        #                         # Edit toggle button
        #                         edit_button_label = "✏️ Edit" if not st.session_state[
        #                             f"edit_mode_{doc_id}"] else "✏️ Editing"
        #                         if st.button(edit_button_label, key=f"edit_toggle_{doc_id}"):
        #                             st.session_state[f"edit_mode_{doc_id}"] = not st.session_state[
        #                                 f"edit_mode_{doc_id}"]
        #                             st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #
        #                         # Save button (only shown in edit mode)
        #                         if st.session_state[f"edit_mode_{doc_id}"]:
        #                             if st.button("💾 Save Changes", key=f"save_{doc_id}"):
        #                                 template_ref.collection(section_key).document(doc_id).update({
        #                                     "description": new_desc,
        #                                     "visibility": new_vis,
        #                                     "pdf_name": new_name,
        #                                     "num_pages": new_num_pages
        #                                 })
        #                                 st.session_state[f"edit_mode_{doc_id}"] = False
        #                                 st.success("Metadata updated successfully")
        #                                 st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #
        #                         # Preview toggle button
        #                         preview_button_label = "👁️ Show Preview" if not st.session_state[
        #                             f"show_preview_{doc_id}"] else "👁️ Hide Preview"
        #                         if st.button(preview_button_label, key=f"preview_toggle_{doc_id}"):
        #                             st.session_state[f"show_preview_{doc_id}"] = not st.session_state[
        #                                 f"show_preview_{doc_id}"]
        #                             st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #
        #                     # Preview section (conditionally shown)
        #                     if st.session_state[f"show_preview_{doc_id}"] and template_data[
        #                         'file_type'] == 'application/pdf' and template_data['visibility'] == 'Public':
        #                         try:
        #                             with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        #                                 blob = bucket.blob(template_data['storage_path'])
        #                                 blob.download_to_filename(tmp_file.name)
        #                                 preview_pdf_all_pages(tmp_file.name)
        #                         except Exception as e:
        #                             st.warning(f"❌ Skipping missing or broken preview: {str(e)}")
        #
        #                     st.markdown(
        #                         f"**Download:** [{template_data['original_name']}]({template_data['download_url']})")
        #
        #     else:
        #         templates = template_ref.collection("templates").order_by("order_number").get()
        #         if not templates:
        #             st.info("No templates found.")
        #             return
        #
        #         for template_doc in templates:
        #             template_data = template_doc.to_dict()
        #             doc_id = template_doc.id
        #
        #             with st.expander(
        #                     f"📄 {template_data.get('original_name', 'Unnamed')} (Order: {template_data['order_number']})"):
        #                 col1, col2 = st.columns([3, 1])
        #                 with col1:
        #                     new_desc = st.text_area("Edit Description", value=template_data.get("description", ""),
        #                                             key=f"desc_{doc_id}")
        #                     new_vis = st.selectbox("Visibility", ["Public", "Private"],
        #                                            index=["Public", "Private"].index(
        #                                                template_data.get("visibility", "Public")), key=f"vis_{doc_id}")
        #                     if st.button("💾 Save Changes", key=f"save_{doc_id}"):
        #                         template_ref.collection("templates").document(doc_id).update({
        #                             "description": new_desc,
        #                             "visibility": new_vis
        #                         })
        #                         st.success("Metadata updated successfully")
        #                         st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #
        #                 with col2:
        #                     if st.button("🗑️ Delete Template", key=f"delete_{doc_id}"):
        #                         try:
        #                             blob = bucket.blob(template_data['storage_path'])
        #                             blob.delete()
        #                             template_ref.collection("templates").document(doc_id).delete()
        #                             st.success("Template deleted successfully")
        #                             st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
        #                         except Exception as e:
        #                             st.error(f"Error deleting: {e}")
        #
        #                 if template_data['file_type'] == 'application/pdf' and template_data['visibility'] == 'Public':
        #                     try:
        #                         with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        #                             blob = bucket.blob(template_data['storage_path'])
        #                             blob.download_to_filename(tmp_file.name)
        #                             preview_pdf_all_pages(tmp_file.name)
        #                     except Exception as e:
        #                         st.warning(f"❌ Skipping missing or broken preview: {str(e)}")
        #
        #                 st.markdown(
        #                     f"**Download:** [{template_data['original_name']}]({template_data['download_url']})")
        #

        # tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        #     ["Internship Certificate",
        #      # "NDA",
        #      # "Invoice",
        #      # "Contract",
        #      # "Proposal",
        #      "Internship Positions"
        #      ])
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(
            ["Internship Certificate",
             "Internship Offer",
             "Relieving Letter",
             # "NDA",
             # "Contract",
             "Project Invoice",
             "Project Contract",
             "Project NDA",
             "Proposal",
             "Internship Positions"
             ])



        with tab1:
            show_templates_tab("Internship Certificate")

        with tab2:
            show_templates_tab("Internship Offer")

        with tab3:
            show_templates_tab("Relieving Letter")

        # with tab4:
        #     show_templates_tab("NDA")
        #
        # with tab5:
        #     show_templates_tab("Contract")

        with tab4:
            show_templates_tab("Project Invoice")

        with tab5:
            show_templates_tab("Project Contract")

        with tab6:
            show_templates_tab("Project NDA")

        with tab7:
            show_templates_tab("Proposal")

        with tab8:
            manage_internship_roles_tab()



elif selected_option == "History" and st.session_state.get('is_admin', False):
    st.title("📜 Generated Documents History")

    # Create tabs for each document type
    # tab1, tab2, tab3, tab4, tab5 = st.tabs([
    #     "Internship",
    #     "NDA",
    #     "Invoice",
    #     "Contract",
    #     "Proposal"
    # ])
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Internship",
        "Internship Offer",
        "Relieving Letter",
        # "NDA",
        # "Contract",
        "Project Invoice",
        "Project Contract",
        "Project NDA",
        "Proposal"
    ])


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
                        )
                    else:
                        st.image(
                            page.to_image(resolution=150).original,
                            caption=f"Page {i + 1}",
                            use_container_width=True
                        )
                    # AS_DOC_Gen

        except Exception as e:
            st.warning(f"Couldn't generate PDF preview: {str(e)}")



    def display_documents_by_type(doc_type):
        try:
            # Query all documents and filter locally
            all_docs = firestore_db.collection("generated_files").stream()
            filtered_docs = []

            for doc in all_docs:
                data = doc.to_dict()
                if data.get('doc_type') == doc_type:
                    filtered_docs.append((doc.id, data))

            # Sort by upload_timestamp if available
            try:
                filtered_docs.sort(key=lambda x: x[1].get('upload_timestamp'), reverse=True)
            except:
                pass

            if not filtered_docs:
                st.info(f"No generated {doc_type} documents found.")
                return

            import io  # for BytesIO

            for doc_id, data in filtered_docs:
                # with st.expander(
                #         f"📄 {data.get('name', data.get('client_name', data.get('intern', 'Unnamed Document')))} - {data.get('upload_date', '')}"):

                with st.expander(
                        f"📄 {data.get('name', data.get('client_name', data.get('intern', 'Unnamed Document')))} - {doc_type} - {data.get('upload_date', '')}"
                ):

                    col1, col2 = st.columns([3, 1])

                    # Unique preview toggle key
                    preview_key = f"preview_{doc_id}"
                    if preview_key not in st.session_state:
                        st.session_state[preview_key] = False

                    # Container for the preview section
                    preview_container = st.container()

                    with col2:
                        # Toggle preview button
                        if st.button("👁️ Show/Hide Preview", key=f"toggle_{doc_id}"):
                            st.session_state[preview_key] = not st.session_state[preview_key]

                    temp_file_bytes = None  # Initialize to be used in download later

                    with col1:
                        st.subheader("Metadata")
                        st.json(data)

                        # Only try preview if user toggled it
                        if st.session_state[preview_key] and 'storage_path' in data:
                            st.write(f"Attempting to preview: {data['storage_path']}")
                            try:
                                _, ext = os.path.splitext(data['storage_path'])
                                if ext.lower() not in ['.pdf', '.docx']:
                                    ext = '.pdf'  # Default to PDF to be safe
                                # Create a temporary file
                                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                                    tmp_path = tmp_file.name

                                # Download the file from Firebase
                                blob = bucket.blob(data['storage_path'])
                                blob.download_to_filename(tmp_path)
                                st.write(f"File downloaded to: {tmp_path}")

                                # Save file contents to BytesIO for download reuse
                                with open(tmp_path, "rb") as f:
                                    temp_file_bytes = f.read()

                                # Preview PDF
                                if os.path.exists(tmp_path):
                                    st.write("File exists, attempting preview...")
                                    if tmp_path.endswith('.pdf'):
                                        pdf_view(tmp_path)
                                    elif tmp_path.endswith('.docx'):
                                        with tempfile.NamedTemporaryFile(suffix="pdf", delete=False) as pdf_tmp_file:
                                            pdf_tmp_path = pdf_tmp_file.name
                                            main_converter(tmp_path, pdf_tmp_path)
                                            pdf_view(pdf_tmp_file)
                                else:
                                    st.error("Downloaded file not found!")

                                os.unlink(tmp_path)

                            except Exception as download_error:
                                st.error(f"Download/preview failed: {str(download_error)}")
                                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                                    os.unlink(tmp_path)

                    with col2:
                        # Download button using previously downloaded file
                        if temp_file_bytes:
                            # st.download_button(
                            #     label="⬇️ Download",
                            #     data=temp_file_bytes,
                            #     file_name=data.get('name', 'document'),
                            #     mime=data.get('file_type', 'application/pdf'),
                            #     key=f"download_{doc_id}"
                            # )
                            if st.button("🔄 Regenerate",
                                         key=f"regenerate_{data.get('name', data.get('client_name', data.get('intern', 'Unnamed Document')))}"):
                                st.session_state['regenerate_data'] = {
                                    'doc_type': doc_type,
                                    'metadata': data,
                                    'source': 'history'
                                }

                                doc_type_map = {
                                    "Internship": "Internship Certificate",
                                    "Offer": "Internship Offer",
                                    "Relieving Letter": "Relieving Letter",
                                    # "NDA": "NDA",
                                    # "Contract": "Contract",
                                    "Project Invoice": "Project Invoice",
                                    "Contract": "Project Contract",
                                    "NDA": "Project NDA",
                                    "Proposal": "Proposal"
                                }
                                # print("here-----------")
                                # print(data.get('doc_type'))
                                # Set the matching sidebar label
                                st.session_state['pending_redirect'] = doc_type_map.get(doc_type, "Admin Panel")
                                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()

                        else:
                            st.caption(f"Preview to Regenerate {doc_type}.")

                        # Download button
                        if 'storage_path' in data:
                            try:
                                blob = bucket.blob(data['storage_path'])

                                # Download to a temporary file
                                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                                    blob.download_to_filename(tmp_file.name)

                                with open(tmp_file.name, "rb") as file:
                                    file_bytes = file.read()

                                st.download_button(
                                    label="⬇️ Download",
                                    data=file_bytes,
                                    file_name=data.get("name", "document.pdf"),
                                    mime="application/octet-stream",  # You can change MIME type if known
                                    key=f"download_{doc_id}"
                                )

                            except Exception as e:
                                st.error(f"Error downloading file: {e}")

                        # Delete button
                        if st.button("🗑️ Delete", key=f"delete_{doc_id}"):
                            try:
                                # Delete from storage if path exists
                                if 'storage_path' in data:
                                    blob = bucket.blob(data['storage_path'])
                                    blob.delete()

                                # Delete from Firestore
                                firestore_db.collection("generated_files").document(doc_id).delete()

                                st.success("Document deleted successfully")
                                st.experimental_rerun() if LOAD_LOCALLY else st.rerun()
                            except Exception as e:
                                st.error(f"Error deleting document: {str(e)}")

                        # Optional extra info
                        if 'client_name' in data:
                            st.caption(f"Client: {data['client_name']}")

        except Exception as e:
            st.error(f"Error loading documents: {str(e)}")


    with tab1:
        display_documents_by_type("Internship")

    with tab2:
        display_documents_by_type("Internship Offer")

    with tab3:
        display_documents_by_type("Relieving Letter")

    # with tab4:
    #     display_documents_by_type("NDA")
    #
    # with tab5:
    #     display_documents_by_type("Contract")

    with tab4:
        display_documents_by_type("Project Invoice")

    with tab5:
        display_documents_by_type("Contract")

    with tab6:
        display_documents_by_type("NDA")

    with tab7:
        display_documents_by_type("Proposal")

# Handle document types
elif selected_option == "Internship Certificate":
    handle_internship_certificate()

elif selected_option == "Internship Offer":
    handle_internship_offer()

elif selected_option == "Relieving Letter":
    handle_relieving_letter()

# elif selected_option == "NDA":
#     handle_nda()
#
# elif selected_option == "Contract":
#     handle_contract()

elif selected_option == "Project Invoice":
    handle_invoice()

elif selected_option == "Project Contract":
    handle_contract()

elif selected_option == "Project NDA":
    handle_nda()

elif selected_option == "Proposal":
    handle_proposal()
