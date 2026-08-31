import base64
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
    .form-container { background-color: #F8FAFC; padding: 20px; border-radius: 10px; border: 1px solid #E2E8F0; margin-bottom: 15px;}
    .login-box { max-width: 420px; margin: 80px auto; padding: 30px; background: #FFFFFF; border-radius: 10px; border: 1px solid #E2E8F0; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# ALL 28 STATES & 8 UNION TERRITORIES GEOGRAPHIC COORDINATES
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
# DUAL DATABASE ENGINE
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fir_no TEXT, state TEXT, police_station TEXT, 
                  timestamp TEXT, text_content TEXT, mo_pattern TEXT, entities_json TEXT, face_hash TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS criminal_watchlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, alias TEXT, state TEXT, gang_affiliation TEXT, 
                  past_jail_record TEXT, mo_pattern TEXT, phone TEXT, vehicle TEXT, face_hash TEXT, image_b64 TEXT)''')
    conn.commit()
    conn.close()

def insert_fir(fir_no, state, station, text, mo_pattern, entities, face_hash=""):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO fir_records (fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (fir_no, state, station, now, text, mo_pattern, json.dumps(entities), face_hash))
    conn.commit()
    conn.close()

def insert_watchlist_criminal(name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("""INSERT INTO criminal_watchlist 
                 (name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash, image_b64) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
              (name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64))
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
    c.execute("SELECT * FROM criminal_watchlist ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
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

def detect_modus_operandi(text):
    text_lower = text.lower()
    if any(k in text_lower for k in ["roof", "shutter", "jewel", "break-in", "vault", "lock"]): return "Night Theft / Roof Breach Heist"
    elif any(k in text_lower for k in ["phishing", "otp", "cyber", "bank", "account", "transfer"]): return "Cyber Financial Phishing Fraud"
    elif any(k in text_lower for k in ["extortion", "ransom", "threat", "gang"]): return "Gang Extortion / Ransom Network"
    elif any(k in text_lower for k in ["highway", "carjack", "vehicle", "chase"]): return "Highway Vehicle Interception"
    return "Standard Criminal Activity"

# -----------------------------------------------------------------------------
# DYNAMIC STATE MANAGEMENT FOR FORMS
# -----------------------------------------------------------------------------
if "suspect_count" not in st.session_state: st.session_state.suspect_count = 1
if "witness_count" not in st.session_state: st.session_state.witness_count = 1
if "vehicle_count" not in st.session_state: st.session_state.vehicle_count = 1

# -----------------------------------------------------------------------------
# SIDEBAR NAVIGATION
# -----------------------------------------------------------------------------
st.sidebar.title("👮 Police Portal Controls")
st.sidebar.write("**Logged in:** Official (MHA Grid)")

if st.sidebar.button("🔒 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.markdown("---")
action_mode = st.sidebar.radio("Navigation Menu:", [
    "📊 Main Dashboard (Graph & Maps)", 
    "📝 File Custom FIR (Structured)", 
    "👤 Add to Watchlist",
    "📂 View Database Records"
])

st.sidebar.markdown("---")
if st.sidebar.button("⚠️ Wipe Master Database"):
    conn = sqlite3.connect('cctns_master.db')
    conn.execute("DELETE FROM fir_records")
    conn.execute("DELETE FROM criminal_watchlist")
    conn.commit()
    conn.close()
    st.sidebar.warning("Database reset complete.")
    st.rerun()

st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network & Intelligence Grid</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">All-India Multi-Entity Intelligence Grid (Structured Data Engine)</div>', unsafe_allow_html=True)

# =============================================================================
# VIEW 1: MAIN DASHBOARD (GRAPH & MAPS)
# =============================================================================
if action_mode == "📊 Main Dashboard (Graph & Maps)":
    fir_rows = get_all_firs()
    watchlist_rows = get_all_watchlist()

    # Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total FIRs Ingested", len(fir_rows))
    m2.metric("Watchlist Criminals", len(watchlist_rows))
    m3.metric("Live Intelligence Nodes", len(fir_rows) * 5 + len(watchlist_rows) * 3) # Approx nodes
    st.markdown("---")

    t1, t2 = st.tabs(["🕸️ Knowledge Graph", "🗺️ All-India CCTNS Geospatial Map"])

    with t1:
        st.subheader("Global Entity Relationship Graph")
        st.caption("Relationships (strings) between entities are explicitly labeled. Zoom and drag nodes to explore networks.")
        
        if fir_rows or watchlist_rows:
            G = nx.Graph()
            
            # Process FIRs
            for row in fir_rows:
                f_id, fir_no, state, station, timestamp, text, mo_pattern, entities_json, face_hash = row
                entities = json.loads(entities_json)
                
                suspects_data = entities.get("Suspects", [])
                witnesses_data = entities.get("Witnesses", [])
                vehicles_data = entities.get("Vehicles", [])
                locations = entities.get("Locations", [])
                
                # Nodes
                for s in suspects_data:
                    G.add_node(s["name"], type="Suspect", rank=s.get("rank", "A1"), image=s.get("image"))
                    if s.get("phone"): G.add_node(s["phone"], type="Phone", color="#3B82F6")
                    if s.get("face_hash"): G.add_node(s["face_hash"], type="Face Biometric", color="#EC4899")
                
                for w in witnesses_data:
                    G.add_node(w["name"], type="Witness", color="#10B981")
                    if w.get("phone"): G.add_node(w["phone"], type="Phone", color="#3B82F6")
                    
                for v in vehicles_data: G.add_node(v["plate"], type="Vehicle", color="#F59E0B", image=v.get("image"))
                for l in locations: G.add_node(l, type="Location", color="#8B5CF6")
                if mo_pattern: G.add_node(f"MO: {mo_pattern}", type="Modus Operandi", color="#F97316")
                
                # Edges (With labels)
                s_names = [s["name"] for s in suspects_data]
                for s_name in s_names:
                    s_dict = next(item for item in suspects_data if item["name"] == s_name)
                    if s_dict.get("phone"): G.add_edge(s_name, s_dict["phone"], relation="OWNS_PHONE")
                    if s_dict.get("face_hash"): G.add_edge(s_name, s_dict["face_hash"], relation="FACE_MATCH")
                    
                    for v in vehicles_data: G.add_edge(s_name, v["plate"], relation=f"LINKED_VEHICLE [{fir_no}]")
                    for l in locations: G.add_edge(s_name, l, relation=f"SEEN_AT")
                    if mo_pattern: G.add_edge(s_name, f"MO: {mo_pattern}", relation=f"OPERATES_BY")
                    for w in witnesses_data: G.add_edge(s_name, w["name"], relation=f"WITNESSED_BY")

                for i in range(len(s_names)):
                    for j in range(i + 1, len(s_names)):
                        G.add_edge(s_names[i], s_names[j], relation=f"CO_ACCUSED")

            # Process Watchlist
            for w in watchlist_rows:
                w_id, name, alias, state, gang, jail_rec, mo, phone, vehicle, face_hash, img_b64 = w
                G.add_node(name, type="Suspect (Watchlist)", color="#DC2626", rank="A1", image=img_b64)
                if gang: 
                    G.add_node(gang, type="Organization", color="#A855F7")
                    G.add_edge(name, gang, relation="GANG_LEADER")
                if phone: 
                    G.add_node(phone, type="Phone", color="#3B82F6")
                    G.add_edge(name, phone, relation="KNOWN_PHONE")
                if vehicle: 
                    G.add_node(vehicle, type="Vehicle", color="#F59E0B")
                    G.add_edge(name, vehicle, relation="KNOWN_VEHICLE")
                if mo: 
                    G.add_node(f"MO: {mo}", type="Modus Operandi", color="#F97316")
                    G.add_edge(name, f"MO: {mo}", relation="KNOWN_MO")

            net = Network(height="750px", width="100%", bgcolor="#0F172A", font_color="white")
            rank_colors = {"A1": "#EF4444", "A2": "#F97316", "A3": "#F59E0B"}
            
            for node, attrs in G.nodes(data=True):
                node_type = attrs.get("type", "Entity")
                image_url = attrs.get("image", None)
                
                if "Suspect" in node_type: color, size = rank_colors.get(attrs.get("rank", "A1"), "#EF4444"), 40
                elif node_type == "Vehicle": color, size = "#F59E0B", 25
                elif node_type == "Phone": color, size = "#3B82F6", 20
                elif node_type == "Witness": color, size = "#10B981", 25
                elif node_type == "Location": color, size = "#8B5CF6", 25
                else: color, size = attrs.get("color", "#94A3B8"), 20

                node_kwargs = {"label": str(node), "color": color, "size": size, "title": f"{node_type}"}
                if image_url: node_kwargs.update({"shape": "circularImage", "image": image_url})
                else: node_kwargs["shape"] = "dot"
                net.add_node(node, **node_kwargs)

            # Add explicit Edge Labels
            for u, v, attrs in G.edges(data=True):
                net.add_edge(u, v, label=attrs.get("relation", ""), title=attrs.get("relation", ""), 
                             color="#475569", font={"size": 10, "color": "#94A3B8", "align": "middle"})

            net.force_atlas_2based(gravity=-120, central_gravity=0.015, spring_length=180, spring_strength=0.06, overlap=0.8)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                net.save_graph(tmp.name)
                with open(tmp.name, 'r', encoding='utf-8') as f:
                    components.html(f.read(), height=800)
            os.remove(tmp.name)
        else:
            st.info("No data available to generate graph. Please file an FIR or add to the Watchlist.")

    with t2:
        st.subheader("All-India CCTNS Spatial Radar")
        st.caption("Dynamically plots crime occurrence hotspots across all 36 States & UTs based on FIRs and Watchlist entries.")
        
        state_counts = {}
        for row in fir_rows:
            st_name = row[2] # State from FIR
            state_counts[st_name] = state_counts.get(st_name, 0) + 1
        for w in watchlist_rows:
            st_name = w[3] # State from Watchlist
            state_counts[st_name] = state_counts.get(st_name, 0) + 1
            
        map_data = []
        for state_name, coords in STATE_COORDINATES.items():
            count = state_counts.get(state_name, 0)
            # Create a base dot for all states, make it larger/red if crime exists
            radius = 15000 + (count * 40000) if count > 0 else 10000
            color = [239, 68, 68, 200] if count > 0 else [100, 116, 139, 100]
            
            map_data.append({
                "state": state_name, "lat": coords["lat"], "lon": coords["lon"],
                "fir_count": count, "radius": radius, "color": color
            })
            
        map_df = pd.DataFrame(map_data)
        
        layer = pdk.Layer(
            "ScatterplotLayer",
            map_df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_line_color="[255, 255, 255, 255]",
            line_width_min_pixels=1,
            get_radius="radius",
            pickable=True
        )
        
        view_state = pdk.ViewState(latitude=22.5937, longitude=78.9629, zoom=4.0, pitch=35)
        
        st.pydeck_chart(pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"html": "<b>State / UT:</b> {state}<br/><b>Active FIRs/Threats:</b> {fir_count}"}
        ))

# =============================================================================
# VIEW 2: FILE CUSTOM FIR (STRUCTURED INPUT)
# =============================================================================
elif action_mode == "📝 File Custom FIR (Structured)":
    st.header("📝 File New Custom FIR")
    st.caption("Explicit structured fields guarantee 100% accurate entity extraction for the Knowledge Graph.")
    
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c_fir_no = c1.text_input("FIR Number", "FIR-2026-001")
        c_state = c2.selectbox("State / UT", list(STATE_COORDINATES.keys()))
        c_station = c1.text_input("Police Station", "Central Crime Branch")
        c_location = c2.text_input("Specific Crime Location", "Main Street Bank")
        fir_text = st.text_area("Case Narrative (Used for Modus Operandi detection)", height=100)
        st.markdown('</div>', unsafe_allow_html=True)

    # Suspects Section
    st.subheader("🔴 Suspects & Accused")
    suspects_collected = []
    for i in range(st.session_state.suspect_count):
        with st.expander(f"Suspect A{i+1}", expanded=True):
            sc1, sc2 = st.columns(2)
            s_name = sc1.text_input(f"Full Name (A{i+1})", key=f"s_name_{i}")
            s_phone = sc2.text_input(f"Phone Number (A{i+1})", key=f"s_ph_{i}")
            s_details = st.text_input(f"Involvement Details / Reason", key=f"s_det_{i}")
            s_photo = st.file_uploader(f"Upload Face Photo (A{i+1})", type=["jpg", "png"], key=f"s_pic_{i}")
            
            if s_name:
                img_b64, img_hash = process_uploaded_image(s_photo)
                suspects_collected.append({"name": s_name, "rank": f"A{i+1}", "reason": s_details, "phone": s_phone, "image": img_b64, "face_hash": img_hash})
    if st.button("➕ Add Another Suspect"): 
        st.session_state.suspect_count += 1
        st.rerun()

    # Witnesses Section
    st.subheader("🟢 Witnesses")
    witnesses_collected = []
    for i in range(st.session_state.witness_count):
        with st.expander(f"Witness W{i+1}", expanded=False):
            w_name = st.text_input(f"Witness Name (W{i+1})", key=f"w_name_{i}")
            w_phone = st.text_input(f"Witness Phone (W{i+1})", key=f"w_ph_{i}")
            w_details = st.text_input(f"Statement / Details", key=f"w_det_{i}")
            if w_name: witnesses_collected.append({"name": w_name, "phone": w_phone, "details": w_details})
    if st.button("➕ Add Another Witness"): 
        st.session_state.witness_count += 1
        st.rerun()

    # Vehicles Section
    st.subheader("🟡 Vehicles Involved")
    vehicles_collected = []
    for i in range(st.session_state.vehicle_count):
        with st.expander(f"Vehicle V{i+1}", expanded=False):
            vc1, vc2 = st.columns(2)
            v_plate = vc1.text_input(f"License Plate (V{i+1})", key=f"v_plate_{i}")
            v_desc = vc2.text_input(f"Make / Model / Color", key=f"v_desc_{i}")
            v_photo = st.file_uploader(f"Upload Vehicle Photo (V{i+1})", type=["jpg", "png"], key=f"v_pic_{i}")
            if v_plate or v_desc:
                img_b64, _ = process_uploaded_image(v_photo)
                vehicles_collected.append({"plate": v_plate, "description": v_desc, "image": img_b64})
    if st.button("➕ Add Another Vehicle"): 
        st.session_state.vehicle_count += 1
        st.rerun()

    # Submission
    st.markdown("---")
    if st.button("💾 Ingest Structured FIR into Database", type="primary", use_container_width=True):
        if not c_fir_no or not c_station:
            st.error("FIR Number and Police Station are required.")
        else:
            structured_entities = {
                "Suspects": suspects_collected, "Witnesses": witnesses_collected,
                "Vehicles": vehicles_collected, "Locations": [c_location] if c_location else [], "Phones": []
            }
            mo_pattern = detect_modus_operandi(fir_text)
            primary_hash = suspects_collected[0].get("face_hash", "") if suspects_collected else ""
            insert_fir(c_fir_no, c_state, c_station, fir_text, mo_pattern, structured_entities, primary_hash)
            st.success(f"✅ FIR {c_fir_no} ingested successfully! All entities structured and linked.")

# =============================================================================
# VIEW 3: ADD TO WATCHLIST
# =============================================================================
elif action_mode == "👤 Add to Watchlist":
    st.header("👤 Register Criminal to Watchlist")
    st.caption("Profiles added here bypass standard FIR generation and are injected directly into the active monitoring grid.")
    
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        wc1, wc2 = st.columns(2)
        w_name = wc1.text_input("Criminal Full Name *")
        w_alias = wc2.text_input("Alias / Moniker")
        w_state = wc1.selectbox("Operating State / UT", list(STATE_COORDINATES.keys()))
        w_gang = wc2.text_input("Gang / Terror Outfit Name")
        
        st.markdown("---")
        w_jail = st.text_input("Past Jail / Arrest Record Details")
        w_mo = st.selectbox("Known Modus Operandi (MO)", [
            "Standard Criminal Activity", "Night Theft / Roof Breach Heist", 
            "Cyber Financial Phishing Fraud", "Gang Extortion / Ransom Network", 
            "Highway Vehicle Interception", "Serial Violent Crime Signature"
        ])
        
        wc3, wc4 = st.columns(2)
        w_phone = wc3.text_input("Known Phone Number")
        w_vehicle = wc4.text_input("Known Vehicle Number (License Plate)")
        
        w_photo = st.file_uploader("Upload Criminal Mugshot / Photo *", type=["jpg", "png", "jpeg"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("🚨 Register Profile in DB", type="primary", use_container_width=True):
            if w_name:
                img_b64, img_hash = process_uploaded_image(w_photo)
                insert_watchlist_criminal(w_name, w_alias, w_state, w_gang, w_jail, w_mo, w_phone, w_vehicle, img_hash, img_b64)
                st.success(f"✅ Profile for '{w_name}' registered successfully and linked to Intelligence Grid!")
            else:
                st.error("Criminal Full Name is required.")

# =============================================================================
# VIEW 4: VIEW DATABASE RECORDS
# =============================================================================
elif action_mode == "📂 View Database Records":
    st.header("📂 Master Database Explorer")
    
    tab_firs, tab_watch = st.tabs(["📄 FIR Records", "👤 Watchlist Profiles"])
    
    with tab_firs:
        rows = get_all_firs()
        if not rows:
            st.info("No FIRs found in the database.")
        else:
            for row in rows:
                f_id, fir_no, state, station, timestamp, text, mo_pattern, entities_json, face_hash = row
                with st.expander(f"📄 {fir_no} | {station}, {state} | MO: {mo_pattern}"):
                    st.write(f"**Date Filed:** {timestamp}")
                    st.write(f"**Narrative:** {text}")
                    entities = json.loads(entities_json)
                    
                    st.write("#### Suspects")
                    if entities.get("Suspects"):
                        cols = st.columns(len(entities["Suspects"]))
                        for idx, s in enumerate(entities["Suspects"]):
                            with cols[idx]:
                                if s.get("image"):
                                    st.markdown(f'<img src="{s["image"]}" width="120" style="border-radius:10px;">', unsafe_allow_html=True)
                                st.write(f"**[{s.get('rank')}] {s.get('name')}**")
                                st.caption(f"Phone: {s.get('phone')}")
                                st.caption(f"Reason: {s.get('reason')}")
                    else: st.write("None")
                    
                    st.write("#### Vehicles")
                    if entities.get("Vehicles"):
                        for v in entities["Vehicles"]:
                            st.write(f"- 🚗 **{v.get('plate')}** ({v.get('description')})")
                            if v.get("image"):
                                st.markdown(f'<img src="{v["image"]}" width="150" style="border-radius:5px;">', unsafe_allow_html=True)
                    else: st.write("None")

    with tab_watch:
        w_rows = get_all_watchlist()
        if not w_rows:
            st.info("No Criminals in Watchlist.")
        else:
            for w in w_rows:
                w_id, name, alias, state, gang, jail_rec, mo, phone, vehicle, face_hash, img_b64 = w
                with st.expander(f"🚨 {name} (Alias: {alias}) | {state}"):
                    wc1, wc2 = st.columns([1, 3])
                    with wc1:
                        if img_b64:
                            st.markdown(f'<img src="{img_b64}" width="150" style="border-radius:10px;">', unsafe_allow_html=True)
                        else: st.write("No Image")
                    with wc2:
                        st.write(f"**Gang Affiliation:** {gang}")
                        st.write(f"**Modus Operandi:** {mo}")
                        st.write(f"**Past Record:** {jail_rec}")
                        st.write(f"**Known Phone:** {phone}")
                        st.write(f"**Known Vehicle:** {vehicle}")
