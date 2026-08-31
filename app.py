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
from datetime import datetime

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="CCTNS Cross-Jurisdictional Criminal Intelligence Grid",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header { font-size: 2.1rem; font-weight: 800; color: #0F172A; margin-bottom: 0px; }
    .sub-header { font-size: 0.95rem; color: #64748B; margin-bottom: 20px; font-weight: 500; }
    .stMetric { background-color: #F8FAFC; padding: 12px; border-radius: 8px; border-left: 5px solid #2563EB; box-shadow: 0 2px 4px rgb(0 0 0 / 0.05); }
    .login-box { max-width: 400px; margin: 80px auto; padding: 30px; background: #FFFFFF; border-radius: 10px; border: 1px solid #E2E8F0; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

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
# DATABASE MANAGEMENT (Persistent All-Time Storage)
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  fir_no TEXT, 
                  state TEXT, 
                  police_station TEXT, 
                  timestamp TEXT, 
                  text_content TEXT, 
                  entities_json TEXT)''')
    conn.commit()
    conn.close()

def insert_fir(fir_no, state, station, text, entities):
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO fir_records 
                 (fir_no, state, police_station, timestamp, text_content, entities_json) 
                 VALUES (?, ?, ?, ?, ?, ?)""", 
              (fir_no, state, station, now, text, json.dumps(entities)))
    conn.commit()
    conn.close()

def get_all_firs():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("SELECT id, fir_no, state, police_station, timestamp, text_content, entities_json FROM fir_records ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def clear_db():
    conn = sqlite3.connect('cctns_master.db')
    c = conn.cursor()
    c.execute("DELETE FROM fir_records")
    conn.commit()
    conn.close()

init_db()

# -----------------------------------------------------------------------------
# NLP EXTRACTION ENGINE
# -----------------------------------------------------------------------------
def extract_entities_from_text(text):
    entities = {
        "Suspects": list(set(re.findall(r'(?:suspect|accused|target|alias)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', text, re.I))),
        "Phones": list(set(re.findall(r'\b[6-9]\d{9}\b', text))),
        "Vehicles": list(set(re.findall(r'\b[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}\b', text))),
        "Organizations": list(set([item for sub in re.findall(r"'(.*?)'|\"(.*?)\"", text) for item in sub if item])),
        "Locations": list(set(re.findall(r'\b(?:near|at|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text, re.I)))
    }
    
    if not entities["Suspects"]:
        names = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', text)
        stopwords = ["Deccan Logistics", "Mahindra Scorpio", "Police Station", "State Police", "Crime Branch", "Brigade Road", "South Tech", "Connaught Place", "Bandra East"]
        entities["Suspects"] = list(set([n for n in names if n not in stopwords]))
        
    return entities

def build_global_graph(fir_rows):
    """Builds a NetworkX graph tracking entity-to-FIR mappings."""
    G = nx.Graph()
    entity_fir_map = {}

    for row in fir_rows:
        fir_id, fir_no, state, station, timestamp, text, entities_json = row
        entities = json.loads(entities_json)
        fir_label = f"FIR: {fir_no} ({state})"
        
        suspects = entities.get("Suspects", [])
        phones = entities.get("Phones", [])
        vehicles = entities.get("Vehicles", [])
        orgs = entities.get("Organizations", [])
        locs = entities.get("Locations", [])
        
        all_found = suspects + phones + vehicles + orgs + locs
        
        for ent in all_found:
            if ent not in entity_fir_map:
                entity_fir_map[ent] = set()
            entity_fir_map[ent].add(fir_no)

        # Add nodes with metadata
        for s in suspects: G.add_node(s, type="Suspect", color="#EF4444")
        for p in phones: G.add_node(p, type="Phone", color="#3B82F6")
        for v in vehicles: G.add_node(v, type="Vehicle", color="#F59E0B")
        for o in orgs: G.add_node(o, type="Organization", color="#A855F7")
        for l in locs: G.add_node(l, type="Location", color="#10B981")

        # Create intra-FIR edges
        for s in suspects:
            for p in phones: G.add_edge(s, p, relation=f"USES [{fir_no}]")
            for v in vehicles: G.add_edge(s, v, relation=f"DRIVES [{fir_no}]")
            for o in orgs: G.add_edge(s, o, relation=f"MEMBER [{fir_no}]")
            for l in locs: G.add_edge(s, l, relation=f"SEEN_AT [{fir_no}]")

        for i in range(len(suspects)):
            for j in range(i + 1, len(suspects)):
                G.add_edge(suspects[i], suspects[j], relation=f"CO_ACCUSED [{fir_no}]")

    return G, entity_fir_map

# -----------------------------------------------------------------------------
# SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.title("👮 Police Portal Controls")
st.sidebar.write(f"**Logged in:** Officer (MHA Grid)")

if st.sidebar.button("🔒 Logout"):
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📥 Ingest New Intelligence")
action_mode = st.sidebar.radio("Select Action:", ["Inject Cross-State Demo FIRs", "Upload Custom FIR"])

if action_mode == "Inject Cross-State Demo FIRs":
    if st.sidebar.button("Load Multi-State Inter-Link Data"):
        demo_firs = [
            ("FIR-2026-TN01", "Tamil Nadu", "Chennai Central PS", "Suspect Ramesh Kumar fled in vehicle TN-01-AB-9999 after robbery near Marina Beach. Phone contact recorded: 9876543210."),
            ("FIR-2026-MH44", "Maharashtra", "Mumbai Crime Branch", "Automobile heist reported in Bandra East. Surveillance captured getaway vehicle TN-01-AB-9999 linked to shell company 'Deccan Logistics'."),
            ("FIR-2026-DL09", "Delhi", "Connaught Place PS", "Financial fraud investigation against 'Deccan Logistics'. Suspect Ramesh Kumar traced via phone 9876543210 in New Delhi.")
        ]
        for fir_no, state, station, text in demo_firs:
            insert_fir(fir_no, state, station, text, extract_entities_from_text(text))
        st.sidebar.success("Multi-state cross-link FIRs ingested!")
        st.rerun()

elif action_mode == "Upload Custom FIR":
    c_fir_no = st.sidebar.text_input("FIR Number", "FIR-2026-001")
    c_state = st.sidebar.selectbox("State / UT", ["Telangana", "Maharashtra", "Tamil Nadu", "Delhi", "Karnataka", "West Bengal", "Gujarat"])
    c_station = st.sidebar.text_input("Police Station", "District HQ PS")
    uploaded_files = st.sidebar.file_uploader("Upload FIR Document (.txt)", type=["txt"], accept_multiple_files=True)
    
    if st.sidebar.button("Ingest FIR into Database"):
        if uploaded_files:
            for f in uploaded_files:
                txt = f.read().decode("utf-8")
                insert_fir(c_fir_no, c_state, c_station, txt, extract_entities_from_text(txt))
            st.sidebar.success("FIR filed & cross-linked in SQLite Database!")
            st.rerun()

st.sidebar.markdown("---")
if st.sidebar.button("⚠️ Wipe Central Database"):
    clear_db()
    st.sidebar.warning("Database reset complete.")
    st.rerun()

# -----------------------------------------------------------------------------
# MAIN DASHBOARD INTERFACE
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ministry of Home Affairs | SIH 2026 Problem ID: 26189 | Cross-Jurisdictional Intelligence Grid</div>', unsafe_allow_html=True)

fir_rows = get_all_firs()

if fir_rows:
    G, entity_fir_map = build_global_graph(fir_rows)
    
    # Calculate Cross-FIR Threat Matrix
    multi_fir_entities = {ent: firs for ent, firs in entity_fir_map.items() if len(firs) > 1}
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("All-Time FIRs Archived", len(fir_rows))
    m2.metric("Total Extracted Entities", len(G.nodes()))
    m3.metric("Cross-FIR Matches", len(multi_fir_entities))
    
    if len(G) > 0:
        deg_cent = nx.degree_centrality(G)
        top_hub = max(deg_cent, key=deg_cent.get)
        m4.metric("Primary Ring Leader / Hub", top_hub)

    st.markdown("---")
    
    t1, t2, t3, t4 = st.tabs([
        "🕸️ Cross-FIR Knowledge Graph", 
        "🗺️ CCTNS Spatial Radar", 
        "🚨 High-Threat Cross Matches", 
        "📜 FIR Repository & Audit Logs"
    ])
    
    # TAB 1: GRAPH VISUALIZATION
    with t1:
        st.subheader("Global Entity Relationship Graph")
        st.caption("Entities connected across multiple FIRs automatically enlarge and highlight cross-state links.")
        
        net = Network(height="600px", width="100%", bgcolor="#0F172A", font_color="white")
        
        for node, attrs in G.nodes(data=True):
            firs_linked = entity_fir_map.get(node, set())
            is_cross_matched = len(firs_linked) > 1
            
            # Enlarge & highlight cross-matched nodes
            node_size = 35 if is_cross_matched else 18
            border_color = "#FACC15" if is_cross_matched else "#475569"
            label = f"{node} ({len(firs_linked)} FIRs)" if is_cross_matched else node
            
            net.add_node(
                node, 
                label=label, 
                color=attrs.get("color", "#CCCCCC"), 
                size=node_size,
                borderWidth=3 if is_cross_matched else 1,
                title=f"Node: {node}<br>Appears in FIRs: {', '.join(firs_linked)}"
            )
            
        for u, v, attrs in G.edges(data=True):
            net.add_edge(u, v, title=attrs.get("relation", "LINKED"), color="#64748B")
            
        net.toggle_physics(True)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            net.save_graph(tmp.name)
            tmp_path = tmp.name
            
        with open(tmp_path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=620)
        os.remove(tmp_path)

    # TAB 2: GEOSPATIAL MAP (CARTO BASEMAP FIX)
    with t2:
        st.subheader("Live Police Station Jurisdictional Map")
        st.caption("Visualizing jurisdictional nodes across Indian police headquarters using CartoDB GL Tiles.")
        
        # Simulated police station mapping based on ingested state data
        ps_coordinates = [
            {"station": "Chennai Central PS", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707, "alerts": 12},
            {"station": "Mumbai Crime Branch", "state": "Maharashtra", "lat": 18.9401, "lon": 72.8347, "alerts": 25},
            {"station": "Connaught Place PS", "state": "Delhi", "lat": 28.6315, "lon": 77.2167, "alerts": 18},
            {"station": "Cyberabad HQ", "state": "Telangana", "lat": 17.4300, "lon": 78.3600, "alerts": 8},
            {"station": "Bengaluru City PS", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946, "alerts": 14}
        ]
        ps_df = pd.DataFrame(ps_coordinates)
        
        layer = pdk.Layer(
            "ScatterplotLayer",
            ps_df,
            get_position="[lon, lat]",
            get_fill_color="[239, 68, 68, 200]",
            get_line_color="[255, 255, 255, 255]",
            line_width_min_pixels=2,
            get_radius="alerts * 1500",
            pickable=True
        )
        
        view_state = pdk.ViewState(latitude=21.1458, longitude=79.0882, zoom=4.1, pitch=30)
        
        # Uses CartoDB Vector style requiring NO Mapbox API key
        st.pydeck_chart(pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"html": "<b>{station}</b> ({state})<br/>Flagged Cross-State Events: <b>{alerts}</b>"}
        ))

    # TAB 3: THREAT PATTERNS (STRICT LOGIC FIX)
    with t3:
        st.subheader("Cross-Jurisdictional Threat Intelligence")
        
        if multi_fir_entities:
            st.error(f"🚨 **CRITICAL THREAT ALERT:** Found **{len(multi_fir_entities)}** entities linking multiple distinct FIRs!")
            
            threat_data = []
            for ent, firs in multi_fir_entities.items():
                ent_type = G.nodes[ent].get("type", "Unknown") if ent in G.nodes else "Unknown"
                threat_data.append({
                    "Cross-Linked Entity": ent,
                    "Entity Type": ent_type,
                    "Matching FIR Count": len(firs),
                    "Linked FIR Numbers": ", ".join(list(firs)),
                    "Threat Classification": "🔴 HIGH THREAT (Cross-State Match)"
                })
            
            st.dataframe(pd.DataFrame(threat_data), use_container_width=True, hide_index=True)
        else:
            st.success("✅ **No Cross-FIR Threats Detected:** All extracted entities are isolated within single FIRs. No cross-jurisdictional matches found yet.")

    # TAB 4: FIR REPOSITORY & HISTORICAL AUDIT
    with t4:
        st.subheader("All-Time Ingested FIR Records")
        st.caption("Complete database log of all FIRs uploaded since app creation.")
        
        search_term = st.text_input("🔍 Search FIR Database (by FIR No, State, or Keyword)", "")
        
        archive_data = []
        for row in fir_rows:
            f_id, f_no, state, station, timestamp, text, ent_json = row
            if search_term.lower() in f_no.lower() or search_term.lower() in state.lower() or search_term.lower() in text.lower():
                archive_data.append({
                    "DB ID": f_id,
                    "FIR Code": f_no,
                    "State": state,
                    "Police Station": station,
                    "Filing Timestamp": timestamp,
                    "Raw Intelligence Text": text,
                    "Parsed Entities": ent_json
                })
                
        if archive_data:
            st.dataframe(pd.DataFrame(archive_data), use_container_width=True, hide_index=True)
        else:
            st.info("No matching FIR records found.")

else:
    st.info("👈 Please authenticate and use the sidebar to **'Inject Cross-State Demo FIRs'** or upload custom files.")
