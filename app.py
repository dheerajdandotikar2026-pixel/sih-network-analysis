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
import pydeck as pdk
import hashlib
from datetime import datetime

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CCTNS AI Criminal Network & Intelligence Grid",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# DARK MODE COMPATIBLE CSS
st.markdown("""
<style>
    .main-header { font-size: 2.1rem; font-weight: 800; margin-bottom: 0px; }
    .sub-header { font-size: 0.95rem; margin-bottom: 20px; font-weight: 500; opacity: 0.8; }
    .stMetric { background-color: rgba(128, 128, 128, 0.1); padding: 12px; border-radius: 8px; border-left: 5px solid #2563EB; box-shadow: 0 2px 4px rgb(0 0 0 / 0.05); }
    .form-container { background-color: rgba(128, 128, 128, 0.05); padding: 20px; border-radius: 10px; border: 1px solid rgba(128, 128, 128, 0.2); margin-bottom: 15px;}
    .login-box { max-width: 420px; margin: 80px auto; padding: 30px; background-color: rgba(128, 128, 128, 0.05); border-radius: 10px; border: 1px solid rgba(128, 128, 128, 0.2); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
    .match-card { background-color: rgba(239, 68, 68, 0.1); border-left: 5px solid #EF4444; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
    .match-card-success { background-color: rgba(34, 197, 94, 0.1); border-left: 5px solid #22C55E; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
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
# 3-DATABASE SYSTEM (FIRs, WATCHLISTS, INVESTIGATION REPORTS)
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    # DB 1: FIR Records (Added property_reg_json)
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, fir_no TEXT UNIQUE, state TEXT, police_station TEXT, 
                  timestamp TEXT, text_content TEXT, mo_pattern TEXT, entities_json TEXT, face_hash TEXT, account_numbers_json TEXT, property_reg_json TEXT)''')
    
    # DB 2: Criminal Watchlist
    c.execute('''CREATE TABLE IF NOT EXISTS criminal_watchlist
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, watchlist_id TEXT UNIQUE, name TEXT, alias TEXT, state TEXT, gang_affiliation TEXT, 
                  past_jail_record TEXT, mo_pattern TEXT, phone TEXT, vehicle TEXT, face_hash TEXT, image_b64 TEXT, aadhaar TEXT, pan TEXT, address TEXT)''')
    
    # DB 3: Investigation Reports
    c.execute('''CREATE TABLE IF NOT EXISTS investigation_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, report_code TEXT, report_type TEXT, fir_no TEXT, person_observed TEXT, 
                  timestamp TEXT, location TEXT, vehicle_details TEXT, vehicle_img_b64 TEXT, people_seen TEXT, places_visited TEXT, 
                  observations TEXT, officer_notes TEXT, evidence_ref TEXT, phone_list_json TEXT, account_from TEXT, account_to TEXT, amount REAL)''')
    conn.commit()
    conn.close()

def upgrade_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    for col, dtype in [("watchlist_id", "TEXT"), ("aadhaar", "TEXT"), ("pan", "TEXT"), ("address", "TEXT")]:
        try: c.execute(f"ALTER TABLE criminal_watchlist ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    for col, dtype in [("account_numbers_json", "TEXT"), ("property_reg_json", "TEXT")]:
        try: c.execute(f"ALTER TABLE fir_records ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

init_db()
upgrade_db()

# Database Helper Functions
def insert_fir(fir_no, state, station, text, mo_pattern, entities, face_hash="", accounts=[], properties=[]):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO fir_records (fir_no, state, police_station, timestamp, text_content, mo_pattern, entities_json, face_hash, account_numbers_json, property_reg_json) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (fir_no, state, station, now, text, mo_pattern, json.dumps(entities), face_hash, json.dumps(accounts), json.dumps(properties)))
    conn.commit()
    conn.close()

def insert_watchlist_criminal(wl_id, name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64, aadhaar, pan, address):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("""INSERT INTO criminal_watchlist 
                 (watchlist_id, name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash, image_b64, aadhaar, pan, address) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
              (wl_id, name, alias, state, gang, jail_record, mo_pattern, phone, vehicle, face_hash, img_b64, aadhaar, pan, address))
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
    c.execute("SELECT id, watchlist_id, name, alias, state, gang_affiliation, past_jail_record, mo_pattern, phone, vehicle, face_hash, image_b64, aadhaar, pan, address FROM criminal_watchlist ORDER BY id DESC")
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

