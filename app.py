import base64

def convert_uploaded_image_to_base64(uploaded_file):
    """Converts a Streamlit uploaded image file into a Base64 Data URI for PyVis graph rendering."""
    if uploaded_file is None:
        return None
    bytes_data = uploaded_file.getvalue()
    base64_str = base64.b64encode(bytes_data).decode('utf-8')
    # Detect image extension
    file_type = uploaded_file.type if hasattr(uploaded_file, 'type') else 'image/png'
    return f"data:{file_type};base64,{base64_str}"
import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import re
import tempfile
import os
import sqlite3
import json
import pydeck as pdk
import hashlib
from datetime import datetime
from PIL import Image

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CCTNS AI Criminal Network & Intelligence Grid",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header { font-size: 2.1rem; font-weight: 800; color: #0F172A; margin-bottom: 0px; }
    .sub-header { font-size: 0.95rem; color: #64748B; margin-bottom: 20px; font-weight: 500; }
    .stMetric { background-color: #F8FAFC; padding: 12px; border-radius: 8px; border-left: 5px solid #2563EB; box-shadow: 0 2px 4px rgb(0 0 0 / 0.05); }
    .login-box { max-width: 420px; margin: 80px auto; padding: 30px; background: #FFFFFF; border-radius: 10px; border: 1px solid #E2E8F0; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ALL 28 STATES & 8 UNION TERRITORIES GEOGRAPHIC COORDINATES
# -----------------------------------------------------------------------------
STATE_COORDINATES = {
    "Andhra Pradesh": {"lat": 16.5062, "lon": 80.6480},
    "Arunachal Pradesh": {"lat": 27.1004, "lon": 93.6166},
    "Assam": {"lat": 26.1433, "lon": 91.7898},
    "Bihar": {"lat": 25.5941, "lon": 85.1376},
    "Chhattisgarh": {"lat": 21.2514, "lon": 81.6296},
    "Goa": {"lat": 15.4909, "lon": 73.8278},
    "Gujarat": {"lat": 23.2156, "lon": 72.6369},
    "Haryana": {"lat": 30.7333, "lon": 76.7794},
    "Himachal Pradesh": {"lat": 31.1048, "lon": 77.1734},
    "Jharkhand": {"lat": 23.3441, "lon": 85.3096},
    "Karnataka": {"lat": 12.9716, "lon": 77.5946},
    "Kerala": {"lat": 8.5241, "lon": 76.9366},
    "Madhya Pradesh": {"lat": 23.2599, "lon": 77.4126},
    "Maharashtra": {"lat": 18.9401, "lon": 72.8347},
    "Manipur": {"lat": 24.8170, "lon": 93.9368},
    "Meghalaya": {"lat": 25.5788, "lon": 91.8933},
    "Mizoram": {"lat": 23.7271, "lon": 92.7176},
    "Nagaland": {"lat": 25.6751, "lon": 94.1086},
    "Odisha": {"lat": 20.2961, "lon": 85.8245},
    "Punjab": {"lat": 30.7333, "lon": 76.7794},
    "Rajasthan": {"lat": 26.9124, "lon": 75.7873},
    "Sikkim": {"lat": 27.3389, "lon": 88.6065},
    "Tamil Nadu": {"lat": 13.0827, "lon": 80.2707},
    "Telangana": {"lat": 17.3850, "lon": 78.4867},
    "Tripura": {"lat": 23.8315, "lon": 91.2868},
    "Uttar Pradesh": {"lat": 26.8467, "lon": 80.9462},
    "Uttarakhand": {"lat": 30.3165, "lon": 78.0322},
    "West Bengal": {"lat": 22.5726, "lon": 88.3639},
    "Andaman and Nicobar Islands": {"lat": 11.6233, "lon": 92.7265},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794},
    "Dadra and Nagar Haveli and Daman and Diu": {"lat": 20.3974, "lon": 72.8328},
    "Delhi": {"lat": 28.6139, "lon": 77.2090},
    "Jammu and Kashmir": {"lat": 34.0837, "lon": 74.7973},
    "Ladakh": {"lat": 34.1526, "lon": 77.5771},
    "Lakshadweep": {"lat": 10.5667, "lon": 72.6417},
    "Puducherry": {"lat": 11.9416, "lon": 79.8083}
}

# -----------------------------------------------------------------------------
# AUTHENTICATION ENGINE
# -----------------------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

def login():
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.title("🛡️ MHA Official Portal")
    st.subheader("CCTNS Confidential Intelligence Gateway")
    user = st.text_input("Official Username")
    pwd = st.text_input("Authorization Key", type="password")
    if st.button("Authenticate Officer", use_container_width=True):
        if user == "SIH" and pwd == "1234":
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid Security Credentials. Unauthorized Access Logged.")
    st.markdown('</div>', unsafe_allow_html=True)

if not st.session_state["authenticated"]:
    login()
    st.stop()

# -----------------------------------------------------------------------------
# DUAL DATABASE ENGINE (FIRs + Watchlist Database)
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    # Table 1: FIR Records
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  fir_no TEXT, 
                  state TEXT, 
                  police_station TEXT, 
                  timestamp TEXT, 
                  text_content TEXT, 
                  mo_pattern TEXT, 
                  entities_json TEXT, 
                  face_hash TEXT)''')
    
    # Table 2: Criminal History & Watchlist Database
    c.execute('''CREATE TABLE IF NOT EXISTS criminal_watchlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  name TEXT, 
                  alias TEXT, 
                  state TEXT, 
                  gang_affiliation TEXT, 
                  past_jail_record TEXT, 
                  mo_pattern TEXT, 
                  phone TEXT, 
                  vehicle TEXT, 
                  face_hash TEXT)''')
    conn.commit()
    conn.close()

def insert_fir(fir_no, state, station, text, mo_pattern, entities, face_hash=""):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO fir_records 
                 (fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
              (fir_no, state, station, now, text, mo_pattern, json.dumps(entities), face_hash))
    conn.commit()
    conn.close()

def insert_watchlist_criminal(name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash=""):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("""INSERT INTO criminal_watchlist 
                 (name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
              (name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash))
    conn.commit()
    conn.close()

def get_all_firs():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash FROM fir_records ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_watchlist():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash FROM criminal_watchlist ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def clear_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("DELETE FROM fir_records")
    c.execute("DELETE FROM criminal_watchlist")
    conn.commit()
    conn.close()

init_db()

# -----------------------------------------------------------------------------
# ADVANCED MULTI-ENTITY NLP & IMAGE HASHING ENGINE
# -----------------------------------------------------------------------------
def generate_image_hash(image_file):
    if image_file is not None:
        image_bytes = image_file.read()
        return "FACE_BIO_" + hashlib.md5(image_bytes).hexdigest()[:10].upper()
    return ""

def detect_modus_operandi(text):
    """Categorizes crime execution styles (Modus Operandi) across cases."""
    text_lower = text.lower()
    if any(k in text_lower for k in ["roof", "shutter", "jewel", "break-in", "vault", "lock"]):
        return "Night Theft / Roof Breach Heist"
    elif any(k in text_lower for k in ["phishing", "otp", "cyber", "bank", "account", "transfer", "link"]):
        return "Cyber Financial Phishing Fraud"
    elif any(k in text_lower for k in ["extortion", "ransom", "threat", "gang", "protection money"]):
        return "Gang Extortion / Ransom Network"
    elif any(k in text_lower for k in ["highway", "carjack", "vehicle", "chase", "interception"]):
        return "Highway Vehicle Interception"
    elif any(k in text_lower for k in ["serial", "poison", "murder", "stabbing", "pattern"]):
        return "Serial Violent Crime Signature"
    return "Standard Criminal Activity"

import json
import re
import requests

def clean_entity_list(data):
    """Guarantees data is a clean list of valid strings (rejects single characters, numbers, and strings disguised as lists)."""
    if isinstance(data, str):
        # If LLM returned a single string, split by commas or wrap in a list
        data = [s.strip() for s in data.split(",") if s.strip()]
    if not isinstance(data, list):
        return []
    
    cleaned = []
    stop_words = {
        "has been", "the time", "the shape", "official note", "action taken", 
        "preliminary investigation", "complainant details", "nature of offence"
    }
    
    for item in data:
        if not isinstance(item, str):
            continue
        item = item.strip().strip('"' + "'")
        # Reject single letters, standalone digits, stop words, or excessively long sentences
        if len(item) > 1 and item.lower() not in stop_words and not item.isdigit() and len(item) < 60:
            cleaned.append(item)
            
    return list(set(cleaned))


import json
import requests

def extract_entities_from_text(text):
    """Extracts intelligence data strictly adhering to structured CCTNS crime categories."""
    prompt = f"""
You are a Police Intelligence System. Extract structured crime data from the FIR text below.
DO NOT include sentence fragments, verbs, or narrative words like 'became suspicious' or 'the complainant'.

Return ONLY a valid JSON object strictly matching this schema:
{{
    "Suspects": [
        {{"name": "Full Name", "rank": "A1", "reason": "Prime suspect / accused"}}
    ],
    "Victims": ["Full Name"],
    "Victim_Family": ["Full Name"],
    "Witnesses": ["Full Name"],
    "Locations": ["Specific Location / Police Station"],
    "Vehicles": ["License Plate or Description"],
    "Phones": ["Phone Number"]
}}

Rank Rules for Suspects:
- "A1": Prime suspect / Mastermind / Main accused
- "A2" to "A5": Co-conspirators, accomplices, or secondary suspects ordered by involvement level.

FIR Text:
\"\"\"
{text}
\"\"\"
"""
    # Default schema fallback
    fallback = {
        "Suspects": [],
        "Victims": [],
        "Victim_Family": [],
        "Witnesses": [],
        "Locations": [],
        "Vehicles": [],
        "Phones": []
    }

    try:
        res = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": prompt, "stream": False, "format": "json"},
            timeout=12
        )
        if res.status_code == 200:
            data = json.loads(res.json().get("response", "{}"))
            # Validate suspect hierarchy structure
            suspects = []
            for item in data.get("Suspects", []):
                if isinstance(item, dict) and "name" in item:
                    suspects.append({
                        "name": item["name"].strip(),
                        "rank": item.get("rank", "A1").upper(),
                        "reason": item.get("reason", "Accused")
                    })
                elif isinstance(item, str) and len(item.strip()) > 1:
                    suspects.append({"name": item.strip(), "rank": "A1", "reason": "Accused"})

            return {
                "Suspects": suspects,
                "Victims": [v for v in data.get("Victims", []) if isinstance(v, str) and len(v) > 1],
                "Victim_Family": [f for f in data.get("Victim_Family", []) if isinstance(f, str) and len(f) > 1],
                "Witnesses": [w for w in data.get("Witnesses", []) if isinstance(w, str) and len(w) > 1],
                "Locations": [l for l in data.get("Locations", []) if isinstance(l, str) and len(l) > 1],
                "Vehicles": [veh for veh in data.get("Vehicles", []) if isinstance(veh, str) and len(veh) > 1],
                "Phones": [p for p in data.get("Phones", []) if isinstance(p, str) and len(p) > 1]
            }
    except Exception:
        pass

    return fallback

def build_global_graph(fir_rows, watchlist_rows):
    """Integrates FIRs, Watchlist profiles, Photos, and Modus Operandi into Knowledge Graph."""
    G = nx.Graph()
    entity_fir_map = {}

    # 1. Process FIRs
    for row in fir_rows:
        f_id, fir_no, state, station, timestamp, text, mo_pattern, entities_json, face_hash = row
        entities = json.loads(entities_json)
        
        suspects = entities.get("Suspects", [])
        phones = entities.get("Phones", [])
        vehicles = entities.get("Vehicles", [])
        orgs = entities.get("Organizations", [])
        locs = entities.get("Locations", [])
        
        all_found = suspects + phones + vehicles + orgs + locs
        if face_hash: all_found.append(face_hash)
        if mo_pattern: all_found.append(f"MO: {mo_pattern}")
        
        for ent in all_found:
            if ent not in entity_fir_map:
                entity_fir_map[ent] = set()
            entity_fir_map[ent].add(f"FIR: {fir_no}")

        # Add Nodes
        for s in suspects: G.add_node(s, type="Suspect", color="#EF4444")
        for p in phones: G.add_node(p, type="Phone", color="#3B82F6")
        for v in vehicles: G.add_node(v, type="Vehicle", color="#F59E0B")
        for o in orgs: G.add_node(o, type="Organization", color="#A855F7")
        for l in locs: G.add_node(l, type="Location", color="#10B981")
        if face_hash: G.add_node(face_hash, type="Face Biometric", color="#EC4899")
        if mo_pattern: G.add_node(f"MO: {mo_pattern}", type="Modus Operandi", color="#F97316")

        # Create Intra-FIR Edges
        for s in suspects:
            for p in phones: G.add_edge(s, p, relation=f"USES [{fir_no}]")
            for v in vehicles: G.add_edge(s, v, relation=f"DRIVES [{fir_no}]")
            for o in orgs: G.add_edge(s, o, relation=f"MEMBER [{fir_no}]")
            for l in locs: G.add_edge(s, l, relation=f"SEEN_AT [{fir_no}]")
            if face_hash: G.add_edge(s, face_hash, relation=f"FACE_MATCH [{fir_no}]")
            if mo_pattern: G.add_edge(s, f"MO: {mo_pattern}", relation=f"MO_STYLE [{fir_no}]")

        for i in range(len(suspects)):
            for j in range(i + 1, len(suspects)):
                G.add_edge(suspects[i], suspects[j], relation=f"GANG_MEMBER [{fir_no}]")

    # 2. Process Criminal Watchlist Database
    for w in watchlist_rows:
        w_id, name, alias, state, gang, jail_rec, mo, phone, vehicle, face_hash = w
        w_label = f"WATCHLIST: {name} (Alias: {alias})"
        
        G.add_node(name, type="Suspect (Watchlist)", color="#DC2626")
        if gang: 
            G.add_node(gang, type="Organization", color="#A855F7")
            G.add_edge(name, gang, relation="GANG_LEADER")
        if phone: 
            G.add_node(phone, type="Phone", color="#3B82F6")
            G.add_edge(name, phone, relation="KNOWN_PHONE")
        if vehicle: 
            G.add_node(vehicle, type="Vehicle", color="#F59E0B")
            G.add_edge(name, vehicle, relation="KNOWN_VEHICLE")
        if face_hash: 
            G.add_node(face_hash, type="Face Biometric", color="#EC4899")
            G.add_edge(name, face_hash, relation="REGISTERED_FACE")
        if mo: 
            G.add_node(f"MO: {mo}", type="Modus Operandi", color="#F97316")
            G.add_edge(name, f"MO: {mo}", relation="KNOWN_MO")

        # Map to entity Tracker
        for item in [name, phone, vehicle, face_hash, f"MO: {mo}"]:
            if item:
                if item not in entity_fir_map: entity_fir_map[item] = set()
                entity_fir_map[item].add("Watchlist DB")

    return G, entity_fir_map

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS & AUTH
# -----------------------------------------------------------------------------
st.sidebar.title("👮 Police Portal Controls")
st.sidebar.write(f"**Logged in:** Officer (MHA Grid)")

if st.sidebar.button("🔒 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📥 Ingest Intelligence Data")
action_mode = st.sidebar.radio("Select Action:", [
    "Inject Multi-State Demo Data", 
    "Upload Custom FIR", 
    "Add Criminal to Watchlist"
])

if action_mode == "Inject Multi-State Demo Data":
    if st.sidebar.button("Load Cross-State Gang & MO Data"):
        # Inject Watchlist
        insert_watchlist_criminal("Dawood Ibrahim", "Don", "Maharashtra", "D-Company", "Tihar Jail 2018", "Gang Extortion / Ransom Network", "9876543210", "MH-01-XX-9999", "FACE_BIO_DEMO123")
        
        # Inject FIRs
        demo_firs = [
            ("FIR-2026-TN01", "Tamil Nadu", "Chennai Central PS", "Gangsters Ramesh Kumar and Vikram Reddy executed a Night Theft / Roof Breach Heist near Marina Beach. Phone: 9876543210. Vehicle: TN-01-AB-9999.", "Night Theft / Roof Breach Heist", "FACE_BIO_DEMO123"),
            ("FIR-2026-MH44", "Maharashtra", "Mumbai Crime Branch", "Automobile heist reported in Bandra East. Getaway vehicle TN-01-AB-9999 linked to suspect Ramesh Kumar.", "Highway Vehicle Interception", ""),
            ("FIR-2026-DL09", "Delhi", "Connaught Place PS", "Extortion threat against 'Deccan Logistics'. Suspect Ramesh Kumar traced via phone 9876543210.", "Gang Extortion / Ransom Network", "FACE_BIO_DEMO123")
        ]
        for fir_no, state, station, text, mo, f_hash in demo_firs:
            insert_fir(fir_no, state, station, text, mo, extract_entities_from_text(text), f_hash)
        st.sidebar.success("Multi-state gang & biometric data injected!")
        st.rerun()

elif action_mode == "Upload Custom FIR":
    c_fir_no = st.sidebar.text_input("FIR Number", "FIR-2026-901")
    c_state = st.sidebar.selectbox("State / UT (All 36 Available)", list(STATE_COORDINATES.keys()))
    c_station = st.sidebar.text_input("Police Station", "District Central PS")
    fir_text = st.sidebar.text_area("Paste FIR Document / Structured Details", height=200)
        uploaded_photo = st.sidebar.file_uploader("Upload Suspect Face Photo (Optional)", type=["jpg", "png", "jpeg"])

        if st.sidebar.button("Ingest FIR into Database"):
            if fir_text.strip():
                # Safely convert image to base64 if uploaded
                import base64
                face_b64 = ""
                if uploaded_photo is not None:
                    face_b64 = base64.b64encode(uploaded_photo.read()).decode("utf-8")
                
                # Extract entities using your existing function
                data = extract_entities_from_text(fir_text)
                
                # Bind face image directly to the A1 Suspect (first suspect in list)
                if face_b64 and "Suspects" in data and len(data["Suspects"]) > 0:
                    data["Suspects"][0]["image"] = face_b64
                
                # Save structured record into Session State
                st.session_state['last_ingested_fir'] = data
                st.sidebar.success("✅ FIR ingested successfully with structured hierarchy!")
            
            insert_fir(c_fir_no, c_state, c_station, txt_content, mo_pattern, extracted, face_hash)
            st.sidebar.success("FIR filed & biometrics cross-linked in Database!")
            st.rerun()

elif action_mode == "Add Criminal to Watchlist":
    w_name = st.sidebar.text_input("Criminal Full Name")
    w_alias = st.sidebar.text_input("Alias / Moniker")
    w_state = st.sidebar.selectbox("Operating State / UT", list(STATE_COORDINATES.keys()), key="w_state")
    w_gang = st.sidebar.text_input("Gang / Terror Outfit Name")
    w_jail = st.sidebar.text_input("Past Jail / Arrest Record Details")
    w_mo = st.sidebar.selectbox("Known Modus Operandi (MO)", [
        "Night Theft / Roof Breach Heist", 
        "Cyber Financial Phishing Fraud", 
        "Gang Extortion / Ransom Network", 
        "Highway Vehicle Interception", 
        "Serial Violent Crime Signature"
    ])
    w_phone = st.sidebar.text_input("Known Phone Number")
    w_vehicle = st.sidebar.text_input("Known Vehicle Number")
    w_photo = st.sidebar.file_uploader("Criminal Photo Registration", type=["jpg", "png", "jpeg"], key="w_photo")
    
    if st.sidebar.button("Register Criminal Profile"):
        if w_name:
            f_hash = generate_image_hash(w_photo) if w_photo else ""
            insert_watchlist_criminal(w_name, w_alias, w_state, w_gang, w_jail, w_mo, w_phone, w_vehicle, f_hash)
            st.sidebar.success(f"Profile registered for {w_name} in Criminal History DB!")
            st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("⚠️ Wipe Master Database"):
    clear_db()
    st.sidebar.warning("Database reset complete.")
    st.rerun()

# -----------------------------------------------------------------------------
# MAIN DASHBOARD INTERFACE
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network & Intelligence Grid</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ministry of Home Affairs | SIH 2026 Problem ID: 26189 | All-India Multi-Entity Intelligence Grid</div>', unsafe_allow_html=True)

fir_rows = get_all_firs()
watchlist_rows = get_all_watchlist()

if fir_rows or watchlist_rows:
    G, entity_fir_map = build_global_graph(fir_rows, watchlist_rows)
    
    # Calculate Multi-Source Threats
    multi_matches = {ent: sources for ent, sources in entity_fir_map.items() if len(sources) > 1}
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("FIRs Ingested", len(fir_rows))
    m2.metric("Watchlist Criminals Registered", len(watchlist_rows))
    m3.metric("Extracted Entities & Biometrics", len(G.nodes()))
    m4.metric("Cross-Jurisdictional Matches", len(multi_matches))

    st.markdown("---")
    
    t1, t2, t3, t4, t5 = st.tabs([
        "🕸️ Knowledge Graph", 
        "🗺️ All-India CCTNS Geospatial Map", 
        "👤 Criminal Watchlist Database", 
        "🎯 Modus Operandi (MO) Matcher", 
        "🚨 High-Threat Alerts"
    ])
    
    # TAB 1: KNOWLEDGE GRAPH
    with t1:
        st.subheader("Global Entity Relationship Graph")
        st.caption("Node Types: 🔴 Suspects (A1-A5) | 🟦 Victims | 🟪 Family | 🟢 Witnesses | 🟡 Vehicles | 🔵 Phones | 📍 Locations")
        
        net = Network(height="680px", width="100%", bgcolor="#0F172A", font_color="white")
        
        # Color mapping by category & suspect hierarchy
        rank_colors = {"A1": "#EF4444", "A2": "#F97316", "A3": "#F59E0B", "A4": "#EAB308", "A5": "#84CC16"}
        
        for node, attrs in G.nodes(data=True):
            # Guard against invalid nodes
            if len(str(node).strip()) <= 1:
                continue
                
            node_type = attrs.get("type", "Entity")
            image_url = attrs.get("image", None)
            rank = attrs.get("rank", "A1")
            
            # Setup styling per category
            if node_type == "Suspect":
                color = rank_colors.get(rank, "#EF4444")
                size = 45 if rank == "A1" else 30
                label = f"[{rank}] {node}"
            elif node_type == "Victim":
                color = "#3B82F6"
                size = 28
                label = f"Victim: {node}"
            elif node_type == "Victim_Family":
                color = "#A855F7"
                size = 22
                label = f"Family: {node}"
            elif node_type == "Witness":
                color = "#10B981"
                size = 22
                label = f"Witness: {node}"
            else:
                color = attrs.get("color", "#94A3B8")
                size = 20
                label = str(node)

            # Node creation kwargs
            node_kwargs = {
                "label": label,
                "color": color,
                "size": size,
                "borderWidth": 3 if rank == "A1" else 1,
                "title": f"Category: {node_type}<br>Details: {attrs.get('info', 'Linked to case')}"
            }

            # Embed Face Image on Node if present
            if image_url:
                node_kwargs["shape"] = "circularImage"
                node_kwargs["image"] = image_url
            else:
                node_kwargs["shape"] = "dot"

            net.add_node(node, **node_kwargs)

        for u, v, attrs in G.edges(data=True):
            net.add_edge(u, v, title=attrs.get("relation", "LINKED"), color="#475569")

        # Stable force layout configuration
        net.force_atlas_2based(
            gravity=-120,
            central_gravity=0.015,
            spring_length=180,
            spring_strength=0.06,
            overlap=0.8
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            net.save_graph(tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=700)
        os.remove(tmp_path)# TAB 1: KNOWLEDGE GRAPH
    with t1:
        st.subheader("Global Entity Relationship Graph")
        st.caption("Node Types: 🔴 Suspects (A1-A5) | 🟦 Victims | 🟪 Family | 🟢 Witnesses | 🟡 Vehicles | 🔵 Phones | 📍 Locations")
        
        net = Network(height="680px", width="100%", bgcolor="#0F172A", font_color="white")
        
        # Color mapping by category & suspect hierarchy
        rank_colors = {"A1": "#EF4444", "A2": "#F97316", "A3": "#F59E0B", "A4": "#EAB308", "A5": "#84CC16"}
        
        for node, attrs in G.nodes(data=True):
            # Guard against invalid nodes
            if len(str(node).strip()) <= 1:
                continue
                
            node_type = attrs.get("type", "Entity")
            image_url = attrs.get("image", None)
            rank = attrs.get("rank", "A1")
            
            # Setup styling per category
            if node_type == "Suspect":
                color = rank_colors.get(rank, "#EF4444")
                size = 45 if rank == "A1" else 30
                label = f"[{rank}] {node}"
            elif node_type == "Victim":
                color = "#3B82F6"
                size = 28
                label = f"Victim: {node}"
            elif node_type == "Victim_Family":
                color = "#A855F7"
                size = 22
                label = f"Family: {node}"
            elif node_type == "Witness":
                color = "#10B981"
                size = 22
                label = f"Witness: {node}"
            else:
                color = attrs.get("color", "#94A3B8")
                size = 20
                label = str(node)

            # Node creation kwargs
            node_kwargs = {
                "label": label,
                "color": color,
                "size": size,
                "borderWidth": 3 if rank == "A1" else 1,
                "title": f"Category: {node_type}<br>Details: {attrs.get('info', 'Linked to case')}"
            }

            # Embed Face Image on Node if present
            if image_url:
                node_kwargs["shape"] = "circularImage"
                node_kwargs["image"] = image_url
            else:
                node_kwargs["shape"] = "dot"

            net.add_node(node, **node_kwargs)

        for u, v, attrs in G.edges(data=True):
            net.add_edge(u, v, title=attrs.get("relation", "LINKED"), color="#475569")

        # Stable force layout configuration
        net.force_atlas_2based(
            gravity=-120,
            central_gravity=0.015,
            spring_length=180,
            spring_strength=0.06,
            overlap=0.8
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            net.save_graph(tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=700)
        os.remove(tmp_path)

    # TAB 2: GEOSPATIAL MAP (DYNAMIC ALL-INDIA PLOTTING)
    with t2:
        st.subheader("All-India CCTNS Spatial Radar")
        st.caption("Dynamically plots crime occurrence hotspots across all 36 States & UTs.")
        
        # Aggregate FIR count per State
        state_counts = {}
        for row in fir_rows:
            st_name = row[2]
            state_counts[st_name] = state_counts.get(st_name, 0) + 1
            
        map_data = []
        for state_name, coords in STATE_COORDINATES.items():
            count = state_counts.get(state_name, 0)
            map_data.append({
                "state": state_name,
                "lat": coords["lat"],
                "lon": coords["lon"],
                "fir_count": count,
                "radius": 15000 + (count * 35000)
            })
            
        map_df = pd.DataFrame(map_data)
        
        layer = pdk.Layer(
            "ScatterplotLayer",
            map_df,
            get_position="[lon, lat]",
            get_fill_color="[239, 68, 68, 200]",
            get_line_color="[255, 255, 255, 255]",
            line_width_min_pixels=2,
            get_radius="radius",
            pickable=True
        )
        
        view_state = pdk.ViewState(latitude=22.5937, longitude=78.9629, zoom=4.2, pitch=30)
        
        st.pydeck_chart(pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"html": "<b>State/UT:</b> {state}<br/><b>Active FIRs File:</b> {fir_count}"}
        ))

    # TAB 3: CRIMINAL WATCHLIST DATABASE
    with t3:
        st.subheader("Pre-Existing Criminal History & Watchlist Database")
        st.caption("Active monitoring list for un-apprehended criminals, past convicts, and terror network suspects.")
        
        if watchlist_rows:
            w_df = pd.DataFrame(watchlist_rows, columns=[
                "DB ID", "Full Name", "Alias", "State", "Gang Affiliation", 
                "Past Jail / Conviction", "Modus Operandi", "Known Phone", "Known Vehicle", "Face Biometric Hash"
            ])
            st.dataframe(w_df, use_container_width=True, hide_index=True)
        else:
            st.info("No criminal profiles registered in Watchlist DB yet. Use the sidebar to register profiles.")

    # TAB 4: MODUS OPERANDI MATCHING
    with t4:
        st.subheader("Modus Operandi (MO) & Serial Crime Signature Engine")
        st.caption("Identifies recurring crime patterns (e.g. serial break-ins, specific heist styles) across states.")
        
        mo_dict = {}
        for row in fir_rows:
            mo = row[6]
            fir = row[1]
            if mo not in mo_dict: mo_dict[mo] = []
            mo_dict[mo].append(fir)
            
        for w in watchlist_rows:
            mo = w[6]
            c_name = f"Watchlist Criminal: {w[1]}"
            if mo not in mo_dict: mo_dict[mo] = []
            mo_dict[mo].append(c_name)
            
        for mo_pattern, cases in mo_dict.items():
            if len(cases) > 1:
                st.warning(f"🎯 **RECURRING MODUS OPERANDI DETECTED:** `{mo_pattern}` linked across: {', '.join(cases)}")
            else:
                st.info(f"Pattern: `{mo_pattern}` -> Active in: {cases[0]}")

    # TAB 5: THREAT ALERTS
    with t5:
        st.subheader("Cross-Jurisdictional Threat Alerts")
        if multi_matches:
            st.error(f"🚨 **CRITICAL CROSS-MATCHES DETECTED:** {len(multi_matches)} entities matched across FIRs & Watchlist DB!")
            
            t_data = []
            for ent, sources in multi_matches.items():
                e_type = G.nodes[ent].get("type", "Unknown") if ent in G.nodes else "Unknown"
                t_data.append({
                    "Cross-Linked Entity / Biometric": ent,
                    "Entity Type": e_type,
                    "Total Matching Sources": len(sources),
                    "Matched Databases / FIRs": ", ".join(list(sources)),
                    "Threat Assessment": "🔴 CRITICAL MATCH (Cross-State / Watchlist Trigger)"
                })
            st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)
        else:
            st.success("✅ No cross-jurisdictional matches flagged yet.")

else:
    st.info("👈 Authenticate and use the sidebar to **'Inject Multi-State Demo Data'** or upload custom files.")
