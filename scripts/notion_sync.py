# notion_sync.py
import os
import json
import sys
import yaml
import shutil
import csv
from pathlib import Path
from dotenv import load_dotenv
from notion_client import Client
from datetime import datetime, timezone

def load_config():
    """Load and validate configuration file."""
    config_path = Path(__file__).parent / "config.json"
    
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config file: {e}")
        sys.exit(1)
    
    # Basic validation
    required_fields = ['output_dir', 'databases']
    for field in required_fields:
        if field not in config:
            print(f"❌ Missing required field in config: {field}")
            sys.exit(1)
    
    if not isinstance(config['databases'], list) or len(config['databases']) == 0:
        print("❌ No databases configured")
        sys.exit(1)
    
    # Validate each database entry
    for i, db in enumerate(config['databases']):
        required_db_fields = ['name', 'prefix', 'database_id', 'title_property_name']
        for field in required_db_fields:
            if field not in db:
                print(f"❌ Database {i}: Missing required field '{field}'")
                sys.exit(1)
    
    print(f"✅ Config loaded successfully with {len(config['databases'])} databases")
    return config

def init_notion_client():
    """Initialize Notion client with API key."""
    load_dotenv() 
    api_key = os.environ.get("NOTION_API_KEY")
        
    if not api_key:
            print("❌ NOTION_API_KEY not found. Make sure it's set in your .env file.")
            sys.exit(1)
        
    try:
        client = Client(auth=api_key)
        print("✅ Notion client initialized")
        return client
    except Exception as e:
        print(f"❌ Failed to initialize Notion client: {e}")
        sys.exit(1)

def test_database_access(client, databases):
    """Test access to each configured database."""
    print("\n🔍 Testing database access...")
    
    accessible_dbs = []
    inaccessible_dbs = []
    
    for db_config in databases:
        db_name = db_config['name']
        db_id = db_config['database_id']
        
        try:
            # Try to query the database (just get metadata, no pages yet)
            response = client.databases.retrieve(database_id=db_id)
            print(f"✅ {db_name}: Accessible")
            accessible_dbs.append(db_config)
            
            # Check if the title property exists
            title_prop = db_config['title_property_name']
            properties = response.get('properties', {})
            if title_prop not in properties:
                print(f"⚠️  {db_name}: Title property '{title_prop}' not found. Available properties: {list(properties.keys())}")
            else:
                print(f"   Title property '{title_prop}' found")
                
        except Exception as e:
            print(f"❌ {db_name}: Not accessible - {str(e)}")
            inaccessible_dbs.append((db_config, str(e)))
    
    return accessible_dbs, inaccessible_dbs

def query_database_pages(client, db_config):
    """Query all pages from a database with pagination."""
    db_name = db_config['name']
    db_id = db_config['database_id']
    
    print(f"\n📄 Querying pages from '{db_name}'...")
    
    all_pages = []
    start_cursor = None
    
    try:
        while True:
            # Query database with pagination
            query_params = {"database_id": db_id, "page_size": 100}
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = client.databases.query(**query_params)
            pages = response.get('results', [])
            all_pages.extend(pages)
            
            print(f"   Fetched {len(pages)} pages (total: {len(all_pages)})")
            
            # Check if there are more pages
            if not response.get('has_more', False):
                break
                
            start_cursor = response.get('next_cursor')
        
        print(f"✅ Total pages found in '{db_name}': {len(all_pages)}")
        return all_pages
        
    except Exception as e:
        print(f"❌ Error querying '{db_name}': {str(e)}")
        return []

