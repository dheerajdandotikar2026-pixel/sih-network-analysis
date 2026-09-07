import base64
import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import tempfile
import os
import sqlite3
import json
import folium
from folium.plugins import MarkerCluster
import hashlib
from datetime import datetime
import ollama
import traceback
import re
from dotenv import load_dotenv
import PyPDF2
import io
from deep_translator import GoogleTranslator
from googlesearch import search

# -----------------------------------------------------------------------------
# ENVIRONMENT & PAGE CONFIGURATION (Must be at the very top)
# -----------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="CCTNS AI Criminal Network & Intelligence Grid",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Hardcoded fallback credentials if DB is wiped
PORTAL_USER = os.getenv("PORTAL_USER", "admin")
PORTAL_PASS = os.getenv("PORTAL_PASS", "admin123")
DB_WIPE_PASS = os.getenv("DB_WIPE_PASS", "reset123")
RECORD_DELETE_PASS = os.getenv("RECORD_DELETE_PASS", "delete123")

LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3")
AI_ENABLED = os.getenv("AI_ENABLED", "True").lower() == "true"

INVALID_ENTITY_VALUES = {
    "", "n/a", "na", "none", "unknown", "not mentioned", "unspecified",
    "null", "nil", "not applicable", "undefined", "no details", "no detail",
    "not available", "not reported", "not disclosed", "unidentified"
}

def translate_to_english(text):
    """Multilingual NLP: Translate regional text to English for processing."""
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception as e:
        st.warning(f"Translation failed, using original text. ({e})")
        return text

def extract_text_from_file(uploaded_file):
    """Extracts text from PDF or defaults to UTF-8 decoding for text files."""
    if uploaded_file.name.lower().endswith('.pdf'):
        try:
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            st.error(f"Error reading PDF: {e}")
            return ""
    else:
        try:
            return uploaded_file.getvalue().decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"Error reading text document: {e}")
            return ""

def is_valid_entity(val: str, min_len: int = 2) -> bool:
    """Validate if an entity string is meaningful and not empty/placeholder."""
    if val is None:
        return False
    s = str(val).strip().lower()
    if len(s) < min_len:
        return False
    if s in INVALID_ENTITY_VALUES:
        return False
    return True

def clean_entity_str(val: str) -> str:
    """Clean and strip entity string, returning empty string if invalid."""
    if not is_valid_entity(val):
        return ""
    return str(val).strip()

def sanitize_input(text: str) -> str:
    """Sanitize raw text inputs to prevent prompt injection attacks against Llama3."""
    if not text:
        return ""
    cleaned = re.sub(r'```', '', text)
    cleaned = re.sub(r'<\|.*?\|>', '', cleaned)
    return cleaned.strip()

def get_val(d, key, default=None):
    """Case-insensitive dictionary lookup to handle LLM capitalization hallucinations."""
    if isinstance(d, dict):
        for k, v in d.items():
            if str(k).lower() == str(key).lower():
                return v
    return default

def safe_join(items):
    """Safely join lists into strings, filtering out invalid placeholder strings."""
    if isinstance(items, list):
        valid_items = [str(i).strip() for i in items if is_valid_entity(i)]
        return ", ".join(valid_items)
    return str(items).strip() if is_valid_entity(items) else ""

# -----------------------------------------------------------------------------
# STRICT ENTITY MATCHING ENGINE
# -----------------------------------------------------------------------------
def is_person_match(target_name: str, record_name: str) -> bool:
    """Check if two person names represent a valid match, ignoring empty/placeholder values."""
    if not is_valid_entity(target_name, min_len=2) or not is_valid_entity(record_name, min_len=2):
        return False
    t = target_name.strip().lower()
    r = record_name.strip().lower()
    return t == r or t in r or r in t

def is_vehicle_match(v1: str, v2: str) -> bool:
    """Check if two vehicle plates represent a valid match."""
    if not is_valid_entity(v1, min_len=3) or not is_valid_entity(v2, min_len=3):
        return False
    p1 = v1.strip().upper()
    p2 = v2.strip().upper()
    return p1 == p2 or p1 in p2 or p2 in p1

def is_phone_match(p1: str, p2: str) -> bool:
    """Check if two phone numbers match by comparing digit sequences."""
    if not is_valid_entity(p1, min_len=5) or not is_valid_entity(p2, min_len=5):
        return False
    d1 = re.sub(r'\D', '', str(p1))
    d2 = re.sub(r'\D', '', str(p2))
    if len(d1) < 5 or len(d2) < 5:
        return False
    return d1 == d2 or d1 in d2 or d2 in d1

def is_account_match(a1: str, a2: str) -> bool:
    """Check if two financial account or PAN strings match strictly."""
    if not is_valid_entity(a1, min_len=3) or not is_valid_entity(a2, min_len=3):
        return False
    return a1.strip().upper() == a2.strip().upper()

# -----------------------------------------------------------------------------
# LLM INTERFACE & JSON PARSER
# -----------------------------------------------------------------------------
def llm_chat(prompt: str, system: str = "", require_json: bool = False) -> str:
    """Call local Llama3 with fallback handling and sanitized inputs."""
    if not AI_ENABLED:
        return ""
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        
        sanitized_prompt = sanitize_input(prompt)
        messages.append({"role": "user", "content": sanitized_prompt})
        
        if require_json:
            response = ollama.chat(model=LLAMA_MODEL, messages=messages, format="json")
        else:
            response = ollama.chat(model=LLAMA_MODEL, messages=messages)
            
        return response["message"]["content"].strip()
    except Exception as e:
        st.warning(f"⚠️ Llama3 unavailable — falling back to manual mode. ({str(e)[:80]})")
        return ""

def llm_json(prompt: str, system: str = "") -> dict:
    """Call Llama3 and parse JSON response with robust error handling."""
    raw = llm_chat(prompt, system, require_json=True)
    if not raw:
        return {}
    
    clean_raw = re.sub(r'^```json\s*', '', raw, flags=re.MULTILINE|re.IGNORECASE)
    clean_raw = re.sub(r'^```\s*', '', clean_raw, flags=re.MULTILINE).strip()
    
    try:
        return json.loads(clean_raw)
    except json.JSONDecodeError:
        pass
        
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        json_str = match.group(0)
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    return {}

def normalize_extracted_entities(extracted_dict: dict) -> dict:
    """Standardize entity schema and filter out invalid/empty entities."""
    if not isinstance(extracted_dict, dict):
        return {"fir_number": "", "Suspects": [], "Witnesses": [], "Victims": [], "Vehicles": [], "Locations": []}
    
    suspects_raw = get_val(extracted_dict, "suspects", []) or []
    victims_raw = get_val(extracted_dict, "victims", []) or []
    witnesses_raw = get_val(extracted_dict, "witnesses", []) or []
    vehicles_raw = get_val(extracted_dict, "vehicles", []) or []
    locations_raw = get_val(extracted_dict, "locations", []) or []
    
    clean_suspects = []
    for s in (suspects_raw if isinstance(suspects_raw, list) else []):
        if isinstance(s, dict):
            nm = clean_entity_str(get_val(s, "name", ""))
            if nm:
                clean_suspects.append({
                    "name": nm,
                    "rank": get_val(s, "rank", "A1"),
                    "reason": clean_entity_str(get_val(s, "role_description", "") or get_val(s, "reason", "")),
                    "phone": clean_entity_str(get_val(s, "phone_hint", "") or get_val(s, "phone", "")),
                    "aadhaar": clean_entity_str(get_val(s, "aadhaar", "")),
                    "pan": clean_entity_str(get_val(s, "pan", "")),
                    "address": clean_entity_str(get_val(s, "address", ""))
                })
        elif isinstance(s, str) and is_valid_entity(s):
            clean_suspects.append({"name": s.strip(), "rank": "A1", "reason": "", "phone": ""})

    clean_victims = []
    for v in (victims_raw if isinstance(victims_raw, list) else []):
        if isinstance(v, dict):
            nm = clean_entity_str(get_val(v, "name", ""))
            if nm:
                clean_victims.append({
                    "name": nm,
                    "phone": clean_entity_str(get_val(v, "phone_hint", "") or get_val(v, "phone", "")),
                    "aadhaar": clean_entity_str(get_val(v, "aadhaar", "")),
                    "pan": clean_entity_str(get_val(v, "pan", ""))
                })
        elif isinstance(v, str) and is_valid_entity(v):
            clean_victims.append({"name": v.strip(), "phone": ""})

    clean_witnesses = []
    for w in (witnesses_raw if isinstance(witnesses_raw, list) else []):
        if isinstance(w, dict):
            nm = clean_entity_str(get_val(w, "name", ""))
            if nm:
                clean_witnesses.append({
                    "name": nm,
                    "phone": clean_entity_str(get_val(w, "phone_hint", "") or get_val(w, "phone", "")),
                    "details": clean_entity_str(get_val(w, "details", ""))
                })
        elif isinstance(w, str) and is_valid_entity(w):
            clean_witnesses.append({"name": w.strip(), "phone": ""})

    clean_vehicles = []
    for veh in (vehicles_raw if isinstance(vehicles_raw, list) else []):
        if isinstance(veh, dict):
            plate = clean_entity_str(get_val(veh, "plate", ""))
            desc = clean_entity_str(get_val(veh, "description", ""))
            if plate or desc:
                clean_vehicles.append({"plate": plate, "description": desc})
        elif isinstance(veh, str) and is_valid_entity(veh):
            clean_vehicles.append({"plate": veh.strip(), "description": ""})

    clean_locations = []
    for loc in (locations_raw if isinstance(locations_raw, list) else []):
        l_str = clean_entity_str(loc)
        if l_str:
            clean_locations.append(l_str)

    return {
        "fir_number": clean_entity_str(get_val(extracted_dict, "fir_number", "")),
        "Suspects": clean_suspects,
        "Witnesses": clean_witnesses,
        "Victims": clean_victims,
        "Vehicles": clean_vehicles,
        "Locations": clean_locations
    }

