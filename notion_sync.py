#!/usr/bin/env python3
"""
Notion Sync Tool - A unified CLI for syncing between Notion and local files.
"""

import os
import sys
import yaml
import logging
import argparse
import datetime
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

# Import incremental sync functions
from incremental_sync import (
    get_last_sync_time,
    fetch_recently_modified_pages,
    incremental_pull,
    check_local_changes,
    push_local_changes
)

# Setup logging
def setup_logging(config):
    """Setup logging based on configuration."""
    log_level = getattr(logging, config.get("level", "INFO").upper())
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(level=log_level, format=log_format)
    logger = logging.getLogger("notion_sync")
    
    # Add file handler if specified
    if "file" in config:
        file_handler = logging.FileHandler(config["file"])
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
    
    # Remove console handler if not wanted
    if not config.get("console", True):
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                logger.removeHandler(handler)
    
    return logger

def load_config(config_path):
    """
    Load the configuration from a YAML file.
    
    Args:
        config_path (str): Path to the configuration file
        
    Returns:
        dict: The configuration
    """
    # Load environment variables
    load_dotenv()
    
    # Check if config file exists
    if not os.path.exists(config_path):
        print(f"Configuration file not found: {config_path}")
        print("Creating a default configuration file...")
        
        # Create default config directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Create a default configuration
        default_config = {
            "defaults": {
                "output_dir": "notion_files",
                "file_format": "markdown",
                "frontmatter_format": "yaml",
                "conflict_resolution": "newer_wins"
            },
            "api": {
                "token": "${NOTION_TOKEN}",
                "notion_version": "2022-06-28"
            },
            "databases": [
                {
                    "name": "tasks",
                    "id": "${NOTION_TASK_DATABASE_ID}",
                    "output_dir": "notion_files",
                    "sync": {
                        "pull": True,
                        "push": True,
                        "incremental": True
                    }
                }
            ],
            "logging": {
                "level": "info",
                "console": True
            }
        }
        
        # Write the default configuration
        with open(config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        
        print(f"Default configuration created at {config_path}")
        print("Please edit the configuration file and run the command again.")
        sys.exit(1)
    
    # Load the configuration
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    # Process environment variables in the configuration
    config = process_env_vars(config)
    
    return config

def process_env_vars(config):
    """
    Process environment variables in the configuration.
    
    Args:
        config (dict): The configuration
        
    Returns:
        dict: The processed configuration
    """
    if isinstance(config, dict):
        for key, value in config.items():
            config[key] = process_env_vars(value)
    elif isinstance(config, list):
        for i, item in enumerate(config):
            config[i] = process_env_vars(item)
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        env_var = config[2:-1]
        if env_var in os.environ:
            return os.environ[env_var]
        else:
            print(f"Warning: Environment variable {env_var} not found")
    
    return config

def get_database_config(config, database_name):
    """
    Get the configuration for a specific database.
    
    Args:
        config (dict): The configuration
        database_name (str): The name of the database
        
    Returns:
        dict: The database configuration
    """
    for db in config.get("databases", []):
        if db.get("name") == database_name:
            return db
    
    print(f"Database '{database_name}' not found in configuration")
    print("Available databases:")
    for db in config.get("databases", []):
        print(f"  - {db.get('name')}")
    
    sys.exit(1)

def get_api_headers(config):
    """
    Get the API headers for Notion.
    
    Args:
        config (dict): The configuration
        
    Returns:
        dict: The API headers
    """
    api_config = config.get("api", {})
    
    token = api_config.get("token")
    if not token:
        print("Notion API token not found in configuration")
        sys.exit(1)
    
    notion_version = api_config.get("notion_version", "2022-06-28")
    
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": notion_version
    }

def sync_database(db_config, headers, logger):
    """
    Sync a database based on its configuration.
    
    Args:
        db_config (dict): The database configuration
        headers (dict): The API headers
        logger (logging.Logger): The logger
    """
    database_id = db_config.get("id")
    output_dir = db_config.get("output_dir")
    sync_config = db_config.get("sync", {})
    
    if not database_id:
        logger.error(f"Database ID not found for {db_config.get('name')}")
        return
    
    logger.info(f"Syncing database: {db_config.get('name')} ({database_id})")
    
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Pull from Notion if enabled
    if sync_config.get("pull", True):
        if sync_config.get("incremental", True):
            logger.info("Performing incremental pull from Notion")
            updated_files, new_files = incremental_pull(database_id, output_dir, headers)
            logger.info(f"Incremental pull complete. Updated {len(updated_files)} files, added {len(new_files)} new files.")
        else:
            logger.info("Performing full pull from Notion")
            from autonote_pull import pull_from_notion
            saved_files = pull_from_notion(database_id, output_dir, headers)
            logger.info(f"Full pull complete. Saved {len(saved_files)} files.")
    
    # Push to Notion if enabled
    if sync_config.get("push", True):
        logger.info("Checking for local changes")
        modified_files = check_local_changes(output_dir)
        
        if modified_files:
            logger.info(f"Found {len(modified_files)} locally modified files")
            pushed_files = push_local_changes(modified_files, headers)
            logger.info(f"Successfully pushed {len(pushed_files)} files to Notion")
        else:
            logger.info("No local changes found")