def extract_page_properties(page, title_property_name):
    """Extract properties from a Notion page."""
    properties = page.get('properties', {})
    extracted = {}
    
    # Extract page ID and last edited time
    extracted['notion_id'] = page['id']
    extracted['last_edited_time'] = page.get('last_edited_time')
    
    # Extract title property
    title_prop = properties.get(title_property_name, {})
    if title_prop.get('type') == 'title':
        title_texts = title_prop.get('title', [])
        if title_texts:
            extracted['title'] = ''.join([text.get('plain_text', '') for text in title_texts])
        else:
            extracted['title'] = 'Untitled'
    else:
        extracted['title'] = 'Untitled'
    
    # Extract other properties (simplified for now)
    for prop_name, prop_data in properties.items():
        if prop_name == title_property_name:
            continue  # Already handled
            
        prop_type = prop_data.get('type')
        
        if prop_type == 'select' and prop_data.get('select'):
            extracted[prop_name.lower().replace(' ', '_')] = prop_data['select']['name']
        elif prop_type == 'multi_select':
            extracted[prop_name.lower().replace(' ', '_')] = [item['name'] for item in prop_data.get('multi_select', [])]
        elif prop_type == 'number' and prop_data.get('number') is not None:
            extracted[prop_name.lower().replace(' ', '_')] = prop_data['number']
        elif prop_type == 'checkbox':
            extracted[prop_name.lower().replace(' ', '_')] = prop_data.get('checkbox', False)
        elif prop_type == 'date' and prop_data.get('date'):
            extracted[prop_name.lower().replace(' ', '_')] = prop_data['date']['start']
        elif prop_type == 'relation':
            relation_ids = [rel['id'] for rel in prop_data.get('relation', [])]
            
            # Special handling for requirement relations - convert to file paths
            if prop_name.lower() in ['requirement', 'requirements']:
                extracted['requirement_file'] = [f"REQ-{rel_id}/index.md" for rel_id in relation_ids]
            else:
                # Keep other relations as-is for now
                extracted[prop_name.lower().replace(' ', '_')] = relation_ids
        # Add more property types as needed
    
    return extracted

def extract_rich_text(rich_text_array):
    """Extract plain text from Notion rich text array with basic formatting."""
    if not rich_text_array:
        return ""
    
    result = ""
    for text_obj in rich_text_array:
        content = text_obj.get('plain_text', '')
        annotations = text_obj.get('annotations', {})
        
        # Apply basic formatting
        if annotations.get('bold'):
            content = f"**{content}**"
        if annotations.get('italic'):
            content = f"*{content}*"
        if annotations.get('code'):
            content = f"`{content}`"
        
        result += content
    
    return result

def fetch_page_blocks(client, page_id):
    """Fetch all blocks from a page with pagination."""
    all_blocks = []
    start_cursor = None
    
    try:
        while True:
            query_params = {"block_id": page_id, "page_size": 100}
            if start_cursor:
                query_params["start_cursor"] = start_cursor
            
            response = client.blocks.children.list(**query_params)
            blocks = response.get('results', [])
            all_blocks.extend(blocks)
            
            # Check if there are more blocks
            if not response.get('has_more', False):
                break
                
            start_cursor = response.get('next_cursor')
        
        return all_blocks
        
    except Exception as e:
        print(f"❌ Error fetching blocks for page {page_id}: {str(e)}")
        return []

