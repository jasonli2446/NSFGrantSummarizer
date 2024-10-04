# NSFGrantSummarizer
A Streamlit app that:
1. Fetches NSF grant abstracts based on a search term/ID and summarizes intellectual merit and broader impacts using ChatGPT.
2. Summarizes uploaded files (PDF, DOCX, TXT, ZIP) with a focus on intellectual merit and broader impacts.
3. Exports results as a CSV file.

This project uses environment variables for sensitive data. To run the project, follow these steps:

1. Create a `.env` file in the root directory.
2. Add the following line to the `.env` file:
