# Overview

This document outlines the synchronization of local Markdown files with a Notion database.

## Usage

1. **Create a Full-Page Database (if you haven't already)** on the current page:

    - In this quick start guide, set the current page title to `database-test`.
        - Instantiate a database by typing `/Database - Full page` in a blank row.
    - Name the created database `Task`.
    - Insert data entries into the database. The table schema should include the following columns:
        - **Name** (the title of the child page)
        - **Checkbox**
        - **URL**
        - **Created Time**
    ![](2025-08-03%20152534.png)

2. **Create a Notion Integration (if you haven't already)**:
    
    - Go to [Notion Integrations](https://www.notion.so/my-integrations).
    - Click "New integration."
    - Give it a recognizable name (e.g., "My Academic Journal Database Integration").
    - Select the associated workspace where your database resides (e.g., "Libin's Notion").
    - Set the appropriate capabilities; at a minimum, select "Read content." Enable "Read/Write" if you want to create new pages or update existing ones.
    - Copy the token from the "Internal Integration Secret" field and click "Save."
    - In the navigation bar, select the “Access” tab.
    - Search for the top-level pages associated with the database (`Task`). In this case, search for the page named `database-test`.
    - Select `database-test` from the search results.

3. **Set Your Environment Variables** for the Notion Integration API key (`NOTION_TOKEN`) and the database ID (`NOTION_TASK_DATABASE_ID`) in the `.env` file.

4. **Run the CLI Tool**:
    ```
    # To get a list of tasks in your database
    python ./autonote.py --get=Task

    # To toggle the checkbox 
    python ./autonote.py --check_task=0
    python ./autonote.py --uncheck_task=0

    # To creae a new task with an blank page
    python ./autonote.py --add_task="<PAGE-TITLE-HERE>"

    # To create a new task with content:
    python ./autonote.py --create_with_content "<PAGE-TITLE-HERE>" --content_file content.md

    # To add content to an existing page (you need the page ID):
    python ./autonote.py --add_content "<PAGE-ID-HERE>" --content_file content.md
    ```