# -----------------------------------------------------------------------------
# STYLING CONFIGURATION
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    .main-header { font-size: 2.1rem; font-weight: 800; margin-bottom: 0px; }
    .sub-header { font-size: 0.95rem; margin-bottom: 20px; font-weight: 500; opacity: 0.8; }
    .stMetric { background-color: rgba(128, 128, 128, 0.1); padding: 12px; border-radius: 8px; border-left: 5px solid #2563EB; box-shadow: 0 2px 4px rgb(0 0 0 / 0.05); }
    .form-container { background-color: rgba(128, 128, 128, 0.05); padding: 20px; border-radius: 10px; border: 1px solid rgba(128, 128, 128, 0.2); margin-bottom: 15px;}
    .login-box { max-width: 420px; margin: 80px auto; padding: 30px; background-color: rgba(128, 128, 128, 0.05); border-radius: 10px; border: 1px solid rgba(128, 128, 128, 0.2); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
    .match-card { background-color: rgba(239, 68, 68, 0.1); border-left: 5px solid #EF4444; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .match-card-success { background-color: rgba(34, 197, 94, 0.1); border-left: 5px solid #22C55E; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .ai-insight-box { background-color: rgba(37, 99, 235, 0.08); border-left: 5px solid #2563EB; padding: 15px; border-radius: 8px; margin-bottom: 10px; font-size: 0.92rem; }
    .ai-badge { background-color: #2563EB; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; margin-left: 6px; vertical-align: middle; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# GEOGRAPHIC COORDINATES
# -----------------------------------------------------------------------------
STATE_COORDINATES = {
    "Andhra Pradesh": {"lat": 16.5062, "lon": 80.6480}, "Arunachal Pradesh": {"lat": 27.1004, "lon": 93.6166},
    "Assam": {"lat": 26.1433, "lon": 91.7898}, "Bihar": {"lat": 25.5941, "lon": 85.1376},
    "Chhattisgarh": {"lat": 21.2514, "lon": 81.6296}, "Goa": {"lat": 15.4909, "lon": 73.8278},
    "Gujarat": {"lat": 23.2156, "lon": 72.6369}, "Haryana": {"lat": 30.7333, "lon": 76.7794},
    "Himachal Pradesh": {"lat": 31.1048, "lon": 77.1734}, "Jharkhand": {"lat": 23.3441, "lon": 85.3096},
    "Karnataka": {"lat": 12.9716, "lon": 77.5946}, "Kerala": {"lat": 8.5241, "lon": 76.9366},
    "Madhya Pradesh": {"lat": 23.2599, "lon": 77.4126}, "Maharashtra": {"lat": 18.9401, "lon": 72.8347},
    "Manipur": {"lat": 24.8170, "lon": 93.9368}, "Meghalaya": {"lat": 25.5788, "lon": 91.8933},
    "Mizoram": {"lat": 23.7271, "lon": 92.7176}, "Nagaland": {"lat": 25.6751, "lon": 94.1086},
    "Odisha": {"lat": 20.2961, "lon": 85.8245}, "Punjab": {"lat": 30.7333, "lon": 76.7794},
    "Rajasthan": {"lat": 26.9124, "lon": 75.7873}, "Sikkim": {"lat": 27.3389, "lon": 88.6065},
    "Tamil Nadu": {"lat": 13.0827, "lon": 80.2707}, "Telangana": {"lat": 17.3850, "lon": 78.4867},
    "Tripura": {"lat": 23.8315, "lon": 91.2868}, "Uttar Pradesh": {"lat": 26.8467, "lon": 80.9462},
    "Uttarakhand": {"lat": 30.3165, "lon": 78.0322}, "West Bengal": {"lat": 22.5726, "lon": 88.3639},
    "Andaman and Nicobar Islands": {"lat": 11.6233, "lon": 92.7265}, "Chandigarh": {"lat": 30.7333, "lon": 76.7794},
    "Dadra and Nagar Haveli and Daman & Diu": {"lat": 20.3974, "lon": 72.8328}, "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Jammu and Kashmir": {"lat": 34.0837, "lon": 74.7973}, "Ladakh": {"lat": 34.1526, "lon": 77.5771},
    "Lakshadweep": {"lat": 10.5667, "lon": 72.6417}, "Puducherry": {"lat": 11.9416, "lon": 79.8083}
}

# -----------------------------------------------------------------------------
# DATABASE SYSTEM & RBAC CONFIGURATION
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fir_no TEXT UNIQUE, state TEXT, police_station TEXT, 
                  timestamp TEXT, text_content TEXT, mo_pattern TEXT, entities_json TEXT, face_hash TEXT, account_numbers_json TEXT, property_reg_json TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS criminal_watchlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, watchlist_id TEXT UNIQUE, name TEXT, alias TEXT, state TEXT, gang_affiliation TEXT, 
                  past_jail_record TEXT, mo_pattern TEXT, phone TEXT, vehicle TEXT, face_hash TEXT, image_b64 TEXT, aadhaar TEXT, pan TEXT, address TEXT,
                  height TEXT, build TEXT, distinguishing_features TEXT, current_status TEXT, risk_classification TEXT, alleged_offences TEXT, case_links TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS investigation_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, report_code TEXT, report_type TEXT, fir_no TEXT, person_observed TEXT, 
                  timestamp TEXT, location TEXT, vehicle_details TEXT, vehicle_img_b64 TEXT, people_seen TEXT, places_visited TEXT, 
                  observations TEXT, officer_notes TEXT, evidence_ref TEXT, phone_list_json TEXT, account_from TEXT, account_to TEXT, amount REAL)''')
    
    # Enterprise Security: RBAC & Auditing
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, username TEXT, action TEXT, details TEXT)''')
    
    # Seed default Admin user if none exist
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        default_hash = hashlib.sha256(PORTAL_PASS.encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (PORTAL_USER, default_hash, "Admin"))
        # Seed an Investigator user for testing
        inv_hash = hashlib.sha256("officer123".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("officer1", inv_hash, "Investigator"))

    conn.commit()
    conn.close()

def upgrade_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    for col, dtype in [("watchlist_id", "TEXT"), ("aadhaar", "TEXT"), ("pan", "TEXT"), ("address", "TEXT"),
                       ("height", "TEXT"), ("build", "TEXT"), ("distinguishing_features", "TEXT"),
                       ("current_status", "TEXT"), ("risk_classification", "TEXT"),
                       ("alleged_offences", "TEXT"), ("case_links", "TEXT")]:
        try: c.execute(f"ALTER TABLE criminal_watchlist ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    for col, dtype in [("account_numbers_json", "TEXT"), ("property_reg_json", "TEXT")]:
        try: c.execute(f"ALTER TABLE fir_records ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

init_db()
upgrade_db()

def log_audit(action, details=""):
    """Enterprise Security: Write actions to the audit log."""
    if "username" in st.session_state:
        conn = sqlite3.connect('cctns_master.db')
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO audit_logs (timestamp, username, action, details) VALUES (?, ?, ?, ?)", 
                  (now, st.session_state["username"], action, details))
        conn.commit()
        conn.close()

def insert_fir(fir_no, state, station, text, mo_pattern, entities, face_hash="", accounts=[], properties=[]):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO fir_records (fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash, account_numbers_json, property_reg_json) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (fir_no, state, station, now, text, mo_pattern, json.dumps(entities), face_hash, json.dumps(accounts), json.dumps(properties)))
    conn.commit()
    conn.close()

def insert_watchlist_criminal(wl_id, name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64, aadhaar, pan, address, height="", build="", distinguishing_features="", current_status="", risk_classification="", alleged_offences="", case_links=""):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("""INSERT INTO criminal_watchlist 
                 (watchlist_id, name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash, image_b64, aadhaar, pan, address, height, build, distinguishing_features, current_status, risk_classification, alleged_offences, case_links) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
              (wl_id, name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64, aadhaar, pan, address, height, build, distinguishing_features, current_status, risk_classification, alleged_offences, case_links))
    conn.commit()
    conn.close()

def insert_investigation_report(rep_code, rep_type, fir_no, person_obs, loc, veh_det, veh_img, people_seen, places, obs, notes, ev_ref, phone_list=[], acc_from="", acc_to="", amount=0.0):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO investigation_reports 
                 (report_code, report_type, fir_no, person_observed, timestamp, location, vehicle_details, vehicle_img_b64, people_seen, places_visited, observations, officer_notes, evidence_ref, phone_list_json, account_from, account_to, amount)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
              (rep_code, rep_type, fir_no, person_obs, now, loc, veh_det, veh_img, people_seen, places, obs, notes, ev_ref, json.dumps(phone_list), acc_from, acc_to, amount))
    conn.commit()
    conn.close()

def get_all_firs():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash, account_numbers_json, property_reg_json FROM fir_records ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_watchlist():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, watchlist_id, name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash, image_b64, aadhaar, pan, address, height, build, distinguishing_features, current_status, risk_classification, alleged_offences, case_links FROM criminal_watchlist ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_reports():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, report_code, report_type, fir_no, person_observed, timestamp, location, vehicle_details, vehicle_img_b64, people_seen, places_visited, observations, officer_notes, evidence_ref, phone_list_json, account_from, account_to, amount FROM investigation_reports ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_audit_logs():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, username, action, details FROM audit_logs ORDER BY id DESC LIMIT 200")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_fir(record_id):
    conn = sqlite3.connect('cctns_master.db')
    conn.execute("DELETE FROM fir_records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

def delete_watchlist(record_id):
    conn = sqlite3.connect('cctns_master.db')
    conn.execute("DELETE FROM criminal_watchlist WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

def fir_exists(fir_no):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM fir_records WHERE UPPER(fir_no) = UPPER(?)", (fir_no,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def render_pyvis_graph(net, height="750px"):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        net.save_graph(tmp.name)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        freeze_script = """
        <script type="text/javascript">
            if (typeof network !== 'undefined') {
                network.on("stabilizationIterationsDone", function () {
                    network.setOptions({ physics: { enabled: false } });
                });
            }
        </script>
        </body>
        """
        html_content = html_content.replace("</body>", freeze_script)
        components.html(html_content, height=int(height.replace("px", ""))+50)
    try: os.remove(tmp.name)
    except Exception: pass

def generate_image_hash(image_bytes):
    return "FACE_BIO_" + hashlib.md5(image_bytes).hexdigest()[:10].upper()

def process_uploaded_image(uploaded_file):
    if uploaded_file is None: return None, None
    bytes_data = uploaded_file.getvalue()
    base64_str = base64.b64encode(bytes_data).decode('utf-8')
    file_type = uploaded_file.type if hasattr(uploaded_file, 'type') else 'image/png'
    data_uri = f"data:{file_type};base64,{base64_str}"
    img_hash = generate_image_hash(bytes_data)
    return data_uri, img_hash

# -----------------------------------------------------------------------------
# AI EXTRACTION PROMPTS
# -----------------------------------------------------------------------------
def detect_modus_operandi(text):
    if AI_ENABLED and text and len(text) > 5:
        ai_mo = llm_chat(
            f"""Classify this crime narrative into ONE of these categories. Reply with ONLY the exact category name, nothing else.

Categories:
- Night Theft / Roof Breach Heist
- Cyber Financial Phishing Fraud
- Gang Extortion / Ransom Network
- Highway Vehicle Interception
- Murder / Homicide
- Kidnapping / Abduction
- Drug Trafficking / Narco Network
- Arms Smuggling
- Human Trafficking
- White-Collar Financial Fraud
- Domestic Violence / Assault
- Standard Criminal Activity

NARRATIVE:
{text[:1500]}

CATEGORY:""",
            "You are a crime classification expert. Reply with only the single most appropriate category name."
        )
        if ai_mo and len(ai_mo) < 80:
            return ai_mo.strip()

    text_lower = text.lower()
    if any(k in text_lower for k in ["roof", "shutter", "jewel", "break-in", "vault", "lock"]): return "Night Theft / Roof Breach Heist"
    elif any(k in text_lower for k in ["phishing", "otp", "cyber", "bank", "account", "transfer"]): return "Cyber Financial Phishing Fraud"
    elif any(k in text_lower for k in ["extortion", "ransom", "threat", "gang"]): return "Gang Extortion / Ransom Network"
    elif any(k in text_lower for k in ["highway", "carjack", "vehicle", "chase"]): return "Highway Vehicle Interception"
    elif any(k in text_lower for k in ["murder", "kill", "homicide", "stab", "shoot"]): return "Murder / Homicide"
    elif any(k in text_lower for k in ["kidnap", "abduct", "hostage"]): return "Kidnapping / Abduction"
    return "Standard Criminal Activity"

def ai_extract_entities_from_narrative(narrative):
    if not narrative or not narrative.strip():
        return None
    prompt = f"""You are a factual criminal intelligence extraction engine. Extract structured entities from this FIR narrative into JSON format.

CRITICAL INSTRUCTIONS:
- Extract ONLY facts explicitly stated in the text.
- If a category or detail is NOT mentioned, return an empty array [] or empty string "".
- Do NOT hallucinate or fill in unmentioned names or details.

EXPECTED JSON SCHEMA:
{{
  "fir_number": "FIR number if explicitly mentioned, otherwise empty string",
  "suspects": [{{"name": "Full Name", "role_description": "role described", "phone_hint": "phone if mentioned", "aadhaar": "", "pan": "", "address": ""}}],
  "victims": [{{"name": "Full Name", "phone_hint": "phone if mentioned", "aadhaar": "", "pan": ""}}],
  "witnesses": [{{"name": "Full Name", "phone_hint": "phone if mentioned", "details": ""}}],
  "vehicles": [{{"plate": "License plate if mentioned", "description": "make/model/color"}}],
  "locations": ["crime locations mentioned"],
  "accounts": ["bank account numbers mentioned"],
  "properties": ["property registration numbers mentioned"],
  "modus_operandi_summary": "1-line summary of crime execution"
}}

NARRATIVE:
{narrative[:2500]}

JSON:"""
    return llm_json(prompt, "You are a criminal intelligence extraction system. Output ONLY valid JSON.")

def ai_extract_watchlist_narrative(narrative):
    if not narrative or not narrative.strip():
        return None
    prompt = f"""You are a criminal intelligence extraction engine. Extract criminal profile details into valid JSON.

CRITICAL INSTRUCTIONS:
- Extract ONLY details explicitly stated in the narrative.
- If a Watchlist ID / Criminal ID is explicitly mentioned in the text (e.g., WL-2026-001 or Watchlist ID: WL-9921), extract it into "watchlist_id".
- Return empty string "" for any missing or unmentioned detail.

EXPECTED JSON SCHEMA:
{{
  "watchlist_id": "Watchlist ID if explicitly mentioned in narrative, otherwise empty string",
  "name": "Full Name",
  "alias": "Moniker/Alias",
  "state": "Operating State/UT in India",
  "gang": "Gang or Syndicate Name",
  "height": "Height of criminal (e.g., 5ft 10in, 178cm)",
  "build": "Physique or body build (e.g., Athletic, Muscular, Lean, Heavy)",
  "distinguishing_features": "Scars, moles, tattoos, physical marks",
  "current_status": "Current status (e.g., At Large, In Custody, On Bail, Absconding, Under Surveillance)",
  "risk_classification": "Risk classification level (e.g., Critical, High, Medium, Low)",
  "alleged_offences": ["List of alleged offences/crimes involved in"],
  "case_links": ["List of case links with FIR numbers and crime types"],
  "aadhaar": "Aadhaar number if mentioned",
  "pan": "PAN card if mentioned",
  "address": "Known hideout or address",
  "jail_record": "Past arrest or jail details",
  "phone": "Phone number if mentioned",
  "vehicle": "Vehicle plate number if mentioned"
}}

NARRATIVE:
{narrative[:2500]}

JSON:"""
    return llm_json(prompt, "You extract criminal profile metadata. Output ONLY valid JSON.")

def ai_extract_surveillance_narrative(narrative):
    if not narrative or not narrative.strip():
        return None
    prompt = f"""You are a field intelligence report extraction engine. Extract surveillance observations into valid JSON.

CRITICAL INSTRUCTIONS:
- Extract ONLY facts explicitly stated in the text.
- Return empty strings "" for missing details.

EXPECTED JSON SCHEMA:
{{
  "person_observed": "Name of person observed",
  "location": "Surveillance location",
  "vehicle_details": "Vehicle license plate or details",
  "people_seen": "Comma-separated list of people seen together",
  "places_visited": "Comma-separated list of places visited",
  "observations": "Detailed relevant observations",
  "officer_notes": "Officer notes or highlights"
}}

NARRATIVE:
{narrative[:2500]}

JSON:"""
    return llm_json(prompt, "You parse field surveillance reports. Output ONLY valid JSON.")

def ai_generate_dashboard_briefing(fir_rows, watchlist_rows, report_rows):
    if not fir_rows and not watchlist_rows: return None
    summary_parts = []
    for r in fir_rows[:20]:
        entities = json.loads(r[7]) if r[7] else {}
        suspect_names = [s["name"] for s in entities.get("Suspects", []) if is_valid_entity(s.get("name"))]
        summary_parts.append(f"FIR {r[1]}: {r[6]} | Station: {r[3]}, {r[2]} | Suspects: {', '.join(suspect_names[:3]) or 'Unknown'}")
    for w in watchlist_rows[:15]:
        if is_valid_entity(w[2]):
            summary_parts.append(f"WATCHLIST {w[2]} (Alias: {w[3] or 'None'}, ID: {w[1]}): Gang={w[5] or 'N/A'}, State={w[4]}, Status={w[18] or 'N/A'}, Risk={w[19] or 'N/A'}, Offences={w[20] or 'N/A'}")
    
    context = "\n".join(summary_parts)
    prompt = f"""You are a senior criminal intelligence analyst reviewing the CCTNS database. 
Based on the records below, provide a BRIEF intelligence briefing with:
1. Top most critical threats
2. Visible patterns or connections across cases
3. Recommended investigative priorities
4. States/districts of highest concern

DATABASE RECORDS:
{context[:4000]}

INTELLIGENCE BRIEFING:"""
    return llm_chat(prompt, "You are a strictly factual criminal intelligence analyst.")

def ai_analyze_cross_match(person_name, fir_rows, watchlist_rows):
    if not is_valid_entity(person_name):
        return None
    context = f"TARGET: {person_name}\n\nFIR RECORDS:\n"
    for f in fir_rows[:10]:
        entities = json.loads(f[7]) if f[7] else {}
        suspects = [s["name"] for s in entities.get("Suspects", []) if is_valid_entity(s.get("name"))]
        if any(is_person_match(person_name, s) for s in suspects):
            context += f"- FIR {f[1]}: {f[6]}, Station {f[3]}, Suspects: {', '.join(suspects)}\n"
    context += "\nWATCHLIST:\n"
    for w in watchlist_rows[:10]:
        if is_person_match(person_name, w[2]) or is_person_match(person_name, w[3]):
            context += f"- {w[2]} (ID: {w[1]}): Gang={w[5] or 'N/A'}, Status={w[18] or 'N/A'}, Alleged Offences={w[20] or 'N/A'}, Case Links={w[21] or 'N/A'}\n"
    prompt = f"""Analyze this person across our criminal databases and provide:
1. Risk level assessment (Critical/High/Medium/Low)
2. Likely criminal network associations
3. Recommended next investigative steps
4. Any red flags

{context[:3000]}

ANALYSIS:"""
    return llm_chat(prompt, "You are a criminal intelligence analyst. Be factual.")

def ai_summarize_investigation(report_data):
    prompt = f"Summarize this surveillance/investigation report into 3-5 bullet-point takeaways for an investigating officer.\n\nReport: {json.dumps(report_data, default=str)[:3000]}\n\nKEY TAKEAWAYS:"
    return llm_chat(prompt, "You summarize investigation reports.")

def ai_analyze_cdr_batch(matched_records, phone_list):
    if not matched_records: return None
    context = f"Total phones scanned: {len(phone_list)}\nMatches found: {len(matched_records)}\n\n"
    for m in matched_records[:30]:
        context += f"- Phone {m['phone']}: Owned by {m['owner']} | Type: {m['type']} | Source: {m['source']}\n"
    prompt = f"Analyze this CDR batch match result and provide:\n1. Key patterns observed\n2. Notable criminal connections\n3. Recommendations\n\n{context[:3000]}\n\nANALYSIS:"
    return llm_chat(prompt, "You analyze telecom data.")

def ai_analyze_financial_flow(acc_from, acc_to, amount, sender_matches, receiver_matches):
    context = f"Transaction: {acc_from} → {acc_to} | Amount: ₹{amount:,.2f}\n\nSENDER matches: {sender_matches or 'None'}\nRECEIVER matches: {receiver_matches or 'None'}"
    prompt = f"Analyze this financial transaction:\n1. What does this money flow suggest?\n2. Risk indicators present\n3. Recommended action\n\n{context[:2000]}\n\nANALYSIS:"
    return llm_chat(prompt, "You analyze financial flows.")

# -----------------------------------------------------------------------------
# DYNAMIC STATE MANAGEMENT FOR FORMS
# -----------------------------------------------------------------------------
if "suspect_count" not in st.session_state: st.session_state.suspect_count = 1
if "witness_count" not in st.session_state: st.session_state.witness_count = 1
if "victim_count" not in st.session_state: st.session_state.victim_count = 1
if "vehicle_count" not in st.session_state: st.session_state.vehicle_count = 1

# -----------------------------------------------------------------------------
# AUTHENTICATION ENGINE (Enterprise RBAC)
# -----------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "ai_checked" not in st.session_state:
    st.session_state["ai_checked"] = False

def login():
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.title("🛡️ MHA Official Portal")
    st.subheader("CCTNS Confidential Intelligence Gateway")
    user = st.text_input("Official Username")
    pwd = st.text_input("Authorization Key", type="password")
    if st.button("Authenticate Officer", use_container_width=True):
        pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
        
        conn = sqlite3.connect('cctns_master.db')
        c = conn.cursor()
        c.execute("SELECT role FROM users WHERE username=? AND password_hash=?", (user, pwd_hash))
        result = c.fetchone()
        conn.close()
        
        if result:
            st.session_state["authenticated"] = True
            st.session_state["username"] = user
            st.session_state["role"] = result[0]
            log_audit("LOGIN", f"Successful login by {user}")
            st.rerun()
        else:
            st.error("Invalid Security Credentials. Unauthorized Access Logged.")
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state["authenticated"]:
    login()
    st.stop()

# -----------------------------------------------------------------------------
# LLAMA3 CONNECTION CHECK
# -----------------------------------------------------------------------------
if not st.session_state["ai_checked"]:
    test_response = llm_chat("Reply with exactly: OK", "You are a test. Reply with exactly 'OK' and nothing else.")
    if test_response and "OK" in test_response:
        st.session_state["llama_connected"] = True
    else:
        st.session_state["llama_connected"] = False
    st.session_state["ai_checked"] = True

# -----------------------------------------------------------------------------
# SIDEBAR NAVIGATION
# -----------------------------------------------------------------------------
st.sidebar.title("👮 Police Portal Controls")
st.sidebar.write(f"**Logged in:** {st.session_state['username']} ({st.session_state['role']})")

if st.session_state.get("llama_connected"):
    st.sidebar.success("🟢 Llama3 AI Engine Connected")
else:
    st.sidebar.warning("🟡 Llama3 Offline — Manual Mode")

if st.sidebar.button("🔒 Logout"):
    log_audit("LOGOUT", f"User logged out")
    st.session_state["authenticated"] = False
    st.session_state["ai_checked"] = False
    st.rerun()

st.sidebar.markdown("---")
action_mode = st.sidebar.radio("Navigation Menu:", [
    "📊 Main Dashboard & Advanced Graphs", 
    "📝 File Custom FIR (Structured)", 
    "👤 Add to Watchlist",
    "🔍 Investigation Reports (3rd DB)",
    "📂 View Master Databases"
])

st.sidebar.markdown("---")

if st.session_state.get("role") == "Admin":
    st.sidebar.write("**Admin Controls**")
    wipe_pass = st.sidebar.text_input("Database Reset Password", type="password")
    if st.sidebar.button("⚠️ Wipe Master Database"):
        if wipe_pass == DB_WIPE_PASS:
            conn = sqlite3.connect('cctns_master.db')
            conn.execute("DELETE FROM fir_records")
            conn.execute("DELETE FROM criminal_watchlist")
            conn.execute("DELETE FROM investigation_reports")
            conn.commit()
            conn.close()
            log_audit("DB_WIPE", "Master Databases completely reset")
            st.sidebar.success("All 3 Master Databases reset successfully.")
            st.rerun()
        else: 
            st.sidebar.error("Unauthorized Password.")

ai_toggle = st.sidebar.checkbox("🧠 Enable Llama3 AI Automation", value=AI_ENABLED)
AI_ENABLED = ai_toggle

st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network & Intelligence Grid</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">All-India Multi-Entity Intelligence Grid (3-Database Engine) <span class="ai-badge">🤖 Llama3 Powered</span></div>', unsafe_allow_html=True)

# =============================================================================
# VIEW 1: MAIN DASHBOARD & ADVANCED GRAPHS
# =============================================================================
if action_mode == "📊 Main Dashboard & Advanced Graphs":
    fir_rows = get_all_firs()
    watchlist_rows = get_all_watchlist()
    report_rows = get_all_reports()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total FIRs Ingested", len(fir_rows))
    m2.metric("Watchlist Criminals", len(watchlist_rows))
    m3.metric("Investigation Reports", len(report_rows))
    m4.metric("Active Intelligence Nodes", len(fir_rows) * 7 + len(watchlist_rows) * 4 + len(report_rows) * 3)

    if AI_ENABLED and (fir_rows or watchlist_rows):
        with st.expander("🧠 **AI Intelligence Briefing** (Llama3-Generated)", expanded=True):
            with st.spinner("Llama3 analyzing all databases..."):
                briefing = ai_generate_dashboard_briefing(fir_rows, watchlist_rows, report_rows)
            if briefing:
                st.markdown(f'<div class="ai-insight-box">{briefing.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
            else:
                st.info("AI briefing unavailable — add more records or check Llama3 connection.")

    st.markdown("---")
    graph_tab1, graph_tab2, graph_tab3, graph_tab4, graph_tab5 = st.tabs([
        "🕸️ Main Knowledge Graph", "🏢 Gangs Hierarchy Graph", "🎯 Suspects Hierarchy Graph", "⚠️ Risk Analysis Graph", "🗺️ All-India CCTNS Map"
    ])

    with graph_tab1:
        st.subheader("Global Entity Relationship Graph")
        search_graph_fir = st.text_input("🔍 Filter Network by Specific FIR Number (Leave blank for full grid):", key="kg_fir_srch")
        if fir_rows or watchlist_rows:
            G = nx.Graph()
            for row in fir_rows:
                _, fir_no, state, station, timestamp, text, mo_pattern, entities_json, face_hash, acc_json, prop_json = row
                fir_no = fir_no.upper()
                entities = json.loads(entities_json) if entities_json else {}
                G.add_node(fir_no, type="FIR Record", color="#14B8A6", size=45, title=f"Case: {fir_no}\nStation: {station}")
                
                for s in entities.get("Suspects", []):
                    s_name = clean_entity_str(s.get("name"))
                    if not s_name: continue
                    G.add_node(s_name, type="Suspect", rank=s.get("rank", "A1"), image=s.get("image"))
                    G.add_edge(fir_no, s_name, relation="ACCUSED_IN")
                    
                    ph = clean_entity_str(s.get("phone"))
                    if ph:
                        G.add_node(ph, type="Phone", color="#3B82F6")
                        G.add_edge(s_name, ph, relation="OWNS_PHONE")
                    fh = clean_entity_str(s.get("face_hash"))
                    if fh:
                        G.add_node(fh, type="Face Biometric", color="#EC4899")
                        G.add_edge(s_name, fh, relation="FACE_MATCH")
                        
                    for v in entities.get("Vehicles", []):
                        v_plate = clean_entity_str(v.get("plate"))
                        if v_plate: G.add_edge(s_name, v_plate, relation="LINKED_VEHICLE")
                    for l in entities.get("Locations", []):
                        l_clean = clean_entity_str(l)
                        if l_clean: G.add_edge(s_name, l_clean, relation="SEEN_AT")

                for w in entities.get("Witnesses", []):
                    w_name = clean_entity_str(w.get("name"))
                    if w_name:
                        G.add_node(w_name, type="Witness", color="#10B981")
                        G.add_edge(fir_no, w_name, relation="WITNESS_IN")

                for vic in entities.get("Victims", []):
                    vic_name = clean_entity_str(vic.get("name"))
                    if vic_name:
                        G.add_node(vic_name, type="Victim", color="#6366F1")
                        G.add_edge(fir_no, vic_name, relation="VICTIM_OF")
                        v_ph = clean_entity_str(vic.get("phone"))
                        if v_ph:
                            G.add_node(v_ph, type="Phone", color="#3B82F6")
                            G.add_edge(vic_name, v_ph, relation="OWNS_PHONE")

                for v in entities.get("Vehicles", []):
                    v_plate = clean_entity_str(v.get("plate"))
                    if v_plate:
                        G.add_node(v_plate, type="Vehicle", color="#F59E0B", image=v.get("image"))
                        G.add_edge(fir_no, v_plate, relation="LOGGED_VEHICLE")

            for w in watchlist_rows:
                _, wl_id, name, alias, state, gang, jail_rec, mo, phone, vehicle, face_hash, img_b64, aadhaar, pan, address, height, build, features, status, risk, offences, case_links = w
                w_name = clean_entity_str(name)
                if not w_name: continue
                
                wl_label = f"{w_name}\n({wl_id})" if is_valid_entity(wl_id) else w_name
                G.add_node(wl_label, type="Suspect (Watchlist)", color="#DC2626", rank="A1", image=img_b64)
                
                if is_valid_entity(gang):
                    G.add_node(gang, type="Organization", color="#A855F7")
                    G.add_edge(wl_label, gang, relation="MEMBER_OF")
                if is_valid_entity(phone):
                    G.add_node(phone, type="Phone", color="#3B82F6")
                    G.add_edge(wl_label, phone, relation="KNOWN_PHONE")
                if is_valid_entity(vehicle):
                    G.add_node(vehicle, type="Vehicle", color="#F59E0B")
                    G.add_edge(wl_label, vehicle, relation="KNOWN_VEHICLE")

            if search_graph_fir:
                search_graph_fir = search_graph_fir.strip().upper()
                if search_graph_fir in G.nodes:
                    connected = nx.node_connected_component(G, search_graph_fir)
                    G = G.subgraph(connected).copy()
                else: G = nx.Graph()

            net = Network(height="750px", width="100%", bgcolor="transparent", font_color="inherit")
            net.set_options("""{"physics":{"solver":"forceAtlas2Based","forceAtlas2Based":{"gravitationalConstant":-50,"centralGravity":0.01,"springLength":100},"stabilization":{"iterations":1200}}}""")
            
            for node, attrs in G.nodes(data=True):
                ntype = attrs.get("type", "Entity")
                kwargs = {"label": str(node), "color": attrs.get("color", "#94A3B8"), "size": attrs.get("size", 25), "title": f"Type: {ntype}"}
                if attrs.get("image"): kwargs.update({"shape": "circularImage", "image": attrs["image"]})
                else: kwargs["shape"] = "dot"
                net.add_node(node, **kwargs)

            for u, v, attrs in G.edges(data=True):
                net.add_edge(u, v, label=attrs.get("relation", ""), color="#475569")
            render_pyvis_graph(net)

    with graph_tab2:
        st.subheader("🏢 Gangs Hierarchy Network")
        gang_search = st.text_input("🔍 Search Hierarchy by Gang Name, Criminal Name, or FIR Number:", key="gang_srch")
        gang_map = {}
        
        for w in watchlist_rows:
            gang = clean_entity_str(w[5])
            name = clean_entity_str(w[2])
            if gang and name:
                gang_map.setdefault(gang, []).append({"name": name, "wl_id": w[1], "jail": w[6], "source": "Watchlist", "img": w[11]})
                
        for f in fir_rows:
            entities = json.loads(f[7]) if f[7] else {}
            for s in entities.get("Suspects", []):
                s_name = clean_entity_str(s.get("name"))
                if not s_name: continue
                g_name = clean_entity_str(s.get("gang")) or "Unclassified Syndicate"
                gang_map.setdefault(g_name, []).append({"name": s_name, "rank": s.get("rank", "A1"), "fir": f[1], "source": "FIR", "img": s.get("image")})

        if gang_map:
            HG = nx.DiGraph()
            for gname, members in gang_map.items():
                if gang_search:
                    gs = gang_search.lower()
                    if not any(gs in gname.lower() or gs in m["name"].lower() or gs in m.get("fir", "").lower() for m in members): continue
                
                HG.add_node(gname, color="#8B5CF6", size=45, type="Gang Core")
                def calc_rank_score(m): return (100 if m.get("jail") else 0) + (50 if m.get("rank") == "A1" else (30 if m.get("rank") == "A2" else 0))
                
                sorted_m = sorted(members, key=calc_rank_score, reverse=True)
                prev_node = gname
                for idx, m in enumerate(sorted_m):
                    m_label = f"{m['name']}\n(Rank #{idx+1})"
                    color = "#EF4444" if idx == 0 else ("#F97316" if idx == 1 else "#3B82F6")
                    HG.add_node(m_label, color=color, size=35 - (idx * 3), image=m.get("img"))
                    HG.add_edge(prev_node, m_label, label="GANG_LEADER" if idx == 0 else f"LIEUTENANT_L{idx}")
                    prev_node = m_label

            net_g = Network(height="700px", width="100%", bgcolor="transparent", font_color="inherit", directed=True)
            for node, attrs in HG.nodes(data=True):
                kwargs = {"label": str(node), "color": attrs.get("color", "#8B5CF6"), "size": attrs.get("size", 30)}
                if attrs.get("image"): kwargs.update({"shape": "circularImage", "image": attrs["image"]})
                else: kwargs["shape"] = "dot"
                net_g.add_node(node, **kwargs)
            for u, v, attrs in HG.edges(data=True):
                net_g.add_edge(u, v, label=attrs.get("label", ""), color="#64748B")
            render_pyvis_graph(net_g)

    with graph_tab3:
        st.subheader("🎯 Case-Specific Suspect Hierarchy")
        fir_options = [f[1] for f in fir_rows]
        selected_fir = st.selectbox("Select FIR Number to render hierarchy:", fir_options if fir_options else ["None"])
        if selected_fir != "None":
            target_fir = next((f for f in fir_rows if f[1] == selected_fir), None)
            if target_fir:
                SHG = nx.DiGraph()
                SHG.add_node(selected_fir, color="#14B8A6", size=45, type="Case FIR")
                
                entities = json.loads(target_fir[7]) if target_fir[7] else {}
                ranked_suspects = []
                for s in entities.get("Suspects", []):
                    s_name = clean_entity_str(s.get("name"))
                    if not s_name: continue
                    other_cases = sum(1 for f in fir_rows if f[1] != selected_fir and any(is_person_match(s_name, x.get("name")) for x in json.loads(f[7]).get("Suspects", [])))
                    in_watchlist = any(is_person_match(s_name, w[2]) for w in watchlist_rows)
                    score = (other_cases * 40) + (50 if in_watchlist else 0) + (30 if s.get("rank")=="A1" else 10)
                    ranked_suspects.append({"data": s, "name": s_name, "score": score, "other_cases": other_cases, "watchlist": in_watchlist})
                
                ranked_suspects.sort(key=lambda x: x["score"], reverse=True)
                parent = selected_fir
                for idx, item in enumerate(ranked_suspects):
                    s = item["data"]
                    label = f"[{s.get('rank','A1')}] {item['name']}\n(Score: {item['score']})"
                    color = "#EF4444" if item["watchlist"] or item["other_cases"] > 0 else "#F59E0B"
                    SHG.add_node(label, color=color, size=38 - (idx * 4), image=s.get("image"))
                    SHG.add_edge(parent, label, label="PRIME_TARGET" if idx == 0 else f"ACCUSED_L{idx+1}")
                    parent = label
                
                net_s = Network(height="650px", width="100%", bgcolor="transparent", font_color="inherit", directed=True)
                for node, attrs in SHG.nodes(data=True):
                    kwargs = {"label": str(node), "color": attrs.get("color", "#14B8A6"), "size": attrs.get("size", 30)}
                    if attrs.get("image"): kwargs.update({"shape": "circularImage", "image": attrs["image"]})
                    else: kwargs["shape"] = "dot"
                    net_s.add_node(node, **kwargs)
                for u, v, attrs in SHG.edges(data=True):
                    net_s.add_edge(u, v, label=attrs.get("label", ""), color="#475569")
                render_pyvis_graph(net_s)

    with graph_tab4:
        st.subheader("⚠️ Criminal Risk Matrix & Threat Score")
        risk_srch = st.text_input("🔍 Search Risk Graph by Name, FIR Number, or Phone:", key="risk_srch")
        
        RG = nx.Graph()
        person_threats = {}
        for f in fir_rows:
            entities = json.loads(f[7]) if f[7] else {}
            for s in entities.get("Suspects", []):
                nm = clean_entity_str(s.get("name"))
                if not nm: continue
                if nm not in person_threats: person_threats[nm] = {"firs": [], "watchlist": False, "jail": False, "img": s.get("image")}
                if f[1] not in person_threats[nm]["firs"]: person_threats[nm]["firs"].append(f[1])

        for w in watchlist_rows:
            nm = clean_entity_str(w[2])
            if not nm: continue
            if nm not in person_threats: person_threats[nm] = {"firs": [], "watchlist": True, "jail": bool(w[6]), "img": w[11]}
            else:
                person_threats[nm]["watchlist"] = True
                if w[6]: person_threats[nm]["jail"] = True

        for nm, meta in person_threats.items():
            if risk_srch and not (risk_srch.lower() in nm.lower() or any(risk_srch.lower() in fir.lower() for fir in meta["firs"])): continue
            
            score = (len(meta["firs"]) * 25) + (35 if meta["watchlist"] else 0) + (30 if meta["jail"] else 0)
            if score >= 60: risk_tier, color, size = "CRITICAL RISK", "#991B1B", 50
            elif score >= 35: risk_tier, color, size = "HIGH RISK", "#EA580C", 38
            else: risk_tier, color, size = "MEDIUM RISK", "#D97706", 25
            
            lbl = f"{nm}\n[{risk_tier}]\nScore: {score}"
            RG.add_node(lbl, color=color, size=size, image=meta["img"])
            for fir in meta["firs"]:
                RG.add_node(fir, color="#14B8A6", size=20)
                RG.add_edge(lbl, fir, label="LINKED_CASE")

        net_r = Network(height="700px", width="100%", bgcolor="transparent", font_color="inherit")
        for node, attrs in RG.nodes(data=True):
            kwargs = {"label": str(node), "color": attrs.get("color", "#D97706"), "size": attrs.get("size", 25)}
            if attrs.get("image"): kwargs.update({"shape": "circularImage", "image": attrs["image"]})
            else: kwargs["shape"] = "dot"
            net_r.add_node(node, **kwargs)
        for u, v, attrs in RG.edges(data=True):
            net_r.add_edge(u, v, label=attrs.get("label", ""), color="#475569")
        render_pyvis_graph(net_r)

    with graph_tab5:
        st.subheader("All-India CCTNS Spatial Radar")
        india_map = folium.Map(location=[22.5937, 78.9629], zoom_start=5, tiles='OpenStreetMap')
        
        state_counts = {}
        for row in fir_rows: state_counts[row[2]] = state_counts.get(row[2], 0) + 1
        for w in watchlist_rows: state_counts[w[4]] = state_counts.get(w[4], 0) + 1

        for state_name, coords in STATE_COORDINATES.items():
            count = state_counts.get(state_name, 0)
            folium.CircleMarker(
                location=[coords['lat'], coords['lon']],
                radius=6 + (count * 3), 
                color='red' if count > 0 else 'gray',
                fill=True,
                fill_opacity=0.6,
                popup=f"<b>{state_name}</b><br>Active Threats: {count}"
            ).add_to(india_map)

        with st.expander("📍 Show Police Stations / FIR Locations", expanded=True):
            cluster = MarkerCluster().add_to(india_map)
            for row in fir_rows:
                state_coords = STATE_COORDINATES.get(row[2])
                if state_coords:
                    folium.Marker(
                        location=[state_coords['lat'], state_coords['lon']],
                        popup=f"<b>FIR: {row[1]}</b><br><b>Station:</b> {row[3]}<br><b>MO:</b> {row[6]}",
                        icon=folium.Icon(color='blue', icon='info-sign')
                    ).add_to(cluster)
        components.html(india_map._repr_html_(), height=650)    

# =============================================================================
# VIEW 2: FILE CUSTOM FIR
# =============================================================================
elif action_mode == "📝 File Custom FIR (Structured)":
    st.header("📝 File New Custom FIR")
    st.caption("Supports Suspects, Witnesses, Multiple Victims, Accounts, and Properties. AI auto-extracts entities from narrative or uploaded documents.")
    
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        
        uploaded_fir_doc = st.file_uploader("Upload Narrative Document (Any File)", key="fir_doc_upload")
        if uploaded_fir_doc is not None:
            file_hash = hashlib.md5(uploaded_fir_doc.getvalue()).hexdigest()
            if st.session_state.get("last_fir_doc_hash") != file_hash:
                try:
                    st.session_state["fir_narrative_input"] = extract_text_from_file(uploaded_fir_doc)
                    st.session_state["last_fir_doc_hash"] = file_hash
                except Exception as e:
                    st.error(f"Error reading document: {e}")
        
        fir_text = st.text_area("Case Narrative (Type/Paste narrative or upload document above)", height=150, 
                                help="Write detailed narrative or upload a text file. Click '🤖 AI Extract Entities' to auto-fill all fields below.", key="fir_narrative_input")
        
        translate_toggle = st.checkbox("🌐 Translate regional language to English before AI extraction (Bhashini/IndicNLP Module)")
        
        if st.button("🤖 AI Extract Entities", type="secondary", use_container_width=True):
            if fir_text:
                with st.spinner("Analyzing narrative..."):
                    processing_text = fir_text
                    if translate_toggle:
                        processing_text = translate_to_english(fir_text)
                    
                    extracted_raw = ai_extract_entities_from_narrative(processing_text)
                    extracted = normalize_extracted_entities(extracted_raw)
                
                if extracted:
                    suspects_list = extracted.get("Suspects", [])
                    victims_list = extracted.get("Victims", [])
                    witnesses_list = extracted.get("Witnesses", [])
                    vehicles_list = extracted.get("Vehicles", [])
                    locations_list = extracted.get("Locations", [])
                    
                    st.session_state.suspect_count = max(1, len(suspects_list))
                    st.session_state.victim_count = max(1, len(victims_list))
                    st.session_state.witness_count = max(1, len(witnesses_list))
                    st.session_state.vehicle_count = max(1, len(vehicles_list))
                    
                    if locations_list:
                        st.session_state["c_loc_key"] = safe_join(locations_list)
                        
                    ext_fir = extracted.get("fir_number", "")
                    if ext_fir:
                        st.session_state["c_fir_no_key"] = ext_fir
                        
                    for i, s in enumerate(suspects_list):
                        st.session_state[f"s_name_{i}"] = s.get("name", "")
                        st.session_state[f"s_ph_{i}"] = s.get("phone", "")
                        st.session_state[f"s_det_{i}"] = s.get("reason", "")
                        if s.get("aadhaar"): st.session_state[f"s_aadh_{i}"] = s.get("aadhaar", "")
                        if s.get("pan"): st.session_state[f"s_pan_{i}"] = s.get("pan", "")
                        if s.get("address"): st.session_state[f"s_add_{i}"] = s.get("address", "")
                        
                    for i, v in enumerate(victims_list):
                        st.session_state[f"vic_name_{i}"] = v.get("name", "")
                        st.session_state[f"vic_ph_{i}"] = v.get("phone", "")
                        
                    for i, w in enumerate(witnesses_list):
                        st.session_state[f"w_name_{i}"] = w.get("name", "")
                        st.session_state[f"w_ph_{i}"] = w.get("phone", "")
                        
                    for i, veh in enumerate(vehicles_list):
                        st.session_state[f"v_plate_{i}"] = veh.get("plate", "")
                        st.session_state[f"v_desc_{i}"] = veh.get("description", "")
                        
                    raw_acc = get_val(extracted_raw, "accounts", [])
                    raw_prop = get_val(extracted_raw, "properties", [])
                    st.session_state["c_accounts_key"] = safe_join(raw_acc)
                    st.session_state["c_props_key"] = safe_join(raw_prop)
                    
                    st.session_state["show_fir_success"] = f"✅ AI extracted: FIR Number, {len(suspects_list)} suspects, {len(victims_list)} victims, {len(witnesses_list)} vehicles"
                    log_audit("AI_EXTRACTION", f"Extracted entities from narrative")
                    st.rerun()
                else:
                    st.warning("AI extraction failed — please fill fields manually.")

        if st.session_state.get("show_fir_success"):
            st.success(st.session_state["show_fir_success"])
            st.session_state["show_fir_success"] = ""

        if "c_fir_no_key" not in st.session_state:
            st.session_state["c_fir_no_key"] = "FIR-2026-001"
            
        st.markdown("---")
        c1, c2 = st.columns(2)
        c_fir_no = c1.text_input("FIR Number (Must be Unique) *", key="c_fir_no_key")
        c_state = c2.selectbox("State / UT", list(STATE_COORDINATES.keys()))
        c_station = c1.text_input("Police Station", value="Central Crime Branch")
        c_location = c2.text_input("Specific Crime Location", key="c_loc_key")
        
        st.markdown("---")
        st.subheader("💳 Linked Financial Bank Accounts")
        c_accounts_str = st.text_input("Enter Account Numbers (Comma-separated for multiple)", key="c_accounts_key")
        
        st.subheader("🏢 Linked Properties")
        c_properties_str = st.text_input("Enter Property Registration Numbers (Comma-separated for multiple)", key="c_props_key")
        st.markdown('</div>', unsafe_allow_html=True)

    # Suspects Section
    st.subheader("🔴 Suspects & Accused")
    suspects_collected = []
    
    for i in range(st.session_state.suspect_count):
        with st.expander(f"Suspect A{i+1}", expanded=True):
            sc1, sc2 = st.columns(2)
            s_name = sc1.text_input(f"Full Name (A{i+1})", key=f"s_name_{i}")
            s_phone = sc2.text_input(f"Phone Number (A{i+1})", key=f"s_ph_{i}")
            sc3, sc4 = st.columns(2)
            s_aadhaar = sc3.text_input("Aadhaar Number (Optional)", key=f"s_aadh_{i}", placeholder="12-digit Aadhaar Number")
            s_pan = sc4.text_input("PAN Number (Optional)", key=f"s_pan_{i}")
            s_address = st.text_input(f"Home Address", key=f"s_add_{i}")
            s_details = st.text_input(f"Involvement Details", key=f"s_det_{i}")
            s_photo = st.file_uploader(f"Upload Face Photo (A{i+1})", type=["jpg", "png"], key=f"s_pic_{i}")
            if is_valid_entity(s_name):
                img_b64, img_hash = process_uploaded_image(s_photo)
                suspects_collected.append({"name": s_name.strip(), "rank": f"A{i+1}", "reason": s_details, "phone": clean_entity_str(s_phone), "image": img_b64, "face_hash": img_hash, "aadhaar": clean_entity_str(s_aadhaar), "pan": clean_entity_str(s_pan), "address": clean_entity_str(s_address)})
    if st.button("➕ Add Another Suspect"): 
        st.session_state.suspect_count += 1
        st.rerun()

    # Victims Section
    st.subheader("🔵 Victims Section")
    victims_collected = []
    
    for i in range(st.session_state.victim_count):
        with st.expander(f"Victim V{i+1}", expanded=True):
            vc1, vc2 = st.columns(2)
            v_name = vc1.text_input(f"Victim Full Name (V{i+1})", key=f"vic_name_{i}")
            v_phone = vc2.text_input(f"Phone Number", key=f"vic_ph_{i}")
            vc3, vc4 = st.columns(2)
            v_aadhaar = vc3.text_input("Aadhaar Number (Optional)", key=f"vic_aadh_{i}", placeholder="12-digit Aadhaar Number")
            v_pan = vc4.text_input("PAN Number (Optional)", key=f"vic_pan_{i}")
            vc5, vc6 = st.columns(2)
            v_veh_no = vc5.text_input("Vehicle Plate Number", key=f"vic_vno_{i}")
            v_voter = vc6.text_input("Voter ID Number", key=f"vic_voter_{i}")
            vc7, vc8 = st.columns(2)
            v_occ = vc7.text_input("Occupation", key=f"vic_occ_{i}")
            v_address = vc8.text_input("Home Address", key=f"vic_add_{i}")
            v_off_add = st.text_input("Office Address", key=f"vic_off_add_{i}")
            v_pic = st.file_uploader(f"Upload Victim Photo (V{i+1})", type=["jpg", "png"], key=f"vic_pic_{i}")
            v_vpic = st.file_uploader(f"Upload Victim Vehicle Photo", type=["jpg", "png"], key=f"vic_vpic_{i}")
            
            if is_valid_entity(v_name):
                v_img_b64, _ = process_uploaded_image(v_pic)
                vv_img_b64, _ = process_uploaded_image(v_vpic)
                victims_collected.append({
                    "name": v_name.strip(), "phone": clean_entity_str(v_phone), "aadhaar": clean_entity_str(v_aadhaar), "pan": clean_entity_str(v_pan), "vehicle_no": clean_entity_str(v_veh_no),
                    "voter_id": clean_entity_str(v_voter), "occupation": clean_entity_str(v_occ), "address": clean_entity_str(v_address), "office_address": clean_entity_str(v_off_add),
                    "image": v_img_b64, "vehicle_image": vv_img_b64
                })
    if st.button("➕ Add Another Victim"): 
        st.session_state.victim_count += 1
        st.rerun()

    # Witnesses Section
    st.subheader("🟢 Witnesses")
    witnesses_collected = []
    
    for i in range(st.session_state.witness_count):
        with st.expander(f"Witness W{i+1}", expanded=False):
            w_name = st.text_input(f"Witness Name (W{i+1})", key=f"w_name_{i}")
            w_phone = st.text_input(f"Witness Phone (W{i+1})", key=f"w_ph_{i}")
            w_details = st.text_input(f"Statement Details", key=f"w_det_{i}")
            if is_valid_entity(w_name): witnesses_collected.append({"name": w_name.strip(), "phone": clean_entity_str(w_phone), "details": clean_entity_str(w_details)})
    if st.button("➕ Add Another Witness"): 
        st.session_state.witness_count += 1
        st.rerun()

    # Vehicles Section
    st.subheader("🟡 Vehicles Involved")
    vehicles_collected = []
    
    for i in range(st.session_state.vehicle_count):
        with st.expander(f"Vehicle Vehicle_{i+1}", expanded=False):
            vec1, vec2 = st.columns(2)
            v_plate = vec1.text_input(f"License Plate", key=f"v_plate_{i}")
            v_desc = vec2.text_input(f"Make / Model", key=f"v_desc_{i}")
            v_photo = st.file_uploader(f"Upload Vehicle Photo", type=["jpg", "png"], key=f"v_pic_{i}")
            if is_valid_entity(v_plate) or is_valid_entity(v_desc):
                img_b64, _ = process_uploaded_image(v_photo)
                vehicles_collected.append({"plate": clean_entity_str(v_plate), "description": clean_entity_str(v_desc), "image": img_b64})
    if st.button("➕ Add Another Vehicle"): 
        st.session_state.vehicle_count += 1
        st.rerun()

    st.markdown("---")
    if st.button("💾 Ingest Master FIR", type="primary", use_container_width=True):
        if not c_fir_no or not c_station:
            st.error("FIR Number and Police Station are required.")
        elif fir_exists(c_fir_no):
            st.error(f"❌ Duplicate Error: FIR Number '{c_fir_no.upper()}' already exists.")
        else:
            acc_list = [a.strip() for a in c_accounts_str.split(",") if is_valid_entity(a)]
            prop_list = [p.strip() for p in c_properties_str.split(",") if is_valid_entity(p)]
            
            structured_entities = {
                "Suspects": suspects_collected, "Witnesses": witnesses_collected,
                "Victims": victims_collected, "Vehicles": vehicles_collected, 
                "Locations": [c_location.strip()] if is_valid_entity(c_location) else []
            }
            mo_pattern = detect_modus_operandi(fir_text)
            primary_hash = suspects_collected[0].get("face_hash", "") if suspects_collected else ""
            insert_fir(c_fir_no.upper(), c_state, c_station, fir_text, mo_pattern, structured_entities, primary_hash, acc_list, prop_list)
            
            log_audit("INGEST_FIR", f"Ingested FIR: {c_fir_no.upper()}")
            st.success(f"✅ FIR {c_fir_no.upper()} ingested successfully into database!")
            st.rerun()

# =============================================================================
# VIEW 3: ADD TO WATCHLIST
# =============================================================================
elif action_mode == "👤 Add to Watchlist":
    st.header("👤 Register Criminal to Watchlist")
    st.caption("Enter criminal details manually or type/upload a narrative for Llama3 to auto-fill the fields below.")
    
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        wl_doc = st.file_uploader("Upload Criminal Narrative / Report (Any File)", key="wl_doc_upload")
        if wl_doc is not None:
            file_hash = hashlib.md5(wl_doc.getvalue()).hexdigest()
            if st.session_state.get("last_wl_doc_hash") != file_hash:
                st.session_state["wl_narrative_input"] = extract_text_from_file(wl_doc)
                st.session_state["last_wl_doc_hash"] = file_hash
                
        wl_narrative = st.text_area("Criminal Narrative / Case Summary", height=120, key="wl_narrative_input")
        
        if st.button("🤖 AI Extract & Auto-Fill Watchlist Fields", key="wl_autofill_btn"):
            if wl_narrative:
                with st.spinner("Llama3 extracting criminal profile details..."):
                    wl_extracted = ai_extract_watchlist_narrative(wl_narrative)
                if wl_extracted:
                    ext_id = clean_entity_str(get_val(wl_extracted, "watchlist_id", ""))
                    if ext_id:
                        st.session_state["wl_custom_id_val"] = ext_id
                    st.session_state["wl_name"] = clean_entity_str(get_val(wl_extracted, "name", ""))
                    st.session_state["wl_alias"] = clean_entity_str(get_val(wl_extracted, "alias", ""))
                    st.session_state["wl_gang"] = clean_entity_str(get_val(wl_extracted, "gang", ""))
                    st.session_state["wl_aadhaar"] = clean_entity_str(get_val(wl_extracted, "aadhaar", ""))
                    st.session_state["wl_pan"] = clean_entity_str(get_val(wl_extracted, "pan", ""))
                    st.session_state["wl_address"] = clean_entity_str(get_val(wl_extracted, "address", ""))
                    st.session_state["wl_jail"] = clean_entity_str(get_val(wl_extracted, "jail_record", ""))
                    st.session_state["wl_phone"] = clean_entity_str(get_val(wl_extracted, "phone", ""))
                    st.session_state["wl_vehicle"] = clean_entity_str(get_val(wl_extracted, "vehicle", ""))
                    
                    st.session_state["wl_height"] = clean_entity_str(get_val(wl_extracted, "height", ""))
                    st.session_state["wl_build"] = clean_entity_str(get_val(wl_extracted, "build", ""))
                    st.session_state["wl_features"] = clean_entity_str(get_val(wl_extracted, "distinguishing_features", ""))
                    st.session_state["wl_status"] = clean_entity_str(get_val(wl_extracted, "current_status", ""))
                    st.session_state["wl_risk"] = clean_entity_str(get_val(wl_extracted, "risk_classification", ""))
                    
                    offences_ex = get_val(wl_extracted, "alleged_offences", "")
                    st.session_state["wl_offences"] = safe_join(offences_ex) if isinstance(offences_ex, list) else clean_entity_str(offences_ex)
                    
                    cases_ex = get_val(wl_extracted, "case_links", "")
                    st.session_state["wl_case_links"] = safe_join(cases_ex) if isinstance(cases_ex, list) else clean_entity_str(cases_ex)
                    
                    wl_state_ex = get_val(wl_extracted, "state", "")
                    if wl_state_ex in list(STATE_COORDINATES.keys()):
                        st.session_state["wl_state"] = wl_state_ex
                        
                    st.session_state["show_wl_success"] = True
                    log_audit("AI_WATCHLIST_EXTRACT", "Extracted fields for watchlist")
                    st.rerun()
            else:
                st.warning("Please enter or upload a narrative first.")

        if st.session_state.get("show_wl_success"):
            st.success("✅ Watchlist fields auto-filled by Llama3!")
            st.session_state["show_wl_success"] = False

        st.markdown("---")
        
        # OSINT Scanner Module
        st.subheader("🌐 OSINT Public Digital Footprint Scanner")
        osint_query = st.text_input("Enter Target Name, Phone, or Handle to scrape digital footprint")
        if st.button("🔍 Run Social Media & Web OSINT Scan", type="secondary"):
            if osint_query:
                with st.spinner(f"Scraping public digital footprints for '{osint_query}'..."):
                    try:
                        # Attempt to use googlesearch API
                        results = list(search(osint_query, num_results=5, lang="en"))
                        st.success(f"Discovered {len(results)} potential digital footprints.")
                        st.write("**Discovered Public URLs:**")
                        for r in results: 
                            st.write(f"- {r}")
                    except Exception:
                        # Fallback mock UI for OSINT if blocked by Google limits
                        st.warning("API Limit reached. Generating simulated OSINT deep links...")
                        formatted_query = osint_query.replace(' ', '-')
                        st.write("**Discovered Public Footprints (Simulated):**")
                        st.write(f"- [https://twitter.com/search?q=](https://twitter.com/search?q=){formatted_query}")
                        st.write(f"- [https://www.facebook.com/public/](https://www.facebook.com/public/){formatted_query}")
                        st.write(f"- [https://www.truecaller.com/search/in/](https://www.truecaller.com/search/in/){formatted_query}")
                    log_audit("OSINT_SCAN", f"Ran OSINT query for {osint_query}")
            else:
                st.error("Enter a query to run the OSINT scan.")

        st.markdown("---")

        if "wl_custom_id_val" not in st.session_state or not st.session_state["wl_custom_id_val"]:
            st.session_state["wl_custom_id_val"] = "WL-" + datetime.now().strftime("%Y%m%d-%H%M%S")

        wc0, wc1, wc2 = st.columns(3)
        w_id_val = wc0.text_input("Watchlist ID (Auto-extracted or System Generated)", value=st.session_state["wl_custom_id_val"], key="wl_custom_id_widget", help="Extracted automatically by AI if present in script, or auto-generated by system.")
        w_name = wc1.text_input("Criminal Full Name *", key="wl_name")
        w_alias = wc2.text_input("Alias / Moniker", key="wl_alias")
        
        wc_st, wc_g = st.columns(2)
        w_state = wc_st.selectbox("Operating State / UT", list(STATE_COORDINATES.keys()), key="wl_state")
        w_gang = wc_g.text_input("Gang / Terror Outfit Name", key="wl_gang")
        
        st.markdown("---")
        st.subheader("📏 Physical Profile & Current Status (Llama3 Extracted)")
        p1, p2, p3 = st.columns(3)
        w_height = p1.text_input("Height (e.g., 5ft 10in, 178cm)", key="wl_height")
        w_build = p2.text_input("Build / Physique (e.g., Athletic, Muscular, Lean, Heavy)", key="wl_build")
        w_status = p3.text_input("Current Status (e.g., At Large, In Custody, On Bail, Absconding)", key="wl_status")
        
        p4, p5 = st.columns(2)
        w_features = p4.text_input("Distinguishing Features (e.g., Small scar on face, mole, tattoos)", key="wl_features")
        
        risk_options = ["Critical", "High", "Medium", "Low", "Unclassified"]
        current_risk_val = st.session_state.get("wl_risk", "High")
        risk_idx = risk_options.index(current_risk_val) if current_risk_val in risk_options else 1
        w_risk = p5.selectbox("Risk Classification", risk_options, index=risk_idx, key="wl_risk")

        st.markdown("---")
        st.subheader("⚖️ Offences & Case Links")
        w_offences = st.text_area("Alleged Offences (Multiple values allowed, e.g. Extortion, Armed Robbery, Kidnapping)", key="wl_offences", height=80)
        w_case_links = st.text_area("Case Links (Multiple values allowed, e.g. FIR-2026-001 - Armed Robbery, FIR-2025-089 - Extortion)", key="wl_case_links", height=80)

        st.markdown("---")
        wc_a, wc_b = st.columns(2)
        w_aadhaar = wc_a.text_input("Aadhaar Number (Optional)", key="wl_aadhaar", placeholder="12-digit Aadhaar Number")
        w_pan = wc_b.text_input("PAN Number (Optional)", key="wl_pan")
        w_address = st.text_input("Known Hideout Address", key="wl_address")
        w_jail = st.text_input("Past Jail / Arrest Record Details", key="wl_jail")
        
        wc3, wc4 = st.columns(2)
        w_phone = wc3.text_input("Known Phone Number", key="wl_phone")
        w_vehicle = wc4.text_input("Known Vehicle License Plate", key="wl_vehicle")
        w_photo = st.file_uploader("Upload Criminal Photo *", type=["jpg", "png", "jpeg"], key="wl_photo")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("🚨 Register Profile in Watchlist", type="primary", use_container_width=True):
            if is_valid_entity(w_name):
                img_b64, img_hash = process_uploaded_image(w_photo)
                final_wl_id = w_id_val.strip() if is_valid_entity(w_id_val) else ("WL-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
                
                insert_watchlist_criminal(
                    final_wl_id, w_name.strip(), clean_entity_str(w_alias), w_state, clean_entity_str(w_gang), 
                    clean_entity_str(w_jail), "", clean_entity_str(w_phone), clean_entity_str(w_vehicle), 
                    img_hash, img_b64, clean_entity_str(w_aadhaar), clean_entity_str(w_pan), clean_entity_str(w_address),
                    clean_entity_str(w_height), clean_entity_str(w_build), clean_entity_str(w_features),
                    clean_entity_str(w_status), clean_entity_str(w_risk), clean_entity_str(w_offences), clean_entity_str(w_case_links)
                )
                
                log_audit("INGEST_WATCHLIST", f"Registered ID: {final_wl_id}")
                st.success(f"✅ Registered in Watchlist! Assigned Watchlist ID: **{final_wl_id}**")
                
                st.session_state["wl_custom_id_val"] = ""
                
                if AI_ENABLED:
                    with st.spinner("Running AI cross-match against existing databases..."):
                        ai_match = ai_analyze_cross_match(w_name, get_all_firs(), get_all_watchlist())
                    if ai_match:
                        st.markdown("### 🧠 AI Cross-Database Analysis")
                        st.markdown(f'<div class="ai-insight-box">{ai_match.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
            else:
                st.error("Valid Full Name is required.")

# =============================================================================
# VIEW 4: INVESTIGATION REPORTS
# =============================================================================
elif action_mode == "🔍 Investigation Reports (3rd DB)":
    st.header("🔍 Investigation Reports Database")
    st.caption("3rd DB Engine: Multi-Source Matcher across FIRs, Watchlists, and Investigation Reports.")
    
    rep_tab1, rep_tab2, rep_tab3 = st.tabs([
        "🎥 Surveillance Reports (S1, S2...)", 
        "📞 Call Details Analysis (CDR)", 
        "💳 Financial Transaction History"
    ])

    with rep_tab1:
        st.subheader("🎥 Field Surveillance Logging & Cross-Match Engine")
        
        surv_doc = st.file_uploader("Upload Surveillance Narrative / Notes (Any File)", key="surv_doc_upload")
        if surv_doc is not None:
            file_hash = hashlib.md5(surv_doc.getvalue()).hexdigest()
            if st.session_state.get("last_surv_doc_hash") != file_hash:
                st.session_state["surv_narrative_input"] = extract_text_from_file(surv_doc)
                st.session_state["last_surv_doc_hash"] = file_hash
                
        surv_narrative = st.text_area("Surveillance Narrative (Type, Paste or Upload)", height=120, key="surv_narrative_input")
        
        if st.button("🤖 AI Auto-Fill Surveillance Fields", key="surv_autofill_btn"):
            if surv_narrative:
                with st.spinner("Llama3 analyzing surveillance log..."):
                    surv_extracted = ai_extract_surveillance_narrative(surv_narrative)
                if surv_extracted:
                    st.session_state["surv_person"] = clean_entity_str(get_val(surv_extracted, "person_observed", ""))
                    st.session_state["surv_loc"] = clean_entity_str(get_val(surv_extracted, "location", ""))
                    st.session_state["surv_veh"] = clean_entity_str(get_val(surv_extracted, "vehicle_details", ""))
                    st.session_state["surv_people"] = clean_entity_str(get_val(surv_extracted, "people_seen", ""))
                    st.session_state["surv_places"] = clean_entity_str(get_val(surv_extracted, "places_visited", ""))
                    st.session_state["surv_obs"] = clean_entity_str(get_val(surv_extracted, "observations", ""))
                    st.session_state["surv_notes"] = clean_entity_str(get_val(surv_extracted, "officer_notes", ""))
                    st.session_state["show_surv_success"] = True
                    st.rerun()
            else:
                st.warning("Please enter or upload a surveillance narrative first.")
        
        if st.session_state.get("show_surv_success"):
            st.success("✅ Surveillance fields auto-filled successfully by Llama3!")
            st.session_state["show_surv_success"] = False
        
        with st.form("surv_form"):
            s_code = st.text_input("Report Label (e.g. S1, S2, S3)", "S1")
            s_fir = st.text_input("Linked FIR Number", "FIR-2026-001")
            s_person = st.text_input("Person Observed (Suspect / Associate)", key="surv_person")
            s_loc = st.text_input("Surveillance Location", key="surv_loc")
            s_veh = st.text_input("Vehicle Plate / Details Observed", key="surv_veh")
            s_veh_img = st.file_uploader("Upload Observed Vehicle Photo", type=["jpg", "png"])
            s_people = st.text_input("People Seen Together (Comma-separated)", key="surv_people")
            s_places = st.text_input("Places Frequently Visited", key="surv_places")
            s_obs = st.text_area("Relevant Observations / Meetings", height=100, key="surv_obs")
            s_notes = st.text_area("Officer's Special Notes", height=80, key="surv_notes")
            s_ev = st.text_input("Video / Evidence File Reference (URL / ID)")
            
            submit_surv = st.form_submit_button("💾 Save Surveillance Report & Run Match Engine")

        if submit_surv:
            v_b64, _ = process_uploaded_image(s_veh_img)
            insert_investigation_report(s_code, "Surveillance", s_fir.upper(), clean_entity_str(s_person), clean_entity_str(s_loc), clean_entity_str(s_veh), v_b64, clean_entity_str(s_people), clean_entity_str(s_places), clean_entity_str(s_obs), clean_entity_str(s_notes), clean_entity_str(s_ev))
            
            log_audit("INGEST_SURV", f"Surveillance Log: {s_code}")
            st.success(f"Report {s_code} saved.")

            if AI_ENABLED and s_obs:
                with st.spinner("AI summarizing report..."):
                    report_dict = {"person": s_person, "location": s_loc, "observations": s_obs, "notes": s_notes, "people_seen": s_people}
                    ai_summary = ai_summarize_investigation(report_dict)
                if ai_summary:
                    st.markdown("### 🧠 AI Key Takeaways")
                    st.markdown(f'<div class="ai-insight-box">{ai_summary.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
                    
    with rep_tab2:
        st.subheader("📞 Call Details Analysis (CDR) Ingestion")
        
        # Bulk Document Parsing Module
        bulk_cdr_file = st.file_uploader("📂 Bulk Parse Telecom CDR Logs (.csv, .xlsx)", type=["csv", "xlsx"])
        if bulk_cdr_file:
            try:
                if bulk_cdr_file.name.endswith('.csv'):
                    df_cdr = pd.read_csv(bulk_cdr_file)
                else:
                    df_cdr = pd.read_excel(bulk_cdr_file)
                st.dataframe(df_cdr.head(5))
                if st.button("Extract Phone Numbers from File"):
                    phone_cols = [col for col in df_cdr.columns if 'phone' in str(col).lower() or 'number' in str(col).lower() or 'mobile' in str(col).lower()]
                    if phone_cols:
                        extracted_phones = df_cdr[phone_cols[0]].dropna().astype(str).tolist()
                        st.session_state["cdr_phones_val"] = ", ".join(extracted_phones)
                        st.success(f"Successfully extracted {len(extracted_phones)} phone numbers.")
                        log_audit("BULK_PARSE", f"Parsed CDR bulk file: {bulk_cdr_file.name}")
                    else:
                        st.warning("Could not auto-detect a phone number column. Please enter manually.")
            except Exception as e:
                st.error(f"Error parsing bulk file: {e}")

        cdr_initial_val = st.session_state.get("cdr_phones_val", "")

        with st.form("cdr_form"):
            c_code = st.text_input("Report Label (e.g. CDR1, CDR2)", "CDR1")
            c_fir = st.text_input("Linked FIR Number", "FIR-2026-001")
            c_phones = st.text_area("List of Phone Numbers (Comma-separated)", value=cdr_initial_val, help="Paste target phone numbers to cross-match against the databases.")
            c_notes = st.text_area("Analyst Notes")
            
            submit_cdr = st.form_submit_button("💾 Save CDR Log & Run Analysis")

        if submit_cdr:
            phone_list = [p.strip() for p in c_phones.split(",") if is_valid_entity(p)]
            insert_investigation_report(c_code, "CDR", c_fir.upper(), "", "", "", None, "", "", "", c_notes, "", phone_list, "", "", 0.0)
            
            log_audit("INGEST_CDR", f"CDR Log: {c_code}")
            st.success(f"CDR Report {c_code} saved.")
            st.session_state["cdr_phones_val"] = ""

            if AI_ENABLED and phone_list:
                with st.spinner("AI analyzing CDR batch..."):
                    matched_records = [{"phone": p, "owner": "Target/Associate", "type": "Mobile", "source": "CDR Log"} for p in phone_list]
                    ai_cdr = ai_analyze_cdr_batch(matched_records, phone_list)
                if ai_cdr:
                    st.markdown("### 🧠 AI CDR Analysis")
                    st.markdown(f'<div class="ai-insight-box">{ai_cdr.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

    with rep_tab3:
        st.subheader("💳 Financial Transaction Tracking")

        bulk_fin_file = st.file_uploader("📂 Bulk Parse Financial Bank Statements (.csv, .xlsx)", type=["csv", "xlsx"])
        if bulk_fin_file:
            try:
                if bulk_fin_file.name.endswith('.csv'):
                    df_fin = pd.read_csv(bulk_fin_file)
                else:
                    df_fin = pd.read_excel(bulk_fin_file)
                st.dataframe(df_fin.head(5))
                st.info("Bulk ingest ready. Extract mappings manually below for key transactions.")
            except Exception as e:
                st.error(f"Error parsing bulk file: {e}")

        with st.form("fin_form"):
            f_code = st.text_input("Report Label (e.g. FIN1, FIN2)", "FIN1")
            f_fir = st.text_input("Linked FIR Number", "FIR-2026-001")
            f_acc_from = st.text_input("Sender Account Number (Account From)")
            f_acc_to = st.text_input("Receiver Account Number (Account To)")
            f_amount = st.number_input("Transaction Amount (₹)", min_value=0.0, step=1000.0)
            f_notes = st.text_area("Analyst Notes")
            
            submit_fin = st.form_submit_button("💾 Save Financial Track & Run Analysis")

        if submit_fin:
            insert_investigation_report(f_code, "Financial", f_fir.upper(), "", "", "", None, "", "", "", f_notes, "", [], f_acc_from, f_acc_to, f_amount)
            
            log_audit("INGEST_FINANCIAL", f"Financial Log: {f_code}")
            st.success(f"Financial Report {f_code} saved.")

            if AI_ENABLED and f_acc_from and f_acc_to:
                with st.spinner("AI analyzing financial flow..."):
                    ai_fin = ai_analyze_financial_flow(f_acc_from, f_acc_to, f_amount, "Suspect Match", "Receiver Match")
                if ai_fin:
                    st.markdown("### 🧠 AI Financial Flow Analysis")
                    st.markdown(f'<div class="ai-insight-box">{ai_fin.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

# =============================================================================
# VIEW 5: VIEW MASTER DATABASES (UPGRADED UI)
# =============================================================================
elif action_mode == "📂 View Master Databases":
    st.header("📂 Master Intelligence Databases")
    st.caption("Clean and structured view of all ingested intelligence records.")

    # Show an additional Security Audit tab if the user is an Admin
    tabs_to_show = ["🚨 FIR Records", "👤 Criminal Watchlist", "🔍 Investigation Reports"]
    if st.session_state.get("role") == "Admin":
        tabs_to_show.append("🔒 Security Audit Logs")

    db_tabs = st.tabs(tabs_to_show)

    with db_tabs[0]:
        st.subheader("FIR Database Directory")
        fir_rows = get_all_firs()
        if fir_rows:
            df_fir = pd.DataFrame(fir_rows, columns=["ID", "FIR No", "State", "Police Station", "Timestamp", "Narrative", "MO Pattern", "Entities JSON", "Face Hash", "Accounts JSON", "Properties JSON"])
            
            display_df = df_fir[["ID", "FIR No", "State", "Police Station", "Timestamp", "MO Pattern", "Narrative"]]
            
            st.dataframe(
                display_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "FIR No": st.column_config.TextColumn("FIR Number", width="medium"),
                    "State": st.column_config.TextColumn("State", width="medium"),
                    "Police Station": st.column_config.TextColumn("Station", width="medium"),
                    "MO Pattern": st.column_config.TextColumn("Modus Operandi", width="medium"),
                    "Narrative": st.column_config.TextColumn("Narrative Snapshot", width="large"),
                    "Timestamp": st.column_config.TextColumn("Date Logged")
                }
            )
            
            st.markdown("---")
            st.subheader("📇 Detailed Case Files (Card View)")
            
            for row in fir_rows:
                fir_id, fir_no, state, station, ts, narrative, mo, entities, face_hash, acc, prop = row
                
                with st.expander(f"📄 {fir_no} | {mo} | 📍 {station}, {state}"):
                    c1, c2 = st.columns([2, 1])
                    
                    with c1:
                        st.markdown(f"**📝 Incident Narrative:**\n> {narrative}")
                        
                    with c2:
                        st.markdown(f"**📅 Date Logged:** {ts}")
                        try:
                            ent_data = json.loads(entities) if entities else {}
                            
                            suspects = [s.get('name') for s in ent_data.get('Suspects', []) if isinstance(s, dict) and s.get('name')]
                            victims = [v.get('name') for v in ent_data.get('Victims', []) if isinstance(v, dict) and v.get('name')]
                            
                            if suspects:
                                st.error(f"**🔴 Suspects:** {', '.join(suspects)}")
                            if victims:
                                st.info(f"**🔵 Victims:** {', '.join(victims)}")
                        except Exception:
                            st.warning("Could not parse entity data.")
            
            # Restrict Deletion to Admins Only
            if st.session_state.get("role") == "Admin":
                st.markdown("---")
                with st.expander("⚠️ Danger Zone: Delete FIR Record"):
                    st.write("🗑️ **Delete Record**")
                    c_del1, c_del2, c_del3 = st.columns([1, 1, 2])
                    del_id = c_del1.number_input("Delete FIR by ID", min_value=0, step=1, key="del_fir_id")
                    del_pass = c_del2.text_input("Deletion Password", type="password", key="del_fir_pass")
                    if c_del3.button("🗑️ Delete FIR Record", use_container_width=True):
                        if del_pass == RECORD_DELETE_PASS:
                            delete_fir(del_id)
                            log_audit("DELETE_FIR", f"Deleted FIR ID {del_id}")
                            st.success(f"Deleted FIR ID {del_id}")
                            st.rerun()
                        else:
                            st.error("Invalid Deletion Password")
        else:
            st.info("No FIR records found.")

    with db_tabs[1]:
        st.subheader("Criminal Watchlist Profiles")
        wl_rows = get_all_watchlist()
        if wl_rows:
            df_wl = pd.DataFrame(wl_rows, columns=["ID", "Watchlist ID", "Name", "Alias", "State", "Gang", "Jail Record", "MO", "Phone", "Vehicle", "Face Hash", "Image B64", "Aadhaar", "PAN", "Address", "Height", "Build", "Features", "Status", "Risk", "Offences", "Case Links"])
            
            display_wl_df = df_wl[["ID", "Watchlist ID", "Name", "Alias", "Gang", "State", "Status", "Risk"]]
            st.dataframe(
                display_wl_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={"Risk": st.column_config.TextColumn("Risk Level")}
            )
            
            st.markdown("---")
            st.subheader("👤 Detailed Watchlist Cards")
            for w in wl_rows:
                with st.expander(f"🎯 {w[1]} | {w[2]} (Alias: {w[3] if w[3] else 'None'}) - {w[19]} Risk"):
                    wc1, wc2, wc3 = st.columns(3)
                    wc1.markdown(f"**State:** {w[4]}\n\n**Gang:** {w[5] if w[5] else 'Independent'}")
                    wc2.markdown(f"**Status:** {w[18]}\n\n**Phone:** {w[8]}")
                    wc3.markdown(f"**Alleged Offences:**\n{w[20]}")
            
            if st.session_state.get("role") == "Admin":
                st.markdown("---")
                with st.expander("⚠️ Danger Zone: Delete Watchlist Record"):
                    c_del1, c_del2, c_del3 = st.columns([1, 1, 2])
                    del_wl_id = c_del1.number_input("Delete Watchlist by ID", min_value=0, step=1, key="del_wl_id")
                    del_wl_pass = c_del2.text_input("Deletion Password", type="password", key="del_wl_pass")
                    if c_del3.button("🗑️ Delete Watchlist Record", use_container_width=True):
                        if del_wl_pass == RECORD_DELETE_PASS:
                            delete_watchlist(del_wl_id)
                            log_audit("DELETE_WATCHLIST", f"Deleted Watchlist ID {del_wl_id}")
                            st.success(f"Deleted Watchlist ID {del_wl_id}")
                            st.rerun()
                        else:
                            st.error("Invalid Deletion Password")
        else:
            st.info("No Watchlist profiles found.")

    with db_tabs[2]:
        st.subheader("Investigation Logs")
        rep_rows = get_all_reports()
        if rep_rows:
            df_rep = pd.DataFrame(rep_rows, columns=["ID", "Code", "Type", "FIR No", "Person", "Timestamp", "Location", "Vehicle", "VehImg", "People", "Places", "Observations", "Notes", "Evidence", "Phones", "Acc From", "Acc To", "Amount"])
            display_rep = df_rep[["ID", "Code", "Type", "FIR No", "Timestamp", "Observations"]]
            st.dataframe(display_rep, use_container_width=True, hide_index=True)
        else:
            st.info("No Investigation Reports found.")

    if st.session_state.get("role") == "Admin":
        with db_tabs[3]:
            st.subheader("Enterprise Audit Logging")
            logs = get_audit_logs()
            if logs:
                df_logs = pd.DataFrame(logs, columns=["Timestamp", "Username", "Action", "Details"])
                st.dataframe(df_logs, use_container_width=True, hide_index=True)
            else:
                st.info("No audit logs recorded yet.")
