import streamlit as st
import requests
import os
import sys
import time

UNINITIALIZED_VALUE = 'UNINITIALIZED'

# Configuration
CONFIG = {
    'BASE_URL': st.secrets["adobe"]["BASE_URL"],
    'CLIENT_ID': st.secrets["adobe"]["CLIENT_ID"],
    'CLIENT_SECRET': st.secrets["adobe"]["CLIENT_SECRET"],
}


def make_request_with_retry(request_func, max_retries=3, initial_delay=1):
    """Helper function to retry requests on connection errors"""
    for attempt in range(max_retries):
        try:
            return request_func()
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            if attempt == max_retries - 1:
                raise
            delay = initial_delay * (2 ** attempt)
            time.sleep(delay)
    raise Exception("Max retries exceeded unexpectedly")


def get_access_token(client_id, client_secret, base_url):
    def request():
        response = requests.post(
            url=base_url + '/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_id': client_id,
                'client_secret': client_secret
            }
        )
        response.raise_for_status()
        return response.json()['access_token']

    return make_request_with_retry(request)


def get_upload_uri(access_token, client_id, base_url):
    def request():
        response = requests.post(
            base_url + '/assets',
            headers={
                'Authorization': f'Bearer {access_token}',
                'x-api-key': client_id,
                'Content-Type': 'application/json',
            },
            json={
                'mediaType': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
        )
        response.raise_for_status()
        data = response.json()
        return data['uploadUri'], data['assetID']

    return make_request_with_retry(request)


def upload_docx(upload_url, docx_filename):
    def request():
        with open(docx_filename, 'rb') as f:
            file_size = os.path.getsize(docx_filename)
            response = requests.put(
                upload_url,
                headers={
                    'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'Content-Length': str(file_size)
                },
                data=f
            )
        response.raise_for_status()

    make_request_with_retry(request)


def create_pdf(access_token, client_id, asset_id, base_url):
    def request():
        response = requests.post(
            base_url + '/operation/createpdf',
            headers={
                'Authorization': f'Bearer {access_token}',
                'x-api-key': client_id,
                'Content-Type': 'application/json'
            },
            json={
                'assetID': asset_id
            }
        )
        response.raise_for_status()
        return response.headers['Location']

    return make_request_with_retry(request)


def retrieve_pdf(access_token, client_id, location):
    while True:
        def request():
            response = requests.get(
                location,
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'x-api-key': client_id,
                }
            )
            response.raise_for_status()
            return response.json()

        data = make_request_with_retry(request)

        if data['status'] == 'done':
            return data['asset']['downloadUri']
        elif data['status'] != 'in progress':
            raise Exception(f'Unknown status: {data["status"]}')
        time.sleep(1)  # Wait before polling again


def download_pdf(download_uri, pdf_filename):
    def request():
        response = requests.get(download_uri)
        response.raise_for_status()
        with open(pdf_filename, 'wb') as f:
            f.write(response.content)

    make_request_with_retry(request)


def delete_asset(access_token, client_id, asset_id, base_url):
    def request():
        response = requests.delete(
            base_url + f'/assets/{asset_id}',
            headers={
                'Authorization': f'Bearer {access_token}',
                'x-api-key': client_id,
            }
        )
        response.raise_for_status()

    make_request_with_retry(request)


def main_converter(docx_filename, output_filename):
    if output_filename == "":
        output_filename = os.path.splitext(docx_filename)[0] + '.pdf'
    base_url = CONFIG['BASE_URL']
    client_id = CONFIG['CLIENT_ID']
    client_secret = CONFIG['CLIENT_SECRET']

    if client_id == UNINITIALIZED_VALUE or client_secret == UNINITIALIZED_VALUE:
        raise Exception("Client ID or Secret not set")

    access_token = get_access_token(client_id, client_secret, base_url)
    upload_url, asset_id = get_upload_uri(access_token, client_id, base_url)
    upload_docx(upload_url, docx_filename)
    location = create_pdf(access_token, client_id, asset_id, base_url)
    download_uri = retrieve_pdf(access_token, client_id, location)
    pdf_filename = output_filename
    download_pdf(download_uri, pdf_filename)
    delete_asset(access_token, client_id, asset_id, base_url)
    print(f"PDF generated successfully: {pdf_filename}")


# if __name__ == "__main__":
#     main_converter("Generated_Contract.docx")

# main_converter("Generated_Contract_105.docx")

