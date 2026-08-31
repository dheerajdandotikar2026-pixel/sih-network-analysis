import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
import re
import tempfile
import os

# Set Page Config
st.set_page_config(
    page_title="AI Criminal Network Analyzer | SIH 2026",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (SIH Theme)
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E293B; margin-bottom: 0px; }
    .sub-header { font-size: 1rem; color: #64748B; margin-bottom: 20px; }
    .stMetric { background-color: #F8FAFC; padding: 15px; border-radius: 10px; border: 1px solid #E2E8F0; }
    .entity-tag { display: inline-block; padding: 3px 8px; border-radius: 5px; font-weight: 600; font-size: 0.85rem; margin: 2px; }
    .tag-suspect { background-color: #FEE2E2; color: #991B1B; }
    .tag-phone { background-color: #DBEAFE; color: #1E40AF; }
    .tag-location { background-color: #DCFCE7; color: #166534; }
    .tag-vehicle { background-color: #FEF3C7; color: #92400E; }
    .tag-org { background-color: #F3E8FF; color: #6B21A8; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# NLP & ENTITY EXTRACTION ENGINE
# -----------------------------------------------------------------------------
def extract_entities_from_text(text):
    """Extract structured entities and relationships from raw unstructured text."""
    entities = {
        "Suspects": list(set(re.findall(r'(?:suspect|accused|target|alias)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', text, re.I))),
        "Phones": list(set(re.findall(r'\b[6-9]\d{9}\b', text))),
        "Vehicles": list(set(re.findall(r'\b[A-Z]{2}[-\s]?\d{2}[-\s]?[A-Z]{1,2}[-\s]?\d{4}\b', text))),
        "Organizations": list(set([item for sub in re.findall(r"'(.*?)'|\"(.*?)\"", text) for item in sub if item])),
        "Locations": list(set(re.findall(r'\b(?:near|at|in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b', text, re.I)))
    }
    
    # Fallback suspect search if strict pattern misses
    if not entities["Suspects"]:
        names = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', text)
        stopwords = ["Deccan Logistics", "Mahindra Scorpio", "Charminar Hyderabad", "Police Report"]
        entities["Suspects"] = list(set([n for n in names if n not in stopwords]))
        
    return entities

def build_graph_from_entities(all_records):
    """Build a NetworkX Graph from extracted entities."""
    G = nx.Graph()
    
    for idx, record in enumerate(all_records):
        doc_id = f"FIR_{idx+1}"
        
        # Collect nodes
        suspects = record.get("Suspects", [])
        phones = record.get("Phones", [])
        vehicles = record.get("Vehicles", [])
        orgs = record.get("Organizations", [])
        locs = record.get("Locations", [])
        
        # Add nodes with types
        for s in suspects: G.add_node(s, type="Suspect", color="#EF4444")
        for p in phones: G.add_node(p, type="Phone", color="#3B82F6")
        for v in vehicles: G.add_node(v, type="Vehicle", color="#F59E0B")
        for o in orgs: G.add_node(o, type="Organization", color="#A855F7")
        for l in locs: G.add_node(l, type="Location", color="#10B981")
        
        # Connect Suspects to all their associated attributes in the FIR
        for s in suspects:
            for p in phones: G.add_edge(s, p, relation="USES_PHONE")
            for v in vehicles: G.add_edge(s, v, relation="DRIVES")
            for o in orgs: G.add_edge(s, o, relation="ASSOCIATED_WITH")
            for l in locs: G.add_edge(s, l, relation="SPOTTED_AT")
            
        # Connect suspects mentioned in the same report
        for i in range(len(suspects)):
            for j in range(i + 1, len(suspects)):
                G.add_edge(suspects[i], suspects[j], relation="CO_SUSPECT")
                
    return G

# -----------------------------------------------------------------------------
# APP HEADER & SIDEBAR
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🛡️ AI Criminal Network Analysis System</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">SIH 2026 Problem ID: 26189 | Law Enforcement Intelligence Dashboard</div>', unsafe_allow_html=True)

st.sidebar.title("📥 Data Ingestion Panel")
data_source = st.sidebar.radio("Select Input Source:", ["Upload FIR Files", "Load SIH Demo Dataset"])

records = []

if data_source == "Load SIH Demo Dataset":
    st.sidebar.success("Demo dataset loaded!")
    sample_texts = [
        "On 12-Aug-2026, suspect Rahul Sharma was seen exchanging a bag with unknown individual near Charminar. Rahul's phone number is 9876543210. He is associated with front company 'Deccan Logistics' and drives a white Mahindra Scorpio (TS-09-AB-1234).",
        "Interception report: Phone 9876543210 made 14 calls to 9123456789 registered to Vikram Reddy. Vikram was spotted at Hitech City meeting suspect Rahul Sharma.",
        "Financial audit flagged 'Deccan Logistics' transferring ₹50,000,000 to offshore entity. Suspect Vikram Reddy is listed as a co-director of 'Deccan Logistics'."
    ]
    for text in sample_texts:
        records.append(extract_entities_from_text(text))

else:
    uploaded_files = st.sidebar.file_uploader("Upload FIR / Intelligence Text Files", type=["txt"], accept_multiple_files=True)
    if uploaded_files:
        for file in uploaded_files:
            content = file.read().decode("utf-8")
            records.append(extract_entities_from_text(content))

# -----------------------------------------------------------------------------
# DASHBOARD LOGIC
# -----------------------------------------------------------------------------
if records:
    G = build_graph_from_entities(records)
    
    # Core Metrics Header
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Identified Entities", len(G.nodes()))
    col2.metric("Inter-Entity Connections", len(G.edges()))
    
    suspect_count = len([n for n, d in G.nodes(data=True) if d.get('type') == 'Suspect'])
    col3.metric("Key Suspects", suspect_count)
    
    # Calculate Centrality
    if len(G) > 0:
        deg_centrality = nx.degree_centrality(G)
        top_influencer = max(deg_centrality, key=deg_centrality.get) if deg_centrality else "N/A"
        col4.metric("Prime Ringleader / Key Hub", top_influencer)
    
    st.markdown("---")
    
    # Tabs Layout
    tab1, tab2, tab3 = st.tabs(["🕸️ Interactive Network Graph", "📊 Entity & Centrality Analysis", "🚨 Suspicious Patterns"])
    
    with tab1:
        st.subheader("Multi-Source Link Analysis Graph")
        
        # Legend
        st.markdown("""
        **Node Types:** 
        🔴 **Suspect** | 🔵 **Phone** | 🟢 **Location** | 🟡 **Vehicle** | 🟣 **Organization**
        """)
        
        # Render PyVis Graph
        net = Network(height="550px", width="100%", bgcolor="#1E293B", font_color="white")
        
        for node, attrs in G.nodes(data=True):
            net.add_node(node, label=node, color=attrs.get("color", "#CCCCCC"), size=20)
            
        for u, v, attrs in G.edges(data=True):
            net.add_edge(u, v, title=attrs.get("relation", "CONNECTED"))
            
        net.toggle_physics(True)
        
        # Save to temporary html file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp_file:
            net.save_graph(tmp_file.name)
            tmp_path = tmp_file.name
            
        with open(tmp_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        components.html(html_content, height=570)
        os.remove(tmp_path)
        
    with tab2:
        st.subheader("Key Influencer Ranking (Network Centrality)")
        
        if len(G) > 0:
            deg_cent = nx.degree_centrality(G)
            bet_cent = nx.betweenness_centrality(G)
            
            centrality_df = pd.DataFrame({
                "Entity": list(G.nodes()),
                "Entity Type": [G.nodes[n].get("type", "Unknown") for n in G.nodes()],
                "Connections Count": [G.degree(n) for n in G.nodes()],
                "Degree Centrality": [round(deg_cent[n], 3) for n in G.nodes()],
                "Betweenness Centrality (Brokerage)": [round(bet_cent[n], 3) for n in G.nodes()]
            }).sort_values(by="Degree Centrality", ascending=False)
            
            st.dataframe(centrality_df, use_container_width=True, hide_index=True)

    with tab3:
        st.subheader("Automated Suspicious Pattern Flags")
        
        # Pattern 1: High Connection Nodes
        high_risk = [n for n in G.nodes() if G.degree(n) >= 3]
        if high_risk:
            st.error(f"⚠️ **High-Risk Network Hubs Detected:** Entities `{', '.join(high_risk)}` are cross-linked across multiple data sources.")
            
        # Pattern 2: Shared Attributes between Suspects
        phones = [n for n, d in G.nodes(data=True) if d.get("type") == "Phone"]
        shared_phones = [p for p in phones if G.degree(p) > 1]
        if shared_phones:
            st.warning(f"⚠️ **Shared Communication Endpoint:** Phone numbers `{', '.join(shared_phones)}` are utilized by multiple suspects.")
            
        if not high_risk and not shared_phones:
            st.info("No immediate high-conspiratorial patterns flagged in current dataset.")

else:
    st.info("👈 Please upload FIR text files or select **'Load SIH Demo Dataset'** from the sidebar to visualize the intelligence network.")
