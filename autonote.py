import argparse
import json
import os
import requests
import sys
from dotenv import load_dotenv

# Add the current directory to the path to make imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.utils import *

token = os.environ["NOTION_TOKEN"]
tasks_databaseId = os.environ["NOTION_TASK_DATABASE_ID"]
update_DB_URL = f'https://api.notion.com/v1/databases/{tasks_databaseId}'

headers = {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"}

def readDatabase(databaseId, headers):
    readUrl = f"https://api.notion.com/v1/databases/{databaseId}/query"

    res = requests.request("POST", readUrl, headers=headers)
    data = res.json()
    print(res.status_code)

    with open('./db.json', 'w', encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False)
    
    return data

def get_tasks_from_db(db_data):
    """
    Gets a task from my task database.
    """
    length_of_table = len(db_data["results"])
    for i in range(length_of_table):
        if len(db_data["results"][i]["properties"]["Name"]["title"])!=0:
            task_name = db_data["results"][i]["properties"]["Name"]["title"][0]["plain_text"]
            print(f"{i} - {task_name}")

def create_task(task_title, tasks_databaseId, headers):
    update_PAGE_URL = "https://api.notion.com/v1/pages"

    # Define the properties of the new page
    properties = {
        "Name": {
            "title": [
                {
                    "text": {
                        "content": task_title
                    }
                }
            ]
        },
        "Checkbox": {
            "checkbox": False
        }
    }

    # Define the parent of the new page
    parent = {
        "database_id": tasks_databaseId
    }

    # Combine the new page properties and parent into a request body
    data = {
        "parent": parent,
        "properties": properties
    }

    # Send the request to create the new page
    response = requests.post(update_PAGE_URL, headers=headers, data=json.dumps(data))

    # Print the response content and status code
    print(response.status_code)
    if response.status_code != 200:
        print(f"Error creating task: {response.text}")
        return None
    
    # Get the ID of the newly created page
    page_id = response.json()["id"]
    print(f"Task '{task_title}' created successfully with ID: {page_id}")
    return page_id

def update_page_content(page_id, markdown_content, headers):
    """
    Updates the content of a Notion page with markdown content.
    
    Args:
        page_id (str): The ID of the Notion page to update
        markdown_content (str): Markdown content to add to the page
        headers (dict): API headers for authentication
        
    Returns:
        bool: True if successful, False otherwise
    """
    # The correct endpoint for updating content is the blocks endpoint
    update_blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    
    # Convert the markdown content to a Notion-compatible format
    blocks = []
    lines = markdown_content.strip().split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Handle headings
        if line.startswith('# '):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"type": "text", "text": {"content": line[2:]}}]
                }
            })
        elif line.startswith('## '):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": line[3:]}}]
                }
            })
        elif line.startswith('### '):
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": line[4:]}}]
                }
            })
        # Handle paragraphs (any normal text)
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })
        
        i += 1
    
    # Create the payload with the children key
    payload = {
        "children": blocks
    }
    
    # Make the API request
    response = requests.patch(update_blocks_url, headers=headers, json=payload)
    
    # Print results
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        print(f"Successfully updated page content")
        return True
    else:
        print(f"Failed to update page content: {response.text}")
        return False

def create_task_with_content(task_title, markdown_content, tasks_databaseId, headers):
    """
    Creates a task in Notion and adds markdown content to its page.
    
    Args:
        task_title (str): Title of the task
        markdown_content (str): Markdown content for the page
        tasks_databaseId (str): ID of the tasks database
        headers (dict): API headers
        
    Returns:
        str: ID of the created page
    """
    # First create the task
    page_id = create_task(task_title, tasks_databaseId, headers)
    
    if page_id is None:
        return None
    
    # Add content to the page
    if markdown_content:
        success = update_page_content(page_id, markdown_content, headers)
        if success:
            print(f"Content added to page successfully")
        else:
            print(f"Failed to add content to page")
    
    return page_id

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--get", type=str, default="")
    parser.add_argument("--check_task", type=int, default=None)
    parser.add_argument("--uncheck_task", type=int, default=None)
    parser.add_argument("--add_task", type=str, default=None, 
                        help="Create a task in your task db.")
    parser.add_argument("--add_content", type=str, default=None,
                        help="Add markdown content to a page (provide page ID)")
    parser.add_argument("--content_file", type=str, default=None,
                        help="File containing markdown content to add")
    parser.add_argument("--create_with_content", type=str, default=None,
                        help="Create a task and add markdown content from a file")
    args = parser.parse_args()
    
    if args.get=="Task":  # Here is the database name.
        db_data = readDatabase(tasks_databaseId, headers)
        print(get_tasks_from_db(db_data))
    
    if args.check_task!=None:
        task_num=args.check_task
        task_status = True
        page_data = get_page_in_database(tasks_databaseId, headers, task_num)
        page_id = page_data["id"]
        check_task(page_data, page_id, headers, check_status=task_status)
    
    if args.uncheck_task!=None:
        task_num=args.uncheck_task
        task_status = False
        page_data = get_page_in_database(tasks_databaseId, headers, task_num)
        page_id = page_data["id"]
        check_task(page_data, page_id, headers, check_status=task_status)
    
    if args.add_task!=None:
        task_title = args.add_task
        create_task(task_title, tasks_databaseId, headers)
    
    if args.add_content != None and args.content_file != None:
        page_id = args.add_content
        with open(args.content_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        update_page_content(page_id, markdown_content, headers)
    
    if args.create_with_content != None and args.content_file != None:
        task_title = args.create_with_content
        with open(args.content_file, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        create_task_with_content(task_title, markdown_content, tasks_databaseId, headers)