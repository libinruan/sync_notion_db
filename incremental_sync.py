import os
import json
import datetime
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add the current directory to the path to make imports work
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.utils import *
from sync_utils import (
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

headers = {
    "Authorization": "Bearer " + token,
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_last_sync_time(output_dir):
    """
    Get the timestamp of the last sync from the metadata file.
    
    Args:
        output_dir (str): Directory where files are saved
        
    Returns:
        str: ISO format timestamp of the last sync, or empty string if never synced
    """
    metadata_path = os.path.join(output_dir, ".notion_sync.json")
    
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            return metadata.get("last_sync", "")
    
    return ""

def fetch_recently_modified_pages(database_id, headers, last_sync_time):
    """
    Fetch only pages that have been modified since the last sync.
    
    Args:
        database_id (str): The ID of the Notion database
        headers (dict): API headers for authentication
        last_sync_time (str): ISO format timestamp of the last sync
        
    Returns:
        list: Pages modified since the last sync
    """
    read_url = f"https://api.notion.com/v1/databases/{database_id}/query"
    
    # If we have a last sync time, use it to filter results
    if last_sync_time:
        # Convert to Notion's expected format if needed
        filter_date = last_sync_time
        
        # Create a filter for pages edited after the last sync
        filter_params = {
            "filter": {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "on_or_after": filter_date
                }
            }
        }
        
        # Make the API request with the filter
        response = requests.post(read_url, headers=headers, json=filter_params)
    else:
        # If no last sync time, get all pages
        response = requests.post(read_url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error fetching pages: {response.text}")
        return []
    
    data = response.json()
    results = data.get("results", [])
    
    # Handle pagination if there are more results
    while data.get("has_more", False):
        next_cursor = data.get("next_cursor")
        
        if last_sync_time:
            filter_params["start_cursor"] = next_cursor
            response = requests.post(read_url, headers=headers, json=filter_params)
        else:
            payload = {"start_cursor": next_cursor}
            response = requests.post(read_url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"Error fetching pages during pagination: {response.text}")
            break
        
        data = response.json()
        
        if "results" in data:
            results.extend(data["results"])
    
    return results

def incremental_pull(database_id, output_dir, headers):
    """
    Pull only pages that have been modified since the last sync.
    
    Args:
        database_id (str): The ID of the Notion database
        output_dir (str): Directory to save the files
        headers (dict): API headers for authentication
        
    Returns:
        tuple: (list of updated files, list of new files)
    """
    print(f"Starting incremental pull from Notion database {database_id}...")
    
    # Get the last sync time
    last_sync_time = get_last_sync_time(output_dir)
    
    if last_sync_time:
        print(f"Last sync was at {last_sync_time}")
    else:
        print("This appears to be the first sync")
    
    # Fetch pages modified since the last sync
    modified_pages = fetch_recently_modified_pages(database_id, headers, last_sync_time)
    print(f"Found {len(modified_pages)} pages modified since last sync")
    
    # Create or update the sync metadata
    metadata, metadata_path = create_sync_metadata(output_dir)
    
    # Get the existing files from metadata
    existing_files = {}
    if "files" in metadata:
        existing_files = metadata["files"]
    
    updated_files = []
    new_files = []
    
    # Process each modified page
    for i, page in enumerate(modified_pages):
        page_id = page.get("id")
        last_edited_time = page.get("last_edited_time")
        
        print(f"Processing page {i+1}/{len(modified_pages)}: {page_id}")
        
        # Check if we've seen this page before
        is_new_page = page_id not in existing_files
        
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
            
            if is_new_page:
                new_files.append(filepath)
                print(f"Saved new page to {filepath}")
            else:
                updated_files.append(filepath)
                print(f"Updated existing page at {filepath}")
        else:
            print(f"Failed to fetch content for page {page_id}")
    
    print(f"Incremental pull complete. Updated {len(updated_files)} files, added {len(new_files)} new files.")
    return updated_files, new_files

def check_local_changes(output_dir):
    """
    Check for local files that have been modified since the last sync.
    
    Args:
        output_dir (str): Directory where files are saved
        
    Returns:
        list: Paths to locally modified files
    """
    metadata_path = os.path.join(output_dir, ".notion_sync.json")
    
    if not os.path.exists(metadata_path):
        print("No sync metadata found. Cannot check for local changes.")
        return []
    
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    modified_files = []
    
    # Check each file in the metadata
    for page_id, file_data in metadata.get("files", {}).items():
        local_path = file_data.get("local_path")
        stored_hash = file_data.get("content_hash")
        
        # Skip if we don't have a path or hash
        if not local_path or not stored_hash:
            continue
        
        # Check if the file still exists
        if not os.path.exists(local_path):
            print(f"File {local_path} no longer exists")
            continue
        
        # Calculate the current hash
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
            current_hash = calculate_content_hash(content)
        
        # Compare hashes
        if current_hash != stored_hash:
            modified_files.append(local_path)
            print(f"Local file modified: {local_path}")
    
    return modified_files

def extract_notion_id_from_frontmatter(filepath):
    """
    Extract the Notion ID from a markdown file's frontmatter.
    
    Args:
        filepath (str): Path to the markdown file
        
    Returns:
        str: Notion ID, or None if not found
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if the file has frontmatter
    if not content.startswith("---"):
        return None
    
    # Find the end of the frontmatter
    end_frontmatter = content.find("---", 3)
    if end_frontmatter == -1:
        return None
    
    # Extract the frontmatter
    frontmatter = content[3:end_frontmatter].strip()
    
    # Look for the notion_id field
    for line in frontmatter.split("\n"):
        if line.startswith("notion_id:"):
            return line.split(":", 1)[1].strip()
    
    return None

def extract_content_from_markdown(filepath):
    """
    Extract the content (without frontmatter) from a markdown file.
    
    Args:
        filepath (str): Path to the markdown file
        
    Returns:
        str: Content without frontmatter
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if the file has frontmatter
    if not content.startswith("---"):
        return content
    
    # Find the end of the frontmatter
    end_frontmatter = content.find("---", 3)
    if end_frontmatter == -1:
        return content
    
    # Return the content after the frontmatter
    return content[end_frontmatter + 3:].strip()

def push_local_changes(modified_files, headers):
    """
    Push local changes to Notion.
    
    Args:
        modified_files (list): Paths to locally modified files
        headers (dict): API headers for authentication
        
    Returns:
        list: Files successfully pushed
    """
    from autonote import update_page_content
    
    pushed_files = []
    
    for filepath in modified_files:
        # Extract the Notion ID from the frontmatter
        notion_id = extract_notion_id_from_frontmatter(filepath)
        
        if not notion_id:
            print(f"Could not find Notion ID in {filepath}")
            continue
        
        # Extract the content without frontmatter
        content = extract_content_from_markdown(filepath)
        
        # Update the page content in Notion
        success = update_page_content(notion_id, content, headers)
        
        if success:
            pushed_files.append(filepath)
            print(f"Successfully pushed changes for {filepath}")
            
            # Update the sync metadata
            metadata_path = os.path.join(os.path.dirname(filepath), ".notion_sync.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                # Calculate the new hash
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    content_hash = calculate_content_hash(content)
                
                # Update the hash in the metadata
                if notion_id in metadata.get("files", {}):
                    metadata["files"][notion_id]["content_hash"] = content_hash
                    metadata["files"][notion_id]["last_synced"] = datetime.datetime.now().isoformat()
                
                # Save the updated metadata
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)
        else:
            print(f"Failed to push changes for {filepath}")
    
    return pushed_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Notion incremental sync tool")
    parser.add_argument("--pull", action="store_true", help="Pull recent changes from Notion to local files")
    parser.add_argument("--push", action="store_true", help="Push local changes to Notion")
    parser.add_argument("--output_dir", type=str, default="notion_files", help="Directory for local files")
    parser.add_argument("--check", action="store_true", help="Check for local changes without pushing")
    
    args = parser.parse_args()
    
    # Create the output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.pull:
        # Pull recent changes from Notion
        incremental_pull(tasks_databaseId, args.output_dir, headers)
    
    if args.check or args.push:
        # Check for local changes
        modified_files = check_local_changes(args.output_dir)
        print(f"Found {len(modified_files)} locally modified files")
        
        if args.push and modified_files:
            # Push local changes to Notion
            pushed_files = push_local_changes(modified_files, headers)
            print(f"Successfully pushed {len(pushed_files)} files to Notion")