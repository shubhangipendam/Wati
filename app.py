from flask import Flask, request, jsonify
import requests
import json
import os
from dotenv import load_dotenv 

load_dotenv()
app = Flask(__name__)

# zoho credentials 
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

# 🔹 Fetch API URLs from .env (Optional, but useful)
ZOHO_BIGIN_SEARCH_URL = os.getenv("ZOHO_BIGIN_SEARCH_URL")
ZOHO_BIGIN_CONTACT_URL = os.getenv("ZOHO_BIGIN_CONTACT_URL")
# ZOHO_BIGIN_NOTES_URL = os.getenv("ZOHO_BIGIN_NOTES_URL")
ZOHO_REFRESH_TOKEN_URL = os.getenv("ZOHO_REFRESH_TOKEN_URL")

# Initial Access Token (Will be updated dynamically)
ZOHO_ACCESS_TOKEN = None

def refresh_access_token():
    """
    Generates a new Zoho OAuth access token using the refresh token.
    """
    global ZOHO_ACCESS_TOKEN

    payload = {
        "refresh_token": ZOHO_REFRESH_TOKEN,
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token"
    }

    response = requests.post(ZOHO_REFRESH_TOKEN_URL, data=payload)

    if response.status_code == 200:
        token_data = response.json()
        ZOHO_ACCESS_TOKEN = token_data["access_token"]
        print(f"✅ New Access Token Generated: {ZOHO_ACCESS_TOKEN}")
        return ZOHO_ACCESS_TOKEN
    else:
        print(f"❌ Failed to Refresh Token: {response.text}")
        return None
    
@app.route("/")
def home():
    return "✅ Flask app is running!", 200

    
@app.route("/check-env")
def check_env():
    return {
        "ZOHO_CLIENT_ID": os.getenv("ZOHO_CLIENT_ID"),
        "ZOHO_CLIENT_SECRET": os.getenv("ZOHO_CLIENT_SECRET"),
        "ZOHO_REFRESH_TOKEN": os.getenv("ZOHO_REFRESH_TOKEN")
    }


@app.route("/wati-webhook", methods=["POST"])
def wati_webhook():
    """
    Webhook to receive WhatsApp messages from WATI and sync with Zoho Bigin.
    """

    global ZOHO_ACCESS_TOKEN

    print("🔹 WATI Webhook Triggered")
    print("🔹 Headers:", request.headers)
    print("🔹 Raw Data:", request.data)  # Print raw request data
    print("🔹 JSON Payload:", request.get_json())  # Print JSON data


    # Ensure access token is available
    if not ZOHO_ACCESS_TOKEN:
        ZOHO_ACCESS_TOKEN = refresh_access_token()
        if not ZOHO_ACCESS_TOKEN:
            return jsonify({"error": "Failed to authenticate with Zoho"}), 401

    data = request.get_json()
    print("📩 Request Data:", data)
    

    if not data:
        print("❌ No data received!")
        return jsonify({"error": "No data received"}), 400

    # Extract phone number, message, and sender name
    message = data.get("text")
    phone_number = data.get("waId")
    sender_name = data.get("senderName")

    if not phone_number or not message or not sender_name:
        print("❌ Missing required fields!")
        return jsonify({"error": "Missing phone number, message, or sender name"}), 400

    print(f"📩 New Message Received!")
    print(f"💬 Message: {message}")
    print(f"📞 Phone Number: {phone_number}")
    print(f"👤 Sender Name: {sender_name}")

    # Step 1: Check if Contact Exists
    contact_id = search_zoho_contact(phone_number)

    if contact_id:
        # Step 2: Add message to Notes of Existing Contact
        print(f"✅ Contact exists in Bigin (ID: {contact_id}) – Adding message to Notes")
        zoho_response = add_message_to_notes(contact_id, message)
    else:
        # Step 3: Create New Contact
        print(f"🆕 Contact not found – Creating a new contact")
        zoho_response = create_zoho_contact(sender_name, phone_number, message)

    return jsonify({"message": "Webhook received successfully", "zoho_response": zoho_response}), 200

def search_zoho_contact(phone):
    """
    Searches for an existing contact in Zoho Bigin using the phone number.
    """
    headers = {"Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"}

    response = requests.get(ZOHO_BIGIN_SEARCH_URL + phone, headers=headers)

    if response.status_code == 401:  # Token expired, refresh and retry
        print("🔄 Access token expired. Refreshing...")
        refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"
        response = requests.get(ZOHO_BIGIN_SEARCH_URL + phone, headers=headers)

    if response.status_code == 200:
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]["id"]  # Return the existing contact ID

    return None  # Contact not found

def create_zoho_contact(name, phone, description):
    """
    Creates a new contact in Zoho Bigin.
    """
    headers = {
        "Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    contact_data = {
        "data": [{
            "Last_Name": name,
            "Phone": phone,
            "Description": description
        }]
    }

    response = requests.post(ZOHO_BIGIN_CONTACT_URL, json=contact_data, headers=headers)

    if response.status_code == 401:  # Token expired, refresh and retry
        print("🔄 Access token expired. Refreshing...")
        refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"
        response = requests.post(ZOHO_BIGIN_CONTACT_URL, json=contact_data, headers=headers)

    if response.status_code == 201:
        print("✅ New Contact Created Successfully in Zoho Bigin:", response.json())
    else:
        print(f"❌ Failed to Create Contact. Status Code: {response.status_code}, Response: {response.text}")

    return response.json()

def add_message_to_notes(contact_id, message):
    """
    Adds a message to the Notes of an existing contact in Zoho Bigin.
    """
    ZOHO_BIGIN_NOTES_URL = f"https://www.zohoapis.in/bigin/v2/Contacts/{contact_id}/Notes"
    headers = {
        "Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    note_data = {
        "data": [{
            "Parent_Id": contact_id,
            "Note_Title": "WhatsApp Message",
            "Note_Content": message
        }]
    }

    response = requests.post(ZOHO_BIGIN_NOTES_URL, json=note_data, headers=headers)

    if response.status_code == 401:  # Token expired, refresh and retry
        print("🔄 Access token expired. Refreshing...")
        refresh_access_token()
        headers["Authorization"] = f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}"
        response = requests.post(ZOHO_BIGIN_NOTES_URL, json=note_data, headers=headers)

    if response.status_code == 201:
        print("✅ Message Added to Notes Successfully in Zoho Bigin:", response.json())
    else:
        print(f"❌ Failed to Add Message to Notes. Status Code: {response.status_code}, Response: {response.text}")

    return response.json()

if __name__ == "__main__":
    ZOHO_ACCESS_TOKEN = refresh_access_token()  # Get initial access token
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