def delete_report(record_id):
    conn = sqlite3.connect('cctns_master.db')
    conn.execute("DELETE FROM investigation_reports WHERE id=?", (record_id,))
    conn.commit()
    conn.close()

def fir_exists(fir_no):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM fir_records WHERE UPPER(fir_no) = UPPER(?)", (fir_no,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

# -----------------------------------------------------------------------------
# GRAPH STABILIZATION ENGINE (FIXES CONTINUOUS ROTATION BUG)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# HELPER UTILITIES
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
if "victim_count" not in st.session_state: st.session_state.victim_count = 1
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
    "📊 Main Dashboard & Advanced Graphs", 
    "📝 File Custom FIR (Structured)", 
    "👤 Add to Watchlist",
    "🔍 Investigation Reports (3rd DB)",
    "📂 View Master Databases"
])

st.sidebar.markdown("---")
st.sidebar.write("**Admin Controls**")
wipe_pass = st.sidebar.text_input("Database Reset Password", type="password")
if st.sidebar.button("⚠️ Wipe Master Database"):
    if wipe_pass == "9876":
        conn = sqlite3.connect('cctns_master.db')
        conn.execute("DELETE FROM fir_records")
        conn.execute("DELETE FROM criminal_watchlist")
        conn.execute("DELETE FROM investigation_reports")
        conn.commit()
        conn.close()
        st.sidebar.success("All 3 Master Databases reset successfully.")
        st.rerun()
    else: st.sidebar.error("Unauthorized Password.")

