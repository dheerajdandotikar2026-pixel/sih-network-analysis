import os
import json
from groq import Groq
import streamlit as st

# Securely grab the API key from Streamlit's secrets
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

system_prompt = """
You are a criminal intelligence extraction tool. 
Extract all entities from the text and return ONLY a valid JSON object matching this structure:
{"people": [], "locations": [], "phone_numbers": [], "vehicles": [], "organizations": []}
"""

def extract_data_from_text(content):
    completion = client.chat.completions.create(
        model="llama3-8b-8192", # Free Llama 3 model hosted on Groq
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        temperature=0.1,
    )
    return completion.choices[0].message.content