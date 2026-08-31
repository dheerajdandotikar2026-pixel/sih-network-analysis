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

# Set Page Config
st.set_page_config(
    page_title="CCTNS Criminal Network Analyzer",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (MHA Dark Theme Elements)
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 800; color: #0F172A; margin-bottom: 0px; }
    .sub-header { font-size: 1.1rem; color: #475569; margin-bottom: 25px; font-weight: 500; }
    .stMetric { background-color: #F1F5F9; padding: 15px; border-radius: 8px; border-left: 5px solid #3B82F6; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# DATABASE MANAGEMENT (Cross-FIR Linking)
# -----------------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('cctns_prototype.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS fir_records
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, text_content TEXT, entities_json TEXT)''')
    conn.commit()
    conn.close()

def insert_fir(text, entities):
    conn = sqlite3.connect('cctns_prototype.db')
    c = conn.cursor()
    c.execute("INSERT INTO fir_records (text_content, entities_json) VALUES (?, ?)", 
              (text, json.dumps(entities)))
    conn.commit()
    conn.close()

def get_all_records():
    conn = sqlite3.connect('cctns_prototype.db')
    c = conn.cursor()
    c.execute("SELECT entities_json FROM fir_records")
    rows = c.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]

def clear_db():
    conn = sqlite3.connect('cctns_prototype.db')
    c = conn.cursor()
    c.execute("DELETE FROM fir_records")
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# -----------------------------------------------------------------------------
# NLP & ENTITY EXTRACTION
# -----------------------------------------------------------------------------
def extract_entities_from_text(text):
    entities = {
        "Suspects": list(set(re.findall(r'(?:suspect|accused|target|alias)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', text, re.I))),
        "Phones": list(set(re.findall(r'\b[6-9]\d{9}\b', text))),
        "Vehicles": list(set(re.findall(r'\b[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}\b', text))),
        "Organizations": list(set([item for sub in re.findall(r"'(.*?)'|\"(.*?)\"", text) for item in sub if item])),
        "Locations": list(set(re.findall(r'\b(?:near|at|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text, re.I)))
    }
    # Fallback suspect search
    if not entities["Suspects"]:
        names = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', text)
        stopwords = ["Deccan Logistics", "Mahindra Scorpio", "Charminar Hyderabad", "Police Report", "Brigade Road", "South Tech Traders"]
        entities["Suspects"] = list(set([n for n in names if n not in stopwords]))
    return entities

def build_graph_from_entities(all_records):
    G = nx.Graph()
    for record in all_records:
        suspects, phones, vehicles = record.get("Suspects", []), record.get("Phones", []), record.get("Vehicles", [])
        orgs, locs = record.get("Organizations", []), record.get("Locations", [])
        
        for s in suspects: G.add_node(s, type="Suspect", color="#EF4444")
        for p in phones: G.add_node(p, type="Phone", color="#3B82F6")
        for v in vehicles: G.add_node(v, type="Vehicle", color="#F59E0B")
        for o in orgs: G.add_node(o, type="Organization", color="#A855F7")
        for l in locs: G.add_node(l, type="Location", color="#10B981")
        
        for s in suspects:
            for p in phones: G.add_edge(s, p, relation="USES")
            for v in vehicles: G.add_edge(s, v, relation="DRIVES")
            for o in orgs: G.add_edge(s, o, relation="ASSOCIATED")
            for l in locs: G.add_edge(s, l, relation="LOCATED")
            
        for i in range(len(suspects)):
            for j in range(i + 1, len(suspects)):
                G.add_edge(suspects[i], suspects[j], relation="CO_SUSPECT")
    return G

# -----------------------------------------------------------------------------
# APP HEADER & SIDEBAR
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🛡️ CCTNS AI Criminal Network Analyzer</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Ministry of Home Affairs | SIH Problem ID: 26189 | Cross-Jurisdictional Intelligence</div>', unsafe_allow_html=True)

st.sidebar.title("📥 Central Database Ingestion")
data_source = st.sidebar.radio("Action:", ["Upload New FIR", "Inject SIH Demo Data"])

if data_source == "Inject SIH Demo Data":
    if st.sidebar.button("Inject Multi-State Data"):
        sample_texts = [
            "FIR 1 (Hyderabad PS): Suspect Rahul Sharma exchanged bags near Charminar. Phone: 9876543210. Vehicle: TS-09-AB-1234.",
            "FIR 2 (Bengaluru PS): Suspect Priya Nair stopped in vehicle TS-09-AB-1234 on Brigade Road. Phone: 9123456781.",
            "FIR 3 (Delhi PS): Financial audit on South Tech Traders links to phone 9876543210 and suspect Amit Singh."
        ]
        for text in sample_texts:
            insert_fir(text, extract_entities_from_text(text))
        st.sidebar.success("Cross-state data injected into database!")

elif data_source == "Upload New FIR":
    uploaded_files = st.sidebar.file_uploader("Upload FIR (Links automatically to past FIRs)", type=["txt"], accept_multiple_files=True)
    if uploaded_files:
        if st.sidebar.button("Process & Save to Database"):
            for file in uploaded_files:
                content = file.read().decode("utf-8")
                insert_fir(content, extract_entities_from_text(content))
            st.sidebar.success("FIR(s) saved and cross-linked globally!")

st.sidebar.markdown("---")
if st.sidebar.button("⚠️ Wipe Database (Reset)"):
    clear_db()
    st.sidebar.warning("Database cleared.")

# -----------------------------------------------------------------------------
# DASHBOARD LOGIC
# -----------------------------------------------------------------------------
records = get_all_records()

if records:
    G = build_graph_from_entities(records)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total FIRs Processed", len(records))
    col2.metric("Total Extracted Entities", len(G.nodes()))
    
    suspect_count = len([n for n, d in G.nodes(data=True) if d.get('type') == 'Suspect'])
    col3.metric("Monitored Suspects", suspect_count)
    
    if len(G) > 0:
        deg_centrality = nx.degree_centrality(G)
        top_influencer = max(deg_centrality, key=deg_centrality.get) if deg_centrality else "N/A"
        col4.metric("Primary Hub Entity", top_influencer)
    
    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🕸️ Global Knowledge Graph", "🗺️ Geospatial CCTNS Mapping", "📊 Intelligence Analytics", "🚨 Threat Patterns"])
    
    with tab1:
        st.subheader("Cross-FIR Network Graph")
        st.caption("Nodes automatically link across different FIRs if they share data (e.g., same phone, same vehicle).")
        
        net = Network(height="600px", width="100%", bgcolor="#0F172A", font_color="white")
        for node, attrs in G.nodes(data=True):
            net.add_node(node, label=node, color=attrs.get("color", "#CCCCCC"), size=25)
        for u, v, attrs in G.edges(data=True):
            net.add_edge(u, v, title=attrs.get("relation", "CONNECTED"), color="#475569")
            
        net.toggle_physics(True)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
            net.save_graph(tmp_file.name)
            tmp_path = tmp_file.name
            
        with open(tmp_path, 'r', encoding='utf-8') as f:
            components.html(f.read(), height=620)
        os.remove(tmp_path)
        
    with tab2:
        st.subheader("Live Police Station Jurisdictions (Simulated CCTNS Nodes)")
        st.caption("Visualizing major law enforcement headquarters connected to the intelligence grid.")
        
        # Simulated Police Station Geodata for SIH Prototype
        ps_data = pd.DataFrame([
            {"station": "Delhi Police HQ", "lat": 28.6271, "lon": 77.2148, "alerts": 50},
            {"station": "Cyberabad Commissionerate", "lat": 17.4300, "lon": 78.3600, "alerts": 35},
            {"station": "Mumbai Crime Branch", "lat": 18.9401, "lon": 72.8347, "alerts": 42},
            {"station": "Bengaluru City Police", "lat": 12.9806, "lon": 77.5973, "alerts": 28},
            {"station": "Chennai Police HQ", "lat": 13.0827, "lon": 80.2707, "alerts": 15}
        ])
        
        layer = pdk.Layer(
            "ScatterplotLayer",
            ps_data,
            get_position="[lon, lat]",
            get_color="[200, 30, 0, 160]",
            get_radius="alerts * 1000",
            pickable=True
        )
        
        view_state = pdk.ViewState(latitude=20.5937, longitude=78.9629, zoom=3.5, pitch=40)
        
        st.pydeck_chart(pdk.Deck(
            map_style="mapbox://styles/mapbox/dark-v10",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"text": "{station}\nActive Network Flags: {alerts}"}
        ))

    with tab3:
        st.subheader("Entity Risk Matrix")
        if len(G) > 0:
            deg_cent, bet_cent = nx.degree_centrality(G), nx.betweenness_centrality(G)
            df = pd.DataFrame({
                "Entity": list(G.nodes()),
                "Type": [G.nodes[n].get("type", "Unknown") for n in G.nodes()],
                "FIR Occurrences (Degree)": [G.degree(n) for n in G.nodes()],
                "Brokerage Score (Betweenness)": [round(bet_cent[n], 3) for n in G.nodes()]
            }).sort_values(by="FIR Occurrences (Degree)", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab4:
        st.subheader("Cross-Jurisdictional Alerts")
        high_risk = [n for n in G.nodes() if G.degree(n) >= 2]
        if high_risk:
            st.error(f"🚨 **High-Risk Shared Entities:** `{', '.join(high_risk)}` appeared in multiple distinct queries or FIRs.")
        else:
            st.info("No cross-linked anomalies detected in the current database.")

else:
    st.info("👈 Upload an FIR file or Inject SIH Demo Data to populate the intelligence database.")
