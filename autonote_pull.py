import argparse
import json
import os
import requests
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the current directory to the path to make imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.utils import *
from sync_utils import (
    fetch_all_pages_from_database,
    fetch_page_content,
    notion_blocks_to_markdown,
    save_page_to_file,
    create_sync_metadata,
    update_sync_metadata,
    calculate_content_hash
)

# Load environment variables
load_dotenv()

token = os.environ["NOTION_TOKEN"]
tasks_databaseId = os.environ["NOTION_TASK_DATABASE_ID"]
update_DB_URL = f'https://api.notion.com/v1/databases/{tasks_databaseId}'

headers = {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def pull_from_notion(database_id, output_dir, headers):
    """
    Pulls all pages from a Notion database and saves them as local markdown files.
    
    Args:
        database_id (str): The ID of the Notion database
        output_dir (str): Directory to save the files
        headers (dict): API headers for authentication
        
    Returns:
        list: Paths to the saved files
    """
    print(f"Pulling data from Notion database {database_id}...")
    
    # Fetch all pages from the database
    pages = fetch_all_pages_from_database(database_id, headers)
    print(f"Found {len(pages)} pages in the database")
    
    # Create or update the sync metadata
    metadata, metadata_path = create_sync_metadata(output_dir)
    
    saved_files = []
    
    # Process each page
    for i, page in enumerate(pages):
        page_id = page.get("id")
        last_edited_time = page.get("last_edited_time")
        
        print(f"Processing page {i+1}/{len(pages)}: {page_id}")
        
        # Fetch the page content
        page_content = fetch_page_content(page_id, headers)
        
        if page_content:
            # Save the page to a file
            filepath = save_page_to_file(page, page_content, output_dir)
            
            # Calculate the content hash
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                content_hash = calculate_content_hash(content)
            
            # Update the sync metadata
            update_sync_metadata(metadata, metadata_path, page_id, filepath, content_hash, last_edited_time)
            
            saved_files.append(filepath)
            print(f"Saved page to {filepath}")
        else:
            print(f"Failed to fetch content for page {page_id}")
    
    print(f"Pull complete. Saved {len(saved_files)} files to {output_dir}")
    return saved_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notion sync tool")
    parser.add_argument("--pull", action="store_true", help="Pull data from Notion to local files")
    parser.add_argument("--output_dir", type=str, default="notion_files", help="Directory to save pulled files")
    
    # Add the existing arguments
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
    
    # Handle the pull command
    if args.pull:
        output_dir = args.output_dir
        pull_from_notion(tasks_databaseId, output_dir, headers)
    
    # Handle the existing commands
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