def convert_block_to_markdown(client, block, level=0):
    """Convert a single Notion block to markdown."""
    block_type = block.get('type')
    block_data = block.get(block_type, {})
    
    # Handle different block types
    if block_type == 'paragraph':
        text = extract_rich_text(block_data.get('rich_text', []))
        return text + '\n\n' if text.strip() else '\n'
    
    elif block_type == 'heading_1':
        text = extract_rich_text(block_data.get('rich_text', []))
        return f"# {text}\n\n"
    
    elif block_type == 'heading_2':
        text = extract_rich_text(block_data.get('rich_text', []))
        return f"## {text}\n\n"
    
    elif block_type == 'heading_3':
        text = extract_rich_text(block_data.get('rich_text', []))
        return f"### {text}\n\n"
    
    elif block_type == 'bulleted_list_item':
        text = extract_rich_text(block_data.get('rich_text', []))
        indent = '  ' * level
        markdown = f"{indent}- {text}\n"
        
        # Handle nested items
        if block.get('has_children'):
            children = fetch_page_blocks(client, block['id'])
            for child in children:
                markdown += convert_block_to_markdown(client, child, level + 1)
        
        return markdown
    
    elif block_type == 'numbered_list_item':
        text = extract_rich_text(block_data.get('rich_text', []))
        indent = '  ' * level
        markdown = f"{indent}1. {text}\n"
        
        # Handle nested items
        if block.get('has_children'):
            children = fetch_page_blocks(client, block['id'])
            for child in children:
                markdown += convert_block_to_markdown(client, child, level + 1)
        
        return markdown
    
    elif block_type == 'to_do':
        text = extract_rich_text(block_data.get('rich_text', []))
        checked = block_data.get('checked', False)
        checkbox = '- [x]' if checked else '- [ ]'
        indent = '  ' * level
        markdown = f"{indent}{checkbox} {text}\n"
        
        # Handle nested items
        if block.get('has_children'):
            children = fetch_page_blocks(client, block['id'])
            for child in children:
                markdown += convert_block_to_markdown(client, child, level + 1)
        
        return markdown
    
    elif block_type == 'code':
        language = block_data.get('language', '')
        text = extract_rich_text(block_data.get('rich_text', []))
        return f"```{language}\n{text}\n```\n\n"
    
    elif block_type == 'divider':
        return "---\n\n"
    
    elif block_type == 'quote':
        text = extract_rich_text(block_data.get('rich_text', []))
        return f"> {text}\n\n"
    
    else:
        # Unsupported block type - add placeholder
        return f"<!-- Unsupported Block Type: '{block_type}' -->\n\n"

def convert_page_to_markdown(client, page_id):
    """Convert an entire Notion page to markdown content."""
    blocks = fetch_page_blocks(client, page_id)
    
    if not blocks:
        return "<!-- No content found -->\n"
    
    markdown_content = ""
    
    for block in blocks:
        markdown_content += convert_block_to_markdown(client, block)
    
    return markdown_content

def create_markdown_file(output_dir, db_config, page, properties, markdown_content):
    """Create a markdown file with YAML frontmatter and content."""
    prefix = db_config['prefix']
    page_id = page['id']
    
    # Create folder name: PREFIX-page_id
    folder_name = f"{prefix}-{page_id}"
    folder_path = Path(output_dir) / folder_name
    
    # Create folder
    folder_path.mkdir(parents=True, exist_ok=True)
    
    # Create index.md file
    index_file = folder_path / "index.md"
    
    # Prepare YAML frontmatter
    frontmatter = {}
    for key, value in properties.items():
        frontmatter[key] = value
    
    # Write file with YAML frontmatter + markdown content
    with open(index_file, 'w', encoding='utf-8') as f:
        # Write YAML frontmatter
        f.write("---\n")
        yaml.dump(frontmatter, f, default_flow_style=False, allow_unicode=True)
        f.write("---\n\n")
        
        # Write markdown content
        f.write(markdown_content)
    
    return folder_path, index_file

