import os
import json
import hashlib
import datetime
import requests
from pathlib import Path

def fetch_all_pages_from_database(database_id, headers):
    """
    Fetches all pages from a Notion database.
    
    Args:
        database_id (str): The ID of the Notion database
        headers (dict): API headers for authentication
        
    Returns:
        list: All pages in the database
    """
    from autonote import readDatabase
    
    # Get the initial database query results
    data = readDatabase(database_id, headers)
    results = data.get("results", [])
    
    # Handle pagination if there are more results
    while data.get("has_more", False):
        next_cursor = data.get("next_cursor")
        read_url = f"https://api.notion.com/v1/databases/{database_id}/query"
        payload = {"start_cursor": next_cursor}
        
        response = requests.post(read_url, headers=headers, json=payload)
        data = response.json()
        
        if "results" in data:
            results.extend(data["results"])
    
    return results

def fetch_page_content(page_id, headers):
    """
    Fetches the content blocks of a Notion page.
    
    Args:
        page_id (str): The ID of the Notion page
        headers (dict): API headers for authentication
        
    Returns:
        dict: The page content blocks
    """
    blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    response = requests.get(blocks_url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error fetching page content: {response.text}")
        return None
    
    return response.json()

def notion_blocks_to_markdown(blocks):
    """
    Converts Notion blocks to markdown format.
    
    Args:
        blocks (dict): The Notion blocks response
        
    Returns:
        str: Markdown representation of the blocks
    """
    markdown = ""
    
    for block in blocks.get("results", []):
        block_type = block.get("type")
        
        if block_type == "paragraph":
            text_content = ""
            for text in block.get("paragraph", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += text_content + "\n\n"
            
        elif block_type == "heading_1":
            text_content = ""
            for text in block.get("heading_1", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += f"# {text_content}\n\n"
            
        elif block_type == "heading_2":
            text_content = ""
            for text in block.get("heading_2", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += f"## {text_content}\n\n"
            
        elif block_type == "heading_3":
            text_content = ""
            for text in block.get("heading_3", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += f"### {text_content}\n\n"
            
        elif block_type == "bulleted_list_item":
            text_content = ""
            for text in block.get("bulleted_list_item", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += f"- {text_content}\n"
            
        elif block_type == "numbered_list_item":
            text_content = ""
            for text in block.get("numbered_list_item", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            markdown += f"1. {text_content}\n"
            
        elif block_type == "to_do":
            text_content = ""
            for text in block.get("to_do", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            checked = block.get("to_do", {}).get("checked", False)
            checkbox = "x" if checked else " "
            markdown += f"- [{checkbox}] {text_content}\n"
            
        elif block_type == "code":
            text_content = ""
            for text in block.get("code", {}).get("rich_text", []):
                text_content += text.get("plain_text", "")
            language = block.get("code", {}).get("language", "")
            markdown += f"```{language}\n{text_content}\n```\n\n"
            
        # Add more block types as needed
    
    return markdown

def generate_frontmatter(page_properties, page_id, last_edited_time):
    """
    Generates YAML frontmatter from Notion page properties.
    
    Args:
        page_properties (dict): The properties of the Notion page
        page_id (str): The ID of the Notion page
        last_edited_time (str): The last edited time of the page
        
    Returns:
        str: YAML frontmatter
    """
    frontmatter = "---\n"
    frontmatter += f"notion_id: {page_id}\n"
    frontmatter += f"last_edited_time: {last_edited_time}\n"
    
    # Add other properties based on their type
    for prop_name, prop_data in page_properties.items():
        prop_type = prop_data.get("type")
        
        if prop_type == "title":
            if prop_data.get("title") and len(prop_data["title"]) > 0:
                title_text = prop_data["title"][0].get("plain_text", "")
                frontmatter += f"title: \"{title_text}\"\n"
                
        elif prop_type == "rich_text":
            if prop_data.get("rich_text") and len(prop_data["rich_text"]) > 0:
                text = prop_data["rich_text"][0].get("plain_text", "")
                frontmatter += f"{prop_name.lower()}: \"{text}\"\n"
                
        elif prop_type == "select":
            if prop_data.get("select") and prop_data["select"].get("name"):
                frontmatter += f"{prop_name.lower()}: {prop_data['select']['name']}\n"
                
        elif prop_type == "multi_select":
            if prop_data.get("multi_select"):
                values = [item.get("name") for item in prop_data["multi_select"] if item.get("name")]
                if values:
                    frontmatter += f"{prop_name.lower()}: [{', '.join([f'\"{v}\"' for v in values])}]\n"
                    
        elif prop_type == "checkbox":
            frontmatter += f"{prop_name.lower()}: {str(prop_data.get('checkbox', False)).lower()}\n"
            
        elif prop_type == "date":
            if prop_data.get("date") and prop_data["date"].get("start"):
                frontmatter += f"{prop_name.lower()}: {prop_data['date']['start']}\n"
    
    frontmatter += "---\n\n"
    return frontmatter

def calculate_content_hash(content):
    """
    Calculates a hash of the content for change detection.
    
    Args:
        content (str): The content to hash
        
    Returns:
        str: Hash of the content
    """
    return hashlib.md5(content.encode()).hexdigest()

def save_page_to_file(page_data, page_content, output_dir):
    """
    Saves a Notion page to a local markdown file with frontmatter.
    
    Args:
        page_data (dict): The page data from Notion
        page_content (dict): The page content blocks
        output_dir (str): Directory to save the file
        
    Returns:
        str: Path to the saved file
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get the page ID and properties
    page_id = page_data.get("id", "").replace("-", "")
    properties = page_data.get("properties", {})
    last_edited_time = page_data.get("last_edited_time", "")
    
    # Get the title for the filename
    title = "Untitled"
    for prop_name, prop_data in properties.items():
        if prop_data.get("type") == "title" and prop_data.get("title") and len(prop_data["title"]) > 0:
            title = prop_data["title"][0].get("plain_text", "Untitled")
            break
    
    # Create a valid filename
    filename = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    filename = f"{filename}.md"
    filepath = os.path.join(output_dir, filename)
    
    # Convert blocks to markdown
    markdown_content = notion_blocks_to_markdown(page_content)
    
    # Generate frontmatter
    frontmatter = generate_frontmatter(properties, page_id, last_edited_time)
    
    # Combine frontmatter and content
    full_content = frontmatter + markdown_content
    
    # Save to file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_content)
    
    # Return the path to the saved file
    return filepath

def create_sync_metadata(output_dir):
    """
    Creates or updates the sync metadata file.
    
    Args:
        output_dir (str): Directory where files are saved
        
    Returns:
        dict: The sync metadata
    """
    metadata_path = os.path.join(output_dir, ".notion_sync.json")
    
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    else:
        metadata = {
            "last_sync": "",
            "files": {}
        }
    
    # Update the last sync time
    metadata["last_sync"] = datetime.datetime.now().isoformat()
    
    return metadata, metadata_path

def update_sync_metadata(metadata, metadata_path, page_id, filepath, content_hash, last_edited_time):
    """
    Updates the sync metadata for a specific file.
    
    Args:
        metadata (dict): The sync metadata
        metadata_path (str): Path to the metadata file
        page_id (str): Notion page ID
        filepath (str): Path to the local file
        content_hash (str): Hash of the file content
        last_edited_time (str): Last edited time from Notion
    """
    # Update the metadata for this file
    metadata["files"][page_id] = {
        "local_path": filepath,
        "content_hash": content_hash,
        "last_edited_time": last_edited_time,
        "last_synced": datetime.datetime.now().isoformat()
    }
    
    # Save the updated metadata
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)