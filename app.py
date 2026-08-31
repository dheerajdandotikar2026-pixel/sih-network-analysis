import streamlit as st
import networkx as nx
from pyvis.network import Network
import pandas as pd
import streamlit.components.v1 as components

# Set the dark mode theme for Streamlit
st.set_page_config(
    page_title="Criminal Network Analysis", 
    page_icon=":gear:", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Create a sidebar to upload new FIR text files
st.sidebar.title("Upload FIR Text Files")
uploaded_file = st.sidebar.file_uploader("Select FIR text file", type=["txt"])

# Create a main window to display the network graph
if uploaded_file is not None:
    try:
        # Read the FIR text file
        fir_data = pd.read_csv(uploaded_file, delimiter=";", header=None, names=["Node", "Type", "Weight"])

        # Create a NetworkX graph from the FIR data
        G = nx.from_pandas_edgelist(fir_data, source="Node", target="Node", edge_attr="Weight", create_using=nx.Graph)

        # Create a pyvis network object
        n = Network(height="800px", width="800px", directed=True)
        n.from_nx(G)

        # Save the network graph locally inside the cloud container (using 'n')
        n.save_graph("network.html")

        # Read the HTML and safely display it in the Streamlit app
        with open("network.html", "r", encoding="utf-8") as f:
            html_data = f.read()

        components.html(html_data, height=650, scrolling=True)

        # Create a sidebar section to list the top 3 'Key Influencers'
        st.sidebar.title("Key Influencers")
        pagerank_dict = nx.pagerank(G)
        key_influencers = sorted(pagerank_dict.items(), key=lambda x: x[1], reverse=True)
        st.sidebar.write(f"Top 3 Key Influencers: {key_influencers[:3]}")

    except Exception as e:
        st.error(f"Error processing file format: {e}")
else:
    st.write("Please upload a FIR text file.")