def sync_database(client, db_config, output_dir, dry_run=False, force_update=False):
    """Sync all pages from a single database."""
    db_name = db_config['name']
    skip_content = db_config.get('skip_content', False)
    
    print(f"\n🔄 Syncing database: {db_name}")
    if skip_content:
        print("   📋 Sparse mode: Properties only (no content processing)")
    
    # Query all pages
    pages = query_database_pages(client, db_config)
    
    if not pages:
        print(f"   No pages found in {db_name}")
        return 0, set()
    
    synced_count = 0
    skipped_count = 0
    page_ids = {page['id'] for page in pages}
    all_properties = []  # Collect all properties for CSV output
    
    for i, page in enumerate(pages, 1):
        try:
            # Extract properties
            properties = extract_page_properties(page, db_config['title_property_name'])
            all_properties.append(properties)  # Collect properties
            
            print(f"   [{i}/{len(pages)}] Processing: {properties['title']}")
            
            if not dry_run:
                # Check if update is needed (unless forced)
                prefix = db_config['prefix']
                page_id = page['id']
                folder_name = f"{prefix}-{page_id}"
                folder_path = Path(output_dir) / folder_name
                
                if not force_update and not needs_update(folder_path, properties.get('last_edited_time')):
                    print("      ⏭️  Skipped: Up to date")
                    skipped_count += 1
                    continue
                
                if skip_content:
                    # Create sparse file (properties only)
                    folder_path, index_file = create_sparse_markdown_file(
                        output_dir, db_config, page, properties
                    )
                    print(f"      ✅ Created: {folder_path.name}/index.md (sparse)")
                else:
                    # Full content processing
                    markdown_content = convert_page_to_markdown(client, page['id'])
                    
                    # Create file
                    folder_path, index_file = create_markdown_file(
                        output_dir, db_config, page, properties, markdown_content
                    )
                    
                    print(f"      ✅ Created: {folder_path.name}/index.md ({len(markdown_content)} chars)")
            else:
                # Dry run
                mode = "sparse" if skip_content else "full"
                print(f"      🔍 [DRY RUN] Would create: {db_config['prefix']}-{page['id']}/index.md ({mode})")
            
            synced_count += 1
            
        except Exception as e:
            print(f"      ❌ Error processing '{properties.get('title', 'Unknown')}': {str(e)}")
    
    # Write CSV if configured
    if db_config.get('output_csv', False) and not dry_run:
        write_database_to_csv(output_dir, db_config, all_properties)
    
    if not dry_run and skipped_count > 0:
        print(f"✅ Synced {synced_count}/{len(pages)} pages from '{db_name}' ({skipped_count} skipped - up to date)")
    else:
        print(f"✅ Synced {synced_count}/{len(pages)} pages from '{db_name}'")
    
    return synced_count, page_ids

