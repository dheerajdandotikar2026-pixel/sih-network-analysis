import streamlit as st
import networkx as nx
import pyvis
from pyvis.network import Network
import pandas as pd

# Set the dark mode theme for Streamlit
st.set_page_config(page_title="Criminal Network Analysis", page_icon=":gear:", layout="wide",
initial_sidebar_state="expanded",)

# Create a sidebar to upload new FIR text files
st.sidebar.title("Upload FIR Text Files")
uploaded_file = st.sidebar.file_uploader("Select FIR text file", type=["txt"])

# Create a main window to display the network graph
if uploaded_file:
    # Read the FIR text file
    fir_data = pd.read_csv(uploaded_file, delimiter=";", header=None, names=["Node", "Type", "Weight"])

    # Create a NetworkX graph from the FIR data
    G = nx.from_pandas_edgelist(fir_data, source="Node", target="Node", edge_attr="Weight", create_using=nx.Graph)

    # Create a pyvis network object
    n = Network(height="800px", width="800px", directed=True)
    n.from_nx(G)

    # Render the interactive network graph
    st.write(n)
    n.show("Criminal Network Analysis")

    # Create a sidebar section to list the top 3 'Key Influencers'
    st.sidebar.title("Key Influencers")
    key_influencers = nx.pagerank(G).items()
    key_influencers.sort(key=lambda x: x[1], reverse=True)
    st.sidebar.write(f"Top 3 Key Influencers: {key_influencers[:3]}")
else:
    st.write("Please upload a FIR text file.")