st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network & Intelligence Grid</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">All-India Multi-Entity Intelligence Grid (3-Database Engine)</div>', unsafe_allow_html=True)

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
    st.markdown("---")

    graph_tab1, graph_tab2, graph_tab3, graph_tab4, graph_tab5 = st.tabs([
        "🕸️ Main Knowledge Graph", 
        "🏢 Gangs Hierarchy Graph", 
        "🎯 Suspects Hierarchy Graph", 
        "⚠️ Risk Analysis Graph",
        "🗺️ All-India CCTNS Map"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: MAIN KNOWLEDGE GRAPH
    # -------------------------------------------------------------------------
    with graph_tab1:
        st.subheader("Global Entity Relationship Graph")
        # DEVELOPER NOTE TEXT REMOVED FROM HERE
        search_graph_fir = st.text_input("🔍 Filter Network by Specific FIR Number (Leave blank for full grid):", key="kg_fir_srch")
        
        if fir_rows or watchlist_rows:
            G = nx.Graph()
            for row in fir_rows:
                _, fir_no, state, station, timestamp, text, mo_pattern, entities_json, face_hash, acc_json, prop_json = row
                fir_no = fir_no.upper()
                entities = json.loads(entities_json)
                G.add_node(fir_no, type="FIR Record", color="#14B8A6", size=45, title=f"Case: {fir_no}\nStation: {station}")
                
                suspects = entities.get("Suspects", [])
                witnesses = entities.get("Witnesses", [])
                victims = entities.get("Victims", [])
                vehicles = entities.get("Vehicles", [])
                locations = entities.get("Locations", [])
                
                for s in suspects:
                    s_name = s["name"]
                    G.add_node(s_name, type="Suspect", rank=s.get("rank", "A1"), image=s.get("image"))
                    G.add_edge(fir_no, s_name, relation="ACCUSED_IN")
                    if s.get("phone"):
                        G.add_node(s["phone"], type="Phone", color="#3B82F6")
                        G.add_edge(s_name, s["phone"], relation="OWNS_PHONE")
                    if s.get("face_hash"):
                        G.add_node(s["face_hash"], type="Face Biometric", color="#EC4899")
                        G.add_edge(s_name, s["face_hash"], relation="FACE_MATCH")
                    for v in vehicles: G.add_edge(s_name, v["plate"], relation="LINKED_VEHICLE")
                    for l in locations: G.add_edge(s_name, l, relation="SEEN_AT")

                for w in witnesses:
                    G.add_node(w["name"], type="Witness", color="#10B981")
                    G.add_edge(fir_no, w["name"], relation="WITNESS_IN")

                for vic in victims:
                    G.add_node(vic["name"], type="Victim", color="#6366F1")
                    G.add_edge(fir_no, vic["name"], relation="VICTIM_OF")
                    if vic.get("phone"):
                        G.add_node(vic["phone"], type="Phone", color="#3B82F6")
                        G.add_edge(vic["name"], vic["phone"], relation="OWNS_PHONE")

                for v in vehicles:
                    G.add_node(v["plate"], type="Vehicle", color="#F59E0B", image=v.get("image"))
                    G.add_edge(fir_no, v["plate"], relation="LOGGED_VEHICLE")

            for w in watchlist_rows:
                _, wl_id, name, alias, state, gang, jail_rec, mo, phone, vehicle, face_hash, img_b64, aadhaar, pan, address = w
                wl_label = f"{name}\n({wl_id})" if wl_id else name
                G.add_node(wl_label, type="Suspect (Watchlist)", color="#DC2626", rank="A1", image=img_b64)
                if gang:
                    G.add_node(gang, type="Organization", color="#A855F7")
                    G.add_edge(wl_label, gang, relation="MEMBER_OF")
                if phone:
                    G.add_node(phone, type="Phone", color="#3B82F6")
                    G.add_edge(wl_label, phone, relation="KNOWN_PHONE")
                if vehicle:
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
                color = attrs.get("color", "#94A3B8")
                size = attrs.get("size", 25)
                img = attrs.get("image", None)
                kwargs = {"label": str(node), "color": color, "size": size, "title": f"Type: {ntype}"}
                if img: kwargs.update({"shape": "circularImage", "image": img})
                else: kwargs["shape"] = "dot"
                net.add_node(node, **kwargs)

            for u, v, attrs in G.edges(data=True):
                net.add_edge(u, v, label=attrs.get("relation", ""), color="#475569")

            render_pyvis_graph(net)

    # -------------------------------------------------------------------------
    # TAB 2: GANGS HIERARCHY GRAPH
    # -------------------------------------------------------------------------
    with graph_tab2:
        st.subheader("🏢 Gangs Hierarchy Network")
        gang_search = st.text_input("🔍 Search Hierarchy by Gang Name, Criminal Name, or FIR Number:", key="gang_srch")
        
        # Aggregate members by gang
        gang_map = {}
        for w in watchlist_rows:
            gang = w[5]
            if gang:
                if gang not in gang_map: gang_map[gang] = []
                gang_map[gang].append({"name": w[2], "wl_id": w[1], "jail": w[6], "source": "Watchlist", "img": w[11]})
                
        for f in fir_rows:
            entities = json.loads(f[7])
            for s in entities.get("Suspects", []):
                # Count cases for priority
                s_name = s["name"]
                # Default group if no explicit gang
                g_name = s.get("gang", "Unclassified Syndicate")
                if g_name not in gang_map: gang_map[g_name] = []
                gang_map[g_name].append({"name": s_name, "rank": s.get("rank", "A1"), "fir": f[1], "source": "FIR", "img": s.get("image")})

        if gang_map:
            HG = nx.DiGraph()
            for gname, members in gang_map.items():
                if gang_search:
                    gs = gang_search.lower()
                    match = any(gs in gname.lower() or gs in m["name"].lower() or gs in m.get("fir", "").lower() for m in members)
                    if not match: continue
                
                HG.add_node(gname, color="#8B5CF6", size=45, type="Gang Core")
                
                # Rank members: Served Jail Time > Multi-Case > A1/A2
                def calc_rank_score(m):
                    score = 0
                    if m.get("jail"): score += 100
                    if m.get("rank") == "A1": score += 50
                    elif m.get("rank") == "A2": score += 30
                    return score

                sorted_m = sorted(members, key=calc_rank_score, reverse=True)
                prev_node = gname
                for idx, m in enumerate(sorted_m):
                    m_label = f"{m['name']}\n(Rank #{idx+1})"
                    color = "#EF4444" if idx == 0 else ("#F97316" if idx == 1 else "#3B82F6")
                    HG.add_node(m_label, color=color, size=35 - (idx * 3), image=m.get("img"))
                    edge_lbl = "GANG_LEADER" if idx == 0 else f"LIEUTENANT_L{idx}"
                    HG.add_edge(prev_node, m_label, label=edge_lbl)
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

    # -------------------------------------------------------------------------
    # TAB 3: SUSPECTS HIERARCHY GRAPH (PER FIR)
    # -------------------------------------------------------------------------
    with graph_tab3:
        st.subheader("🎯 Case-Specific Suspect Hierarchy")
        fir_options = [f[1] for f in fir_rows]
        selected_fir = st.selectbox("Select FIR Number to render hierarchy:", fir_options if fir_options else ["None"])
        
        if selected_fir != "None":
            target_fir = next((f for f in fir_rows if f[1] == selected_fir), None)
            if target_fir:
                entities = json.loads(target_fir[7])
                suspects = entities.get("Suspects", [])
                
                SHG = nx.DiGraph()
                SHG.add_node(selected_fir, color="#14B8A6", size=45, type="Case FIR")
                
                # Check cross-case involvement for each suspect
                ranked_suspects = []
                for s in suspects:
                    s_name = s["name"]
                    other_cases = sum(1 for f in fir_rows if f[1] != selected_fir and s_name in [x["name"] for x in json.loads(f[7]).get("Suspects", [])])
                    in_watchlist = any(w[2].lower() == s_name.lower() for w in watchlist_rows)
                    
                    # Priority Calculation: Multi-case > Watchlist > FIR Rank A1
                    priority_score = (other_cases * 40) + (50 if in_watchlist else 0) + (30 if s.get("rank")=="A1" else 10)
                    ranked_suspects.append({"data": s, "score": priority_score, "other_cases": other_cases, "watchlist": in_watchlist})
                
                ranked_suspects.sort(key=lambda x: x["score"], reverse=True)
                
                parent = selected_fir
                for idx, item in enumerate(ranked_suspects):
                    s = item["data"]
                    label = f"[{s.get('rank','A1')}] {s['name']}\n(Score: {item['score']})"
                    color = "#EF4444" if item["watchlist"] or item["other_cases"] > 0 else "#F59E0B"
                    SHG.add_node(label, color=color, size=38 - (idx * 4), image=s.get("image"))
                    rel = "PRIME_TARGET" if idx == 0 else f"ACCUSED_L{idx+1}"
                    SHG.add_edge(parent, label, label=rel)
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

    # -------------------------------------------------------------------------
    # TAB 4: RISK ANALYSIS GRAPH
    # -------------------------------------------------------------------------
    with graph_tab4:
        st.subheader("⚠️ Criminal Risk Matrix & Threat Score")
        risk_srch = st.text_input("🔍 Search Risk Graph by Name, FIR Number, or Phone:", key="risk_srch")
        
        RG = nx.Graph()
        # Compute Risk Scores across all entities
        person_threats = {}
        for f in fir_rows:
            entities = json.loads(f[7])
            for s in entities.get("Suspects", []):
                nm = s["name"]
                if nm not in person_threats: person_threats[nm] = {"firs": [], "watchlist": False, "jail": False, "img": s.get("image")}
                person_threats[nm]["firs"].append(f[1])

        for w in watchlist_rows:
            nm = w[2]
            if nm not in person_threats: person_threats[nm] = {"firs": [], "watchlist": True, "jail": bool(w[6]), "img": w[11]}
            else:
                person_threats[nm]["watchlist"] = True
                if w[6]: person_threats[nm]["jail"] = True

        for nm, meta in person_threats.items():
            if risk_srch and not (risk_srch.lower() in nm.lower() or any(risk_srch.lower() in fir.lower() for fir in meta["firs"])):
                continue
            
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

    # -------------------------------------------------------------------------
    # TAB 5: ALL-INDIA GEOSPATIAL MAP
    # -------------------------------------------------------------------------
    with graph_tab5:
        st.subheader("All-India CCTNS Spatial Radar")
        state_counts = {}
        for row in fir_rows: state_counts[row[2]] = state_counts.get(row[2], 0) + 1
        for w in watchlist_rows: state_counts[w[4]] = state_counts.get(w[4], 0) + 1
            
        map_data = []
        for state_name, coords in STATE_COORDINATES.items():
            count = state_counts.get(state_name, 0)
            radius = 15000 + (count * 40000) if count > 0 else 10000
            color = [239, 68, 68, 200] if count > 0 else [100, 116, 139, 100]
            map_data.append({"state": state_name, "lat": coords["lat"], "lon": coords["lon"], "fir_count": count, "radius": radius, "color": color})
            
        map_df = pd.DataFrame(map_data)
        layer = pdk.Layer("ScatterplotLayer", map_df, get_position="[lon, lat]", get_fill_color="color", get_line_color="[255, 255, 255, 255]", line_width_min_pixels=1, get_radius="radius", pickable=True)
        view_state = pdk.ViewState(latitude=22.5937, longitude=78.9629, zoom=4.0, pitch=35)
        st.pydeck_chart(pdk.Deck(map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json", initial_view_state=view_state, layers=[layer], tooltip={"html": "<b>State:</b> {state}<br/><b>Active Threats:</b> {fir_count}"}))

# =============================================================================
# VIEW 2: FILE CUSTOM FIR (STRUCTURED INPUT WITH VICTIMS & ACCOUNTS)
# =============================================================================
elif action_mode == "📝 File Custom FIR (Structured)":
    st.header("📝 File New Custom FIR")
    st.caption("Supports Suspects, Witnesses, Multiple Victims, Accounts, and Properties.")
    
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c_fir_no = c1.text_input("FIR Number (Must be Unique) *", "FIR-2026-001")
        c_state = c2.selectbox("State / UT", list(STATE_COORDINATES.keys()))
        c_station = c1.text_input("Police Station", "Central Crime Branch")
        c_location = c2.text_input("Specific Crime Location", "Main Street Bank")
        fir_text = st.text_area("Case Narrative", height=100)
        
        st.markdown("---")
        st.subheader("💳 Linked Financial Bank Accounts")
        c_accounts_str = st.text_input("Enter Account Numbers (Comma-separated for multiple)", "")
        
        st.subheader("🏢 Linked Properties")
        c_properties_str = st.text_input("Enter Property Registration Numbers (Comma-separated for multiple)", "")
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
            s_aadhaar = sc3.text_input("Aadhaar Number (Optional)", key=f"s_aadh_{i}")
            s_pan = sc4.text_input("PAN Number (Optional)", key=f"s_pan_{i}")
            s_address = st.text_input(f"Home Address", key=f"s_add_{i}")
            s_details = st.text_input(f"Involvement Details", key=f"s_det_{i}")
            s_photo = st.file_uploader(f"Upload Face Photo (A{i+1})", type=["jpg", "png"], key=f"s_pic_{i}")
            if s_name:
                img_b64, img_hash = process_uploaded_image(s_photo)
                suspects_collected.append({"name": s_name, "rank": f"A{i+1}", "reason": s_details, "phone": s_phone, "image": img_b64, "face_hash": img_hash, "aadhaar": s_aadhaar, "pan": s_pan, "address": s_address})
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
            v_aadhaar = vc3.text_input("Aadhaar Number (Optional)", key=f"vic_aadh_{i}")
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
            
            if v_name:
                v_img_b64, _ = process_uploaded_image(v_pic)
                vv_img_b64, _ = process_uploaded_image(v_vpic)
                victims_collected.append({
                    "name": v_name, "phone": v_phone, "aadhaar": v_aadhaar, "pan": v_pan, "vehicle_no": v_veh_no,
                    "voter_id": v_voter, "occupation": v_occ, "address": v_address, "office_address": v_off_add,
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
            if w_name: witnesses_collected.append({"name": w_name, "phone": w_phone, "details": w_details})
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
            if v_plate or v_desc:
                img_b64, _ = process_uploaded_image(v_photo)
                vehicles_collected.append({"plate": v_plate, "description": v_desc, "image": img_b64})
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
            acc_list = [a.strip() for a in c_accounts_str.split(",") if a.strip()]
            prop_list = [p.strip() for p in c_properties_str.split(",") if p.strip()]
            
            structured_entities = {
                "Suspects": suspects_collected, "Witnesses": witnesses_collected,
                "Victims": victims_collected, "Vehicles": vehicles_collected, 
                "Locations": [c_location] if c_location else []
            }
            mo_pattern = detect_modus_operandi(fir_text)
            primary_hash = suspects_collected[0].get("face_hash", "") if suspects_collected else ""
            insert_fir(c_fir_no.upper(), c_state, c_station, fir_text, mo_pattern, structured_entities, primary_hash, acc_list, prop_list)
            st.success(f"✅ FIR {c_fir_no.upper()} ingested successfully into database!")

# =============================================================================
# VIEW 3: ADD TO WATCHLIST
# =============================================================================
elif action_mode == "👤 Add to Watchlist":
    st.header("👤 Register Criminal to Watchlist")
    with st.container():
        st.markdown('<div class="form-container">', unsafe_allow_html=True)
        wc1, wc2 = st.columns(2)
        w_name = wc1.text_input("Criminal Full Name *")
        w_alias = wc2.text_input("Alias / Moniker")
        w_state = wc1.selectbox("Operating State / UT", list(STATE_COORDINATES.keys()))
        w_gang = wc2.text_input("Gang / Terror Outfit Name")
        
        st.markdown("---")
        wc_a, wc_b = st.columns(2)
        w_aadhaar = wc_a.text_input("Aadhaar Number (Optional)")
        w_pan = wc_b.text_input("PAN Number (Optional)")
        w_address = st.text_input("Known Hideout Address")
        w_jail = st.text_input("Past Jail / Arrest Record Details")
        w_mo = st.selectbox("Known Modus Operandi (MO)", [
            "Standard Criminal Activity", "Night Theft / Roof Breach Heist", 
            "Cyber Financial Phishing Fraud", "Gang Extortion / Ransom Network", "Highway Vehicle Interception"
        ])
        wc3, wc4 = st.columns(2)
        w_phone = wc3.text_input("Known Phone Number")
        w_vehicle = wc4.text_input("Known Vehicle License Plate")
        w_photo = st.file_uploader("Upload Criminal Photo *", type=["jpg", "png", "jpeg"])
        st.markdown('</div>', unsafe_allow_html=True)
        
        if st.button("🚨 Register Profile in Watchlist", type="primary", use_container_width=True):
            if w_name:
                img_b64, img_hash = process_uploaded_image(w_photo)
                wl_id = "WL-" + datetime.now().strftime("%Y%m%d-%H%M%S")
                insert_watchlist_criminal(wl_id, w_name, w_alias, w_state, w_gang, w_jail, w_mo, w_phone, w_vehicle, img_hash, img_b64, w_aadhaar, w_pan, w_address)
                st.success(f"✅ Registered in Watchlist! Assigned Unique ID: **{wl_id}**")
            else: st.error("Full Name is required.")

# =============================================================================
# VIEW 4: INVESTIGATION REPORTS (3RD DATABASE MODULE)
# =============================================================================
elif action_mode == "🔍 Investigation Reports (3rd DB)":
    st.header("🔍 Investigation Reports Database")
    st.caption("3rd DB Engine: Multi-Source Matcher across FIRs, Watchlists, and Investigation Reports.")
    
    rep_tab1, rep_tab2, rep_tab3 = st.tabs([
        "🎥 Surveillance Reports (S1, S2...)", 
        "📞 Call Details Analysis (CDR)", 
        "💳 Financial Transaction History"
    ])

    # -------------------------------------------------------------------------
    # SUB-MODULE A: SURVEILLANCE REPORTS
    # -------------------------------------------------------------------------
    with rep_tab1:
        st.subheader("🎥 Field Surveillance Logging & Cross-Match Engine")
        with st.form("surv_form"):
            s_code = st.text_input("Report Label (e.g. S1, S2, S3)", "S1")
            s_fir = st.text_input("Linked FIR Number", "FIR-2026-001")
            s_person = st.text_input("Person Observed (Suspect / Associate)")
            s_loc = st.text_input("Surveillance Location")
            s_veh = st.text_input("Vehicle Plate / Details Observed")
            s_veh_img = st.file_uploader("Upload Observed Vehicle Photo", type=["jpg", "png"])
            s_people = st.text_input("People Seen Together (Comma-separated)")
            s_places = st.text_input("Places Frequently Visited")
            s_obs = st.text_area("Relevant Observations / Meetings")
            s_notes = st.text_area("Officer's Special Notes")
            s_ev = st.text_input("Video / Evidence File Reference (URL / ID)")
            
            submit_surv = st.form_submit_button("💾 Save Surveillance Report & Run Match Engine")

        if submit_surv:
            v_b64, _ = process_uploaded_image(s_veh_img)
            insert_investigation_report(s_code, "Surveillance", s_fir.upper(), s_person, s_loc, s_veh, v_b64, s_people, s_places, s_obs, s_notes, s_ev)
            st.success(f"Report {s_code} saved.")

            # REAL-TIME 3-DATABASE CROSS MATCH ENGINE
            st.markdown("### 🎯 Automatic Cross-Database Match Engine Results")
            all_firs = get_all_firs()
            all_watch = get_all_watchlist()

            # Match Person
            p_matches = []
            for w in all_watch:
                if s_person and (s_person.lower() in w[2].lower() or s_person.lower() in w[3].lower()):
                    p_matches.append(f"Watchlist Criminal: **{w[2]}** (ID: {w[1]}, Gang: {w[5]})")
            for f in all_firs:
                entities = json.loads(f[7])
                for s in entities.get("Suspects", []):
                    if s_person and s_person.lower() in s["name"].lower():
                        p_matches.append(f"FIR Accused: **{s['name']}** in Case **{f[1]}** ({f[3]})")

            if p_matches:
                for pm in p_matches:
                    st.markdown(f'<div class="match-card">🚨 <b>MATCH FOUND:</b> {pm}</div>', unsafe_allow_html=True)
            else: st.info("No immediate direct suspect matches found for person observed.")

            # Match Vehicle
            v_matches = []
            if s_veh:
                for w in all_watch:
                    if w[9] and s_veh.lower() in w[9].lower():
                        v_matches.append(f"Watchlist Registered Vehicle: **{w[9]}** belonging to **{w[2]}**")
                for f in all_firs:
                    entities = json.loads(f[7])
                    for v in entities.get("Vehicles", []):
                        if s_veh.lower() in v["plate"].lower():
                            v_matches.append(f"FIR Logged Vehicle: **{v['plate']}** in Case **{f[1]}**")

            if v_matches:
                for vm in v_matches:
                    st.markdown(f'<div class="match-card">🚗 <b>VEHICLE MATCH FOUND:</b> {vm}</div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # SUB-MODULE B: CALL DETAILS ANALYSIS (CDR)
    # -------------------------------------------------------------------------
    with rep_tab2:
        st.subheader("📞 CDR Phone Number Batch Intersect")
        cdr_fir = st.text_input("Target FIR Number", "FIR-2026-001")
        uploaded_txt = st.file_uploader("Upload CDR Text File (.txt)", type=["txt"])
        raw_phones_input = st.text_area("Or Paste Random Phone Numbers List (One per line or comma-separated)")

        if st.button("🔍 Run Cross-Database CDR Matcher", type="primary"):
            phone_list = []
            if uploaded_txt:
                lines = uploaded_txt.getvalue().decode("utf-8").splitlines()
                for l in lines: phone_list.extend([p.strip() for p in l.split(",") if p.strip()])
            if raw_phones_input:
                phone_list.extend([p.strip() for p in raw_phones_input.replace("\n", ",").split(",") if p.strip()])

            phone_list = list(set(phone_list))
            st.write(f"Scanned **{len(phone_list)}** unique phone numbers across 3 databases...")

            all_firs = get_all_firs()
            all_watch = get_all_watchlist()

            matched_records = []
            for ph in phone_list:
                # Check Watchlist
                for w in all_watch:
                    if w[8] and ph in w[8]:
                        matched_records.append({"phone": ph, "owner": w[2], "source": f"Watchlist ({w[1]})", "type": "Criminal Target"})
                # Check FIRs
                for f in all_firs:
                    entities = json.loads(f[7])
                    for s in entities.get("Suspects", []):
                        if s.get("phone") and ph in s["phone"]:
                            matched_records.append({"phone": ph, "owner": s["name"], "source": f"FIR {f[1]}", "type": "Suspect"})
                    for vic in entities.get("Victims", []):
                        if vic.get("phone") and ph in vic["phone"]:
                            matched_records.append({"phone": ph, "owner": vic["name"], "source": f"FIR {f[1]}", "type": "Victim"})

            if matched_records:
                st.success(f"🎯 Found {len(matched_records)} Database Matches!")
                st.dataframe(pd.DataFrame(matched_records), use_container_width=True)
            else:
                st.warning("No numbers in the provided CDR batch matched any database records.")

    # -------------------------------------------------------------------------
    # SUB-MODULE C: FINANCIAL TRANSACTION HISTORY
    # -------------------------------------------------------------------------
    with rep_tab3:
        st.subheader("💳 Financial Transaction Link Analysis")
        fc1, fc2 = st.columns(2)
        acc_from = fc1.text_input("Transaction Sender Account (Account X)")
        acc_to = fc2.text_input("Transaction Receiver Account (Account Y)")
        amount = st.number_input("Transaction Amount (₹)", min_value=0.0, value=50000.0)
        
        if st.button("🔗 Track Financial Flow & Match Entities"):
            all_firs = get_all_firs()
            all_watch = get_all_watchlist()
            
            def find_acc_owner(acc):
                owners = []
                # Check FIR Bank Accounts & PANs
                for f in all_firs:
                    accs = json.loads(f[9]) if f[9] else []
                    if acc in accs: owners.append(f"Linked to Case {f[1]} (Bank Account)")
                    entities = json.loads(f[7])
                    for s in entities.get("Suspects", []):
                        if s.get("pan") == acc: owners.append(f"Suspect {s['name']} (PAN Match in {f[1]})")
                    for v in entities.get("Victims", []):
                        if v.get("pan") == acc: owners.append(f"Victim {v['name']} (PAN Match in {f[1]})")
                # Check Watchlist PANs
                for w in all_watch:
                    if w[13] == acc: owners.append(f"Watchlist Criminal {w[2]} (PAN Match)")
                return owners

            sender_matches = find_acc_owner(acc_from)
            receiver_matches = find_acc_owner(acc_to)

            c_s, c_r = st.columns(2)
            with c_s:
                st.markdown(f"#### Sender (Account X: `{acc_from}`)")
                if sender_matches:
                    for sm in sender_matches: st.markdown(f'<div class="match-card"><b>SENDER MATCH:</b> {sm}</div>', unsafe_allow_html=True)
                else: st.info("No database matches for Sender account/PAN.")
                
            with c_r:
                st.markdown(f"#### Receiver (Account Y: `{acc_to}`)")
                if receiver_matches:
                    for rm in receiver_matches: st.markdown(f'<div class="match-card"><b>RECEIVER MATCH:</b> {rm}</div>', unsafe_allow_html=True)
                else: st.info("No database matches for Receiver account/PAN.")

# =============================================================================
# VIEW 5: VIEW MASTER DATABASES (3-DATABASE EXPLORER)
# =============================================================================
elif action_mode == "📂 View Master Databases":
    st.header("📂 Master Database Explorer")
    
    t_firs, t_watch, t_reps = st.tabs(["📄 FIR Database", "👤 Watchlist Database", "🔍 Investigation Reports DB"])
    
    with t_firs:
        srch = st.text_input("Search FIR Number:", key="v_fir_s")
        rows = get_all_firs()
        if srch: rows = [r for r in rows if srch.upper() in r[1].upper()]
        for r in rows:
            with st.expander(f"📄 {r[1]} | {r[3]}, {r[2]} | MO: {r[6]}"):
                st.write(f"**Timestamp:** {r[4]}")
                st.write(f"**Narrative:** {r[5]}")
                st.write(f"**Bank Accounts:** {r[9]}")
                st.write(f"**Property Registrations:** {r[10]}")
                entities = json.loads(r[7])
                st.json(entities)
                dpass = st.text_input("Password", type="password", key=f"df_p_{r[0]}")
                if st.button("❌ Delete FIR", key=f"df_b_{r[0]}"):
                    if dpass == "0123": delete_fir(r[0]); st.rerun()
                    else: st.error("Invalid Password")

    with t_watch:
        srch = st.text_input("Search Watchlist ID:", key="v_wl_s")
        wrows = get_all_watchlist()
        if srch: wrows = [w for w in wrows if w[1] and srch.upper() in w[1].upper()]
        for w in wrows:
            with st.expander(f"🚨 {w[2]} (Alias: {w[3]}) | ID: {w[1]}"):
                st.write(f"**Gang:** {w[5]} | **State:** {w[4]}")
                st.write(f"**Jail Record:** {w[6]}")
                if w[12]: st.write(f"**Aadhaar:** {w[12]}")
                if w[13]: st.write(f"**PAN:** {w[13]}")
                dpass = st.text_input("Password", type="password", key=f"dw_p_{w[0]}")
                if st.button("❌ Delete Watchlist Profile", key=f"dw_b_{w[0]}"):
                    if dpass == "0123": delete_watchlist(w[0]); st.rerun()
                    else: st.error("Invalid Password")

    with t_reps:
        rrows = get_all_reports()
        for rep in rrows:
            with st.expander(f"🔍 [{rep[2]}] Report Code: {rep[1]} | Case: {rep[3]}"):
                st.write(f"**Person Observed:** {rep[4]}")
                st.write(f"**Location:** {rep[6]}")
                st.write(f"**Observations:** {rep[11]}")
                dpass = st.text_input("Password", type="password", key=f"dr_p_{rep[0]}")
                if st.button("❌ Delete Report", key=f"dr_b_{rep[0]}"):
                    if dpass == "0123": delete_report(rep[0]); st.rerun()
                    else: st.error("Invalid Password")
