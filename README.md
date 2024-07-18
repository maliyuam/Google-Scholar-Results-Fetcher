# Google Scholar Top Cited Paper Results Fetcher

This script fetches and processes Google Scholar search results using the SerpAPI and saves them to an Excel file. The results are fetched based on a user-provided query, and the number of results to fetch can also be specified by the user. The script ensures a respectful delay between API calls to avoid hitting rate limits.

## Requirements
Before using this code, follow this SerpAPI Account Setup Guide, to create a SerpAPI account:

#### Step 1: Create a SerpAPI Account

1. **Visit the SerpAPI Website**
   - Go to [serpapi.com](https://serpapi.com).

2. **Sign Up**
   - Click on the "Sign Up" button at the top right corner of the homepage.
   - Fill in the required details such as your email, password, and name.
   - Alternatively, you can sign up using your Google or GitHub account.

3. **Verify Your Email**
   - After signing up, you will receive a verification email.
   - Open the email and click on the verification link to activate your account.

#### Step 2: Obtain Your API Key

1. **Log In to Your Account**
   - After verifying your email, log in to your SerpAPI account.

2. **Navigate to the API Key Section**
   - Once logged in, click on your profile icon at the top right corner of the page.
   - Select "API Keys" from the dropdown menu.

3. **Copy Your API Key**
   - In the "API Keys" section, you will find your unique API key.
   - Click the "Copy" button next to the API key to copy it to your clipboard.


Before running the script, ensure the following Python packages are installed:

- serpapi
- pandas
- openpyxl
- google-search-results

You can install these packages using pip:

```sh
!pip install serpapi
!pip install -q pandas
!pip install -q openpyxl
!pip install -q google-search-results
```

## Environment Setup

Make sure you have your SerpAPI API key set as an environment variable:

```sh
export SERPAPI_API_KEY="your_serpapi_api_key"
```

In Google Colab, you can set the environment variable using:

```python
import os
os.environ["SERPAPI_API_KEY"] = "your_serpapi_api_key"
```

## Script Components

### Imports

The script imports necessary libraries and modules:

```python
import pandas as pd
import requests
from serpapi.google_search import GoogleSearch
import re
import time
import os
```

### Environment Variable Check

The script ensures the `SERPAPI_API_KEY` environment variable is set:

```python
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')
if not SERPAPI_API_KEY:
    raise ValueError("Please set the SERPAPI_API_KEY environment variable.")
```

### Function Definitions

#### `fetch_google_scholar_results(query, num_results, sleep_interval=2)`

Fetches Google Scholar results using the SerpAPI.

**Parameters:**
- `query` (str): The search query.
- `num_results` (int): The number of results to fetch.
- `sleep_interval` (int): Time to sleep between API calls to avoid rate limits.

**Returns:**
- `list`: A list of fetched papers.

#### `process_results(results)`

Processes the results fetched from Google Scholar.

**Parameters:**
- `results` (list): The fetched results.

**Returns:**
- `list`: A list of processed papers.

#### `generate_file_name(query)`

Generates a sanitized file name from the query.

**Parameters:**
- `query` (str): The search query.

**Returns:**
- `str`: The sanitized file name.

#### `save_to_excel(papers, filename)`

Saves the processed papers to an Excel file.

**Parameters:**
- `papers` (list): The processed papers.
- `filename` (str): The file name to save the papers.

### Main Function

The main function handles user input, fetches results, processes them, and saves them to an Excel file:

```python
def main():
    query = input("Enter your search query: ")
    num_results = int(input("Enter the number of results you want to fetch: "))
    sleep_interval = int(input("Enter the sleep interval between API calls (seconds): "))
    print("Fetching results...")

    results = fetch_google_scholar_results(query, num_results, sleep_interval)
    print(f"Fetched {len(results)} results.")

    if not results:
        print("No results found or API call failed.")
        return

    print("Processing results...")
    papers = process_results(results)
    print("Saving results to Excel...")
    file_name = generate_file_name(query)
    save_to_excel(papers, file_name)
    print("Done!")

if __name__ == "__main__":
    main()
```

### Usage

1. **Run the Script**: Execute the script in a Python environment or Google Colab.
2. **Provide Input**: Enter the search query, the number of results to fetch, and the sleep interval between API calls when prompted.
3. **Fetch and Process**: The script will fetch the results, process them, and save them to an Excel file.
4. **Output**: The processed results will be saved in an Excel file named based on the search query.

### Example

```sh
Enter your search query: artificial intelligence
Enter the number of results you want to fetch: 50
Enter the sleep interval between API calls (seconds): 2
Fetching results...
Fetched 50 results.
Processing results...
Saving results to Excel...
Saved 50 papers to summary_of_artificial_int.xlsx
Done!
```

### Notes

- Ensure you have a valid SerpAPI API key and it is set as an environment variable.
- Adjust the sleep interval if you encounter rate limiting issues.
- The script processes a maximum of 200 results per page, iterating through pages until the specified number of results is fetched.
