import pyrebase
import os
from dotenv import load_dotenv
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage

load_dotenv()


firebaseConfig = {
    "apiKey": st.secrets["API_KEY"],
    "authDomain": st.secrets["AUTH_DOMAIN"],
    "databaseURL": st.secrets["DATABASE_URL"],
    "projectId": st.secrets["PROJECT_ID"],
    "storageBucket": st.secrets["STORAGE_BUCKET"],
    "messagingSenderId": st.secrets["MESSAGING_SENDER_ID"],
    "appId": st.secrets["APP_ID"],
    "measurementId": st.secrets["MEASUREMENT_ID"]
}


firebase_credentials = {
    "type": st.secrets["firebase"]["type"],
    "project_id": st.secrets["firebase"]["project_id"],
    "private_key_id": st.secrets["firebase"]["private_key_id"],
    "private_key": st.secrets["firebase"]["private_key"].replace("\\n", "\n"),  # <- no replace() here
    "client_email": st.secrets["firebase"]["client_email"],
    "client_id": st.secrets["firebase"]["client_id"],
    "auth_uri": st.secrets["firebase"]["auth_uri"],
    "token_uri": st.secrets["firebase"]["token_uri"],
    "auth_provider_x509_cert_url": st.secrets["firebase"]["auth_provider_x509_cert_url"],
    "client_x509_cert_url": st.secrets["firebase"]["client_x509_cert_url"]
}

cred = credentials.Certificate(firebase_credentials)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'storageBucket': st.secrets["STORAGE_BUCKET"]
    })

# Initialize services

bucket = storage.bucket(st.secrets["STORAGE_BUCKET"])
firestore_db = firestore.client()

# Initialize Pyrebase
firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
rt_db = firebase.database()

# docs = firestore_db.collection("hvt_generator").document("Proposal").collection("templates").limit(1).get()
# print([doc.id for doc in docs])


