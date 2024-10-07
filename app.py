import streamlit as st
import requests
import json
from openai import OpenAI
import pdfplumber
import csv
import os
import tempfile
import pandas as pd
import docx
import zipfile
from io import BytesIO
from io import StringIO
from dotenv import load_dotenv

# Connect to OpenAI
load_dotenv()
API_KEY = os.getenv('API_KEY')
client = OpenAI(api_key = API_KEY)

# Function to fetch grant IDs and titles based on search term or ID
def fetch_info(search, number):
    ids = []
    titles = []
    # Calculate the number of pages
    pages = number // 25 + (number % 25 > 0)
    for page in range(pages):
        # Calculate the record offset
        offset = page * 25 + 1
        # Construct the URL for searching by keyword
        url = f"http://api.nsf.gov/services/v1/awards.json?keyword={search}&offset={offset}"

        # Make the GET request to the API
        grants = requests.get(url)

        # Check if the request was successful
        if grants.status_code == 200:
            try:
                # Parse the JSON data
                data = grants.json()
                # Handle the case when searching by keyword
                if "response" in data and "award" in data["response"]:
                    ids += [award["id"] for award in data["response"]["award"]]
                    titles += [award["title"] for award in data["response"]["award"]]
                elif "award" in data:
                    ids += [data["award"]["id"]]
                    titles += [data["award"]["title"]]
            except json.JSONDecodeError as e:
                st.error(f"Error parsing JSON response: {e}")
                st.error(f"Response text: {grants.text}")
        else:
            st.error(f"Error: Unable to fetch data from the API. Status code: {grants.status_code}")
    
    return ids[:number], titles[:number]

# Function to fetch abstracts for each grant ID, returning abstracts and valid IDs and titles
def fetch_abstracts(grant_ids, titles):
    abstracts = []
    for grant_id, title in zip(grant_ids, titles):
        # Construct the URL for fetching the abstract by ID
        url = f"http://api.nsf.gov/services/v1/awards/{grant_id}.json?printFields=abstractText"        
        # Make the GET request to the API
        response = requests.get(url)
        
        # Check if the request was successful
        if response.status_code == 200:
            try:
                # Parse the JSON data
                data = response.json()
                if "response" in data and "award" in data["response"]:
                    for award in data["response"]["award"]:
                        if "abstractText" in award:
                            abstracts.append(award["abstractText"])
            except json.JSONDecodeError as e:
                st.error(f"Error parsing JSON response for ID {grant_id}: {e}")
                st.error(f"Response text: {response.text}")
        else:
            st.error(f"Error: Unable to fetch data for grant ID {grant_id}. Status code: {response.status_code}")
    
    return abstracts

# Summarize function
def summarize(text, prompt_file):
    # Read system context and prompt from files
    system_context = open("SYSTEM_CONTEXT", "r").read().strip()
    prompt = open(prompt_file, "r").read().strip()
    prompt += text

    # Create a completion request to OpenAI
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_context},
            {"role": "user", "content": prompt}
        ]
    )

    # Extract and return the summary from the response
    summary = response.choices[0].message.content

    return summary

# Read file content function
def read_file(file_path, file_type):
    text = ''
    if file_type == 'pdf':
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
    elif file_type == 'docx':
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text += para.text + '\n'
    elif file_type == 'txt':
        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read()
    return text

# Summarize file content function
def summarize_file_content(file_content):
    return {
        "Intellectual Merit": summarize(file_content, "PROMPT_INTELLECTUAL_MERIT"),
        "Broader Impact": summarize(file_content, "PROMPT_BROADER_IMPACT"),
    }

# Process uploaded files and return summaries
def process_files(files):
    summaries = []
    progress_text = st.empty()  # Create a placeholder for the progress text
    progress_bar = st.progress(0)  # Create a progress bar
    
    total_files = len(files)
    for i, uploaded_file in enumerate(files):
        file_type = uploaded_file.name.split('.')[-1]
        
        # Handle zip files
        if file_type == 'zip':
            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                for file_info in zip_ref.infolist():
                    with zip_ref.open(file_info) as file:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_info.filename.split('.')[-1]}") as tmpfile:
                            tmpfile.write(file.read())
                            tmpfile.flush()  # Ensure the file is written to disk
                            file_content = read_file(tmpfile.name, file_info.filename.split('.')[-1])
                            summaries.append((file_info.filename, summarize_file_content(file_content)))
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmpfile:
                tmpfile.write(uploaded_file.getbuffer())
                tmpfile.flush()  # Ensure the file is written to disk
                file_content = read_file(tmpfile.name, file_type)
                summaries.append((uploaded_file.name, summarize_file_content(file_content)))
        
        # Update progress bar and text
        progress_percentage = (i + 1) / total_files * 100
        progress_bar.progress(progress_percentage / 100)
        progress_text.text(f'Progress: {progress_percentage:.2f}%')

    return summaries

