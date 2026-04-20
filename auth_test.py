from flask import Flask, redirect, request, jsonify
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
import json
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"

CALENDAR_ID = "209f68fd22e1750a2f0c3205b5d0793b7b1cf608954336b391666da7e4ab623c@group.calendar.google.com"

PARTIFUL_URL = "https://partiful.com/explore/sf"
PARTIFUL_JSON = "partiful.json"

flow = Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri="http://localhost:8080/oauth2callback"
)

# ---------------- AUTH ----------------

def get_credentials():
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return creds
    return None


@app.route("/")
def index():
    creds = get_credentials()

    if creds:
        return "Authenticated. Use /parse-partiful or /import-partiful"

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials

    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    return "Authentication successful."


# ---------------- PARTIFUL LIVE PARSER ----------------

def fetch_partiful_html():
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    response = requests.get(PARTIFUL_URL, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Failed to fetch page: {response.status_code}")

    return response.text


def extract_next_data(html):
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", {"id": "__NEXT_DATA__"})

    if not script:
        raise Exception("No __NEXT_DATA__ found")

    return json.loads(script.string)


def extract_event(event):
    return {
        "id": event.get("id"),
        "title": event.get("title"),
        "description": event.get("description"),
        "start": event.get("startDate"),
        "end": event.get("endDate"),
        "timezone": event.get("timezone") or "America/Los_Angeles",
        "location": " ".join(
            event.get("locationInfo", {})
                 .get("displayAddressLines", [])
        ),
        "url": f"https://partiful.com/e/{event.get('id')}",
    }


def parse_partiful_live():
    html = fetch_partiful_html()
    next_data = extract_next_data(html)

    page = next_data["props"]["pageProps"]
    events = []

    # trending
    for item in page.get("trendingSection", {}).get("items", []):
        if item.get("type") == "event":
            events.append(extract_event(item["event"]))

    # sections
    for section in page.get("sections", []):
        for item in section.get("items", []):
            if item.get("type") == "event":
                events.append(extract_event(item["event"]))

    # save to JSON
    with open(PARTIFUL_JSON, "w") as f:
        json.dump(events, f, indent=2)

    return events


@app.route("/parse-partiful")
def parse_partiful_route():
    events = parse_partiful_live()

    return jsonify({
        "status": "parsed",
        "count": len(events)
    })


# ---------------- GOOGLE CALENDAR IMPORT ----------------

def to_google_event(e):
    return {
        "summary": e["title"],
        "description": f'{e.get("description","")}\n\n{e.get("url","")}',
        "start": {
            "dateTime": e["start"],
            "timeZone": e["timezone"],
        },
        "end": {
            "dateTime": e["end"],
            "timeZone": e["timezone"],
        },
        "location": e.get("location"),
        "extendedProperties": {
            "private": {
                "partiful_key": build_event_key(e),
                "partiful_title": e["title"]
            }
        }
    }


@app.route("/import-partiful")

@app.route("/import-partiful")
def import_partiful():
    creds = get_credentials()
    if not creds:
        return redirect("/")

    if not os.path.exists(PARTIFUL_JSON):
        return {"error": "Run /parse-partiful first"}

    with open(PARTIFUL_JSON, "r") as f:
        events = json.load(f)

    service = build("calendar", "v3", credentials=creds)

    existing_events = fetch_existing_events(service)
    exact_map, title_map = build_event_maps(existing_events)

    inserted = 0
    updated = 0
    skipped = 0

    for e in events:
        try:
            key = build_event_key(e)
            title = build_title_key(e)

            # ✅ CASE 1: exact match → skip
            if key in exact_map:
                skipped += 1
                continue

            # 🔁 CASE 2: same title but different time → update
            if title in title_map:
                existing = title_map[title]

                service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=existing["id"],
                    body=to_google_event(e)
                ).execute()

                updated += 1
                continue

            # ➕ CASE 3: new event → insert
            service.events().insert(
                calendarId=CALENDAR_ID,
                body=to_google_event(e)
            ).execute()

            inserted += 1

        except Exception as ex:
            print("Error:", ex)

    return {
        "status": "done",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped
    }
    
# ---------------- RUN ----------------

def build_event_key(e):
    return f"{e['title']}|{e['start']}|{e['end']}"


def build_title_key(e):
    return e["title"]


def fetch_existing_events(service):
    events = []
    page_token = None

    while True:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            singleEvents=True,
            maxResults=2500,
            pageToken=page_token
        ).execute()

        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return events

def build_event_maps(existing_events):
    exact_map = {}   # full key → event
    title_map = {}   # title → event

    for e in existing_events:
        props = e.get("extendedProperties", {}).get("private", {})

        key = props.get("partiful_key")
        title = props.get("partiful_title")

        if key:
            exact_map[key] = e

        if title:
            title_map[title] = e

    return exact_map, title_map

if __name__ == "__main__":
    app.run(port=8080, debug=True)