def full_sync(client, config, dry_run=False, force_update=False):
    """Perform full sync of all configured databases."""
    output_dir = Path(config['output_dir'])
    
    sync_type = "FULL SYNC"
    if dry_run:
        sync_type = "DRY RUN"
    elif not force_update:
        sync_type = "INCREMENTAL SYNC"
    
    print(f"\n🚀 Starting {sync_type}")
    print(f"📁 Output directory: {output_dir.absolute()}")
    
    if not dry_run:
        if force_update and output_dir.exists():
            print("🗑️  Cleaning existing output directory (force update)...")
            shutil.rmtree(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        print("✅ Output directory ready")
    
    total_synced = 0
    all_current_page_ids = set()
    
    # Sync each database and collect page IDs
    for db_config in config['databases']:
        try:
            # Sync the database and get page IDs
            synced, page_ids = sync_database(client, db_config, output_dir, dry_run, force_update)
            total_synced += synced
            all_current_page_ids.update(page_ids)
        except Exception as e:
            print(f"❌ Error syncing database '{db_config['name']}': {str(e)}")
    
    # Clean up orphaned files (only for incremental sync, not force update)
    if not force_update:
        clean_orphaned_files(output_dir, all_current_page_ids, config['databases'], dry_run)
    
    print(f"\n📊 Sync Summary:")
    print(f"✅ Total pages synced: {total_synced}")
    print(f"📁 Output location: {output_dir.absolute()}")
    
    return total_synced

def test_block_processing(client, accessible_dbs, limit_per_db=1):
    """Test block processing for a limited number of pages."""
    print("\n🧪 Testing block processing (limited sample)...")
    
    for db_config in accessible_dbs[:1]:  # Test only first database
        pages = query_database_pages(client, db_config)
        
        if not pages:
            continue
            
        print(f"\n📝 Processing content from '{db_config['name']}':")
        
        # Try to find a page with more content - look for "Project Design and Principles"
        test_page = None
        for page in pages:
            properties = extract_page_properties(page, db_config['title_property_name'])
            if 'Design' in properties['title'] or 'Architecture' in properties['title']:
                test_page = page
                break
        
        # If no specific page found, use the first one
        if not test_page and pages:
            test_page = pages[0]
        
        if test_page:
            properties = extract_page_properties(test_page, db_config['title_property_name'])
            
            print(f"\n   📄 Processing: {properties['title']}")
            print(f"      Page ID: {properties['notion_id']}")
            
            # Fetch and convert content
            markdown_content = convert_page_to_markdown(client, test_page['id'])
            
            # Show more lines of content
            content_lines = markdown_content.split('\n')[:20]
            print(f"      Content preview ({len(markdown_content)} chars):")
            for line in content_lines:
                if line.strip():
                    print(f"        {line[:100]}{'...' if len(line) > 100 else ''}")
                elif line == '':
                    print("        [empty line]")

def test_page_extraction(client, accessible_dbs, limit_per_db=3):
    """Test page extraction for a limited number of pages per database."""
    print("\n🧪 Testing page extraction (limited sample)...")
    
    for db_config in accessible_dbs[:2]:  # Test only first 2 databases
        pages = query_database_pages(client, db_config)
        
        if not pages:
            continue
            
        print(f"\n📋 Sample pages from '{db_config['name']}':")
        
        # Process only first few pages for testing
        for i, page in enumerate(pages[:limit_per_db]):
            properties = extract_page_properties(page, db_config['title_property_name'])
            
            print(f"   {i+1}. {properties['title']}")
            print(f"      ID: {properties['notion_id']}")
            print(f"      Properties: {len(properties)-2} additional")  # -2 for title and notion_id
            
            # Show a few properties
            for key, value in list(properties.items())[2:4]:  # Show first 2 non-title properties
                print(f"      {key}: {value}")

def validate_output_directory(output_dir):
    """Validate that output directory can be created/written to."""
    output_path = Path(output_dir)
    
    try:
        output_path.mkdir(parents=True, exist_ok=True)
        # Test write access
        test_file = output_path / ".test_write"
        test_file.write_text("test")
        test_file.unlink()
        print(f"✅ Output directory accessible: {output_path.absolute()}")
        return True
    except Exception as e:
        print(f"❌ Cannot write to output directory {output_path}: {e}")
        return False

def needs_update(folder_path, notion_last_edited):
    """Check if a local file needs updating based on Notion's last_edited_time."""
    index_file = folder_path / "index.md"
    
    if not index_file.exists():
        return True  # File doesn't exist, needs creation
    
    if not notion_last_edited:
        print(f"      ⚠️  No timestamp from Notion, forcing update")
        return True  # Missing timestamp is suspicious, force update
    
    try:
        # Parse Notion timestamp (always UTC)
        notion_time = datetime.fromisoformat(notion_last_edited.replace('Z', '+00:00'))
        
        # Get local file time and convert to UTC
        local_timestamp = index_file.stat().st_mtime
        local_time = datetime.fromtimestamp(local_timestamp, tz=timezone.utc)
        
        # Compare both in UTC
        return notion_time > local_time
        
    except Exception as e:
        print(f"      ⚠️  Error comparing timestamps: {e}, forcing update")
        return True

def create_sparse_markdown_file(output_dir, db_config, page, properties):
    """Create a markdown file with only YAML frontmatter (no content processing)."""
    prefix = db_config['prefix']
    page_id = page['id']
    
    # Create folder name: PREFIX-page_id
    folder_name = f"{prefix}-{page_id}"
    folder_path = Path(output_dir) / folder_name
    
    # Create folder
    folder_path.mkdir(parents=True, exist_ok=True)
    
    # Create index.md file
    index_file = folder_path / "index.md"
    
    # Prepare YAML frontmatter
    frontmatter = {}
    for key, value in properties.items():
        frontmatter[key] = value
    
    # Write file with YAML frontmatter only
    with open(index_file, 'w', encoding='utf-8') as f:
        # Write YAML frontmatter
        f.write("---\n")
        yaml.dump(frontmatter, f, default_flow_style=False, allow_unicode=True)
        f.write("---\n\n")
        
        # Add note for sparse content
        f.write("<!-- This is a sparse entry with properties only -->\n")
    
    return folder_path, index_file

def write_database_to_csv(output_dir, db_config, all_pages_properties):
    """Write database contents to CSV file."""
    csv_filename = f"{db_config['name'].lower().replace(' ', '_')}.csv"
    csv_path = Path(output_dir) / csv_filename
    
    if not all_pages_properties:
        return
    
    # Get all unique property keys
    all_keys = set()
    for props in all_pages_properties:
        all_keys.update(props.keys())
    
    # Write CSV
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
        writer.writeheader()
        writer.writerows(all_pages_properties)
    
    print(f"      📊 Created CSV: {csv_filename}")

def clean_orphaned_files(output_dir, all_current_page_ids, db_configs, dry_run=False):
    """Remove files for pages that no longer exist in Notion."""
    print("\n🧹 Cleaning orphaned files...")
    
    output_path = Path(output_dir)
    if not output_path.exists():
        print("   No output directory exists, nothing to clean")
        return 0
    
    orphaned_count = 0
    
    for db_config in db_configs:
        prefix = db_config['prefix']
        db_name = db_config['name']
        
        # Find all existing folders with this prefix
        existing_folders = list(output_path.glob(f"{prefix}-*"))
        
        if not existing_folders:
            continue
            
        print(f"   Checking {db_name} ({prefix}-*): {len(existing_folders)} existing folders")
        
        for folder in existing_folders:
            # Extract page ID from folder name
            folder_name = folder.name
            if not folder_name.startswith(f"{prefix}-"):
                continue
                
            page_id = folder_name.replace(f"{prefix}-", "")
            
            if page_id not in all_current_page_ids:
                if dry_run:
                    print(f"      🔍 [DRY RUN] Would remove orphaned: {folder_name}")
                else:
                    print(f"      🗑️  Removing orphaned: {folder_name}")
                    try:
                        shutil.rmtree(folder)
                    except Exception as e:
                        print(f"      ❌ Error removing {folder_name}: {e}")
                        continue
                
                orphaned_count += 1
    
    if orphaned_count > 0:
        action = "Would remove" if dry_run else "Removed"
        print(f"✅ {action} {orphaned_count} orphaned files")
    else:
        print("✅ No orphaned files found")
    
    return orphaned_count

def main():
    """Main function - can run tests or full sync."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Notion Database Sync Tool')
    parser.add_argument('--sync', action='store_true', help='Perform incremental sync (default)')
    parser.add_argument('--force', action='store_true', help='Force full sync (ignore timestamps, recreate all files)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without writing files')
    parser.add_argument('--test', action='store_true', help='Run connection and processing tests')
    
    args = parser.parse_args()
    
    # Default to sync mode if no arguments
    if not (args.sync or args.force or args.dry_run or args.test):
        args.sync = True
    
    if args.sync or args.force or args.dry_run:
        sync_type = "Full Sync Mode" if args.force else "Incremental Sync Mode"
        if args.dry_run:
            sync_type = "Dry Run Mode"
        print(f"🚀 Notion Sync - {sync_type}")
        print("=" * 50)
    else:
        print("🚀 Notion Sync - Test Mode")
        print("=" * 50)
    
    # Load configuration
    config = load_config()
    
    # Test output directory
    if not validate_output_directory(config['output_dir']):
        sys.exit(1)
    
    # Initialize Notion client
    client = init_notion_client()
    
    # Test database access
    accessible_dbs, inaccessible_dbs = test_database_access(client, config['databases'])
    
    if not accessible_dbs:
        print("\n❌ No databases accessible. Please check your configuration and permissions.")
        sys.exit(1)
    
    if args.sync or args.force or args.dry_run:
        # Perform sync
        total_synced = full_sync(client, config, dry_run=args.dry_run, force_update=args.force)
        
        if total_synced > 0:
            print(f"\n🎉 Sync completed successfully!")
        else:
            print(f"\n⚠️  No pages were synced.")
    
    else:
        # Run tests
        test_page_extraction(client, accessible_dbs)
        test_block_processing(client, accessible_dbs)
    
    # Summary
    print("\n📊 Summary:")
    print(f"✅ Accessible databases: {len(accessible_dbs)}")
    print(f"❌ Inaccessible databases: {len(inaccessible_dbs)}")
    
    if inaccessible_dbs:
        print("\n⚠️  Issues found:")
        for db_config, error in inaccessible_dbs:
            print(f"   - {db_config['name']}: {error}")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)