# Summarize abstracts function
def summarize_abstracts(abstracts):
    # Initialize empty lists
    intellectual_merits = []
    broader_impacts = []
    progress_text = st.empty()  # Create a placeholder for the progress text
    # Use ChatGPT to summarize abstracts
    for i, abstract in enumerate(abstracts):
        intellectual_merits.append(summarize(abstract, "PROMPT_INTELLECTUAL_MERIT"))
        broader_impacts.append(summarize(abstract, "PROMPT_BROADER_IMPACT"))
        progress_percentage = (i + 1) / len(abstracts) * 100
        progress_bar.progress(progress_percentage / 100)  # Update progress bar
        progress_text.text(f'Progress: {progress_percentage:.2f}%')  # Update progress text
    return (intellectual_merits, broader_impacts)

# Creating CSV function
def create_csv(ids, titles, intellectual_merits, broader_impacts, search):
    # Function to sanitize cell content
    def sanitize_cell_content(content):
        if isinstance(content, str) and (content.startswith('=') or content.startswith('+') or content.startswith('-') or content.startswith('@')):
            return f' {content}'  # Prepend a space to the content
        return content

    # Assign data as list of lists
    data = [
        ["Titles"] + [sanitize_cell_content(title) for title in titles],
        ["Intellectual Merit"] + [sanitize_cell_content(merit) for merit in intellectual_merits],
        ["Broader Impact"] + [sanitize_cell_content(impact) for impact in broader_impacts]
    ]

    # Create header
    id_headers = ["Topic"] + [f"Award Abstract #{id}" for id in ids]

    # Use StringIO to create CSV in memory
    output = StringIO()
    csvwriter = csv.writer(output)
    
    # Writing the header
    csvwriter.writerow(id_headers)
    
    # Writing the data rows
    csvwriter.writerows(data)
    
    return output.getvalue()

# Display summarized data in table format
def display_summary_table(summaries):
    data = {
        "Filename": [],
        "Intellectual Merit": [],
        "Broader Impact": []
    }
    
    for filename, summary in summaries:
        data["Filename"].append(filename)
        data["Intellectual Merit"].append(summary["Intellectual Merit"])
        data["Broader Impact"].append(summary["Broader Impact"])
    
    df = pd.DataFrame(data)
    st.write("Summary Table")
    st.dataframe(df)

    # Create CSV
    csv_data = df.to_csv(index=False)

    # Provide download link for the summary
    st.download_button(
        label="Download File Summaries CSV",
        data=csv_data,
        file_name="file_summaries.csv",
        mime="text/csv"
    )

# Streamlit UI
st.title("NSF Grant Abstract Summarizer")
st.write("This application uses ChatGPT to summarize NSF grant abstracts based on your search term.")

# Get the search keyword or ID from user input
search = st.text_input("Search term or ID:", "")

# Get the maximum number of results from user input
max_results = st.number_input("Enter the max number of results:", min_value=1, max_value=20, value=10)

if st.button("Fetch and Summarize Grants"):
    # Fetch grant IDs and Titles
    ids, titles = fetch_info(search, max_results)
    st.write(f"Number of grants found: {len(ids)}")

    # Progress bar
    progress_bar = st.progress(0)

    # Fetch abstracts for all grant IDs
    abstracts = fetch_abstracts(ids, titles)

    # Summarize abstracts
    intellectual_merits, broader_impacts = summarize_abstracts(abstracts)

    # Create CSV data
    csv_data = create_csv(ids, titles, intellectual_merits, broader_impacts, search)

    # Provide download button for the CSV file
    st.download_button(
        label="Download Grant Summaries CSV",
        data=csv_data,
        file_name=f"Summaries_for_search_{search.replace(' ', '_')}.csv",
        mime="text/csv"
    )

    # Prepare data for display table
    data = {
        "Topic": ["Titles", "Intellectual Merit", "Broader Impact"],
        **{f"Award Abstract #{id}": [titles[i], intellectual_merits[i], broader_impacts[i]] for i, id in enumerate(ids)}
    }
    df = pd.DataFrame(data)

    # Set the index to the "Topic" column and then remove the index name
    df.set_index("Topic", inplace=True)
    df.index.name = None

    # Display the data in a table
    st.write("Summary Table")
    st.dataframe(df)

# Streamlit UI for File Summarizer
st.title("File Summarizer")
st.write("This application uses ChatGPT to summarize uploaded files. Supported formats are PDF, Docx, Text files, and ZIP files containing any of these formats.")

# Upload multiple files
uploaded_files = st.file_uploader("Choose files", type=["pdf", "docx", "txt", "zip"], accept_multiple_files=True)

if uploaded_files:
    # Process and summarize the files
    summaries = process_files(uploaded_files)
    
    # Display summarized data in table format
    display_summary_table(summaries)