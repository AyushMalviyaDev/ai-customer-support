from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Force Google to show the account picker so you can select the NEW email address
flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="select_account consent")

# Fetch and display the exact authorized email address to confirm
service = build("gmail", "v1", credentials=creds, cache_discovery=False)
user_profile = service.users().getProfile(userId="me").execute()
authorized_email = user_profile.get("emailAddress")

print("\n" + "=" * 60)
print(f"SUCCESSFULLY AUTHORIZED EMAIL: {authorized_email}")
print("=" * 60)
print(f"GOOGLE_CLIENT_ID={creds.client_id}")
print(f"GOOGLE_CLIENT_SECRET={creds.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
print("=" * 60)
print(f"Please copy the GOOGLE_REFRESH_TOKEN above and paste it into Render and your .env file.\n")