def list_databases(config):
    """
    List all databases in the configuration.
    
    Args:
        config (dict): The configuration
    """
    print("Available databases:")
    for db in config.get("databases", []):
        name = db.get("name", "Unnamed")
        db_id = db.get("id", "No ID")
        output_dir = db.get("output_dir", "Default output directory")
        
        print(f"  - {name}")
        print(f"    ID: {db_id}")
        print(f"    Output directory: {output_dir}")
        print()

def main():
    """Main entry point for the Notion sync tool."""
    parser = argparse.ArgumentParser(description="Notion Sync Tool")
    
    # General options
    parser.add_argument("--config", type=str, default="config.yaml", 
                        help="Path to the configuration file")
    parser.add_argument("--list", action="store_true", 
                        help="List available databases in the configuration")
    
    # Sync commands
    subparsers = parser.add_subparsers(dest="command", help="Sync commands")
    
    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Sync databases")
    sync_parser.add_argument("database", type=str, nargs="?", 
                            help="Name of the database to sync (from config)")
    sync_parser.add_argument("--all", action="store_true", 
                            help="Sync all databases in the configuration")
    
    # Pull command
    pull_parser = subparsers.add_parser("pull", help="Pull from Notion to local")
    pull_parser.add_argument("database", type=str, nargs="?", 
                            help="Name of the database to pull from (from config)")
    pull_parser.add_argument("--all", action="store_true", 
                            help="Pull all databases in the configuration")
    pull_parser.add_argument("--full", action="store_true", 
                            help="Perform a full pull instead of incremental")
    
    # Push command
    push_parser = subparsers.add_parser("push", help="Push from local to Notion")
    push_parser.add_argument("database", type=str, nargs="?", 
                            help="Name of the database to push to (from config)")
    push_parser.add_argument("--all", action="store_true", 
                            help="Push all databases in the configuration")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Check sync status")
    status_parser.add_argument("database", type=str, nargs="?", 
                            help="Name of the database to check (from config)")
    status_parser.add_argument("--all", action="store_true", 
                            help="Check all databases in the configuration")
    
    args = parser.parse_args()
    
    # Load the configuration
    config = load_config(args.config)
    
    # Setup logging
    logger = setup_logging(config.get("logging", {}))
    
    # Get API headers
    headers = get_api_headers(config)
    
    # Handle list command
    if args.list:
        list_databases(config)
        return
    
    # Handle sync command
    if args.command == "sync":
        if args.all:
            for db_config in config.get("databases", []):
                sync_database(db_config, headers, logger)
        elif args.database:
            db_config = get_database_config(config, args.database)
            sync_database(db_config, headers, logger)
        else:
            print("Please specify a database name or use --all")
            return
    
    # Handle pull command
    elif args.command == "pull":
        if args.all:
            for db_config in config.get("databases", []):
                # Override incremental setting if --full is specified
                if args.full:
                    db_config.setdefault("sync", {})["incremental"] = False
                
                # Only run the pull part
                db_config.setdefault("sync", {})["push"] = False
                
                sync_database(db_config, headers, logger)
        elif args.database:
            db_config = get_database_config(config, args.database)
            
            # Override incremental setting if --full is specified
            if args.full:
                db_config.setdefault("sync", {})["incremental"] = False
            
            # Only run the pull part
            db_config.setdefault("sync", {})["push"] = False
            
            sync_database(db_config, headers, logger)
        else:
            print("Please specify a database name or use --all")
            return
    
    # Handle push command
    elif args.command == "push":
        if args.all:
            for db_config in config.get("databases", []):
                # Only run the push part
                db_config.setdefault("sync", {})["pull"] = False
                
                sync_database(db_config, headers, logger)
        elif args.database:
            db_config = get_database_config(config, args.database)
            
            # Only run the push part
            db_config.setdefault("sync", {})["pull"] = False
            
            sync_database(db_config, headers, logger)
        else:
            print("Please specify a database name or use --all")
            return
    
    # Handle status command
    elif args.command == "status":
        if args.all:
            for db_config in config.get("databases", []):
                output_dir = db_config.get("output_dir")
                
                print(f"Status for database: {db_config.get('name')}")
                
                # Get the last sync time
                last_sync = get_last_sync_time(output_dir)
                if last_sync:
                    print(f"  Last sync: {last_sync}")
                else:
                    print("  Never synced")
                
                # Check for local changes
                modified_files = check_local_changes(output_dir)
                if modified_files:
                    print(f"  {len(modified_files)} local files modified since last sync:")
                    for filepath in modified_files:
                        print(f"    - {filepath}")
                else:
                    print("  No local changes since last sync")
                
                print()
        elif args.database:
            db_config = get_database_config(config, args.database)
            output_dir = db_config.get("output_dir")
            
            print(f"Status for database: {db_config.get('name')}")
            
            # Get the last sync time
            last_sync = get_last_sync_time(output_dir)
            if last_sync:
                print(f"  Last sync: {last_sync}")
            else:
                print("  Never synced")
            
            # Check for local changes
            modified_files = check_local_changes(output_dir)
            if modified_files:
                print(f"  {len(modified_files)} local files modified since last sync:")
                for filepath in modified_files:
                    print(f"    - {filepath}")
            else:
                print("  No local changes since last sync")
        else:
            print("Please specify a database name or use --all")
            return
    
    # No command specified
    else:
        parser.print_help()

if __name__ == "__main__":
    main()