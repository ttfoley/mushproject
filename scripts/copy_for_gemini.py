#!/usr/bin/env python3
"""
Copy codebase for Gemini/AI tools with folder structure preservation.

This script:
- Always preserves all folder structure (except .* folders)  
- Only copies content from selected top-level folders
- Provides interactive folder selection
- Has safety checks to prevent overwriting source
"""

import os
import shutil
import argparse
from pathlib import Path
from typing import List, Set

def get_folder_size(path: Path) -> int:
    """Get folder size in bytes."""
    total_size = 0
    try:
        for file_path in path.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
    except (PermissionError, OSError):
        pass
    return total_size

def format_size(size_bytes: int) -> str:
    """Format size in human readable format."""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def scan_top_level_folders(source_dir: Path) -> List[Path]:
    """Get all top-level folders, excluding .* folders."""
    folders = []
    for item in source_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            folders.append(item)
    return sorted(folders)

def interactive_folder_selection(folders: List[Path]) -> List[Path]:
    """Let user select which folders to copy content from."""
    print("\n📁 Available folders:")
    print("=" * 60)
    
    for i, folder in enumerate(folders, 1):
        size = get_folder_size(folder)
        file_count = sum(1 for _ in folder.rglob('*') if _.is_file())
        print(f"{i:2d}. {folder.name:<25} {format_size(size):>10} ({file_count} files)")
    
    print("\n🏗️  FOLDER STRUCTURE: All folders will be created to preserve structure")
    print("📁 CONTENT COPYING: Select which folders to copy content from:")
    print("- Enter numbers separated by spaces (e.g., '1 3 5')")
    print("- Enter 'all' to copy content from all folders")
    print("- Enter 'docs' to copy only from 'docs' folder")
    print("- Press Enter to copy content from all folders")
    
    while True:
        try:
            selection = input("\nCopy content from folders: ").strip().lower()
            
            if not selection or selection == 'all':
                return folders
            elif selection == 'docs':
                docs_folders = [f for f in folders if f.name == 'docs']
                if not docs_folders:
                    print("❌ No 'docs' folder found")
                    continue
                return docs_folders
            else:
                # Parse numbers
                indices = [int(x) - 1 for x in selection.split()]
                selected = [folders[i] for i in indices if 0 <= i < len(folders)]
                if not selected:
                    print("❌ No valid folders selected")
                    continue
                return selected
        except (ValueError, IndexError):
            print("❌ Invalid selection. Please try again.")

def create_empty_structure(src_dir: Path, dst_dir: Path):
    """Create empty directory structure recursively."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    
    for item in src_dir.iterdir():
        if item.is_dir():
            create_empty_structure(item, dst_dir / item.name)

def copy_folder_content(src_dir: Path, dst_dir: Path) -> tuple:
    """Recursively copy all content from src to dst. Returns (files_copied, bytes_copied)."""
    files_copied = 0
    bytes_copied = 0
    
    # Ensure destination exists
    dst_dir.mkdir(parents=True, exist_ok=True)
    
    for item in src_dir.iterdir():
        dst_item = dst_dir / item.name
        
        if item.is_dir():
            sub_files, sub_bytes = copy_folder_content(item, dst_item)
            files_copied += sub_files
            bytes_copied += sub_bytes
        else:
            try:
                shutil.copy2(item, dst_item)
                files_copied += 1
                bytes_copied += item.stat().st_size
            except (PermissionError, OSError) as e:
                print(f"⚠️  Skipped {item}: {e}")
    
    return files_copied, bytes_copied

def main():
    parser = argparse.ArgumentParser(description="Copy codebase for Gemini/AI tools")
    parser.add_argument('--source', '-s', type=Path, default=Path('.').parent,
                       help='Source directory (default: parent of scripts/)')
    parser.add_argument('--output', '-o', type=Path, default=Path('/home/ttfoley/content_for_gemini'),
                       help='Output directory (default: /home/ttfoley/content_for_gemini)')
    
    args = parser.parse_args()
    
    source_dir = args.source.resolve()
    output_dir = args.output.resolve()
    codebase_dir = output_dir / 'codebase'
    
    # Safety check: prevent copying to/from the same directory
    if source_dir == codebase_dir or codebase_dir in source_dir.parents or source_dir in codebase_dir.parents:
        print("❌ SAFETY ERROR: Cannot copy to/from the same directory!")
        print(f"   Source: {source_dir}")
        print(f"   Target: {codebase_dir}")
        return
    
    print(f"🚀 Copy Codebase for Gemini")
    print(f"📂 Source: {source_dir}")
    print(f"📁 Target: {codebase_dir}")
    
    # Get all top-level folders (excluding .* folders)
    folders = scan_top_level_folders(source_dir)
    
    if not folders:
        print("❌ No folders found to copy")
        return
    
    # Let user select which folders to copy content from
    selected_folders = interactive_folder_selection(folders)
    
    print(f"\n✅ Selected {len(selected_folders)} folders for content copying:")
    for folder in selected_folders:
        print(f"   📁 {folder.name}")
    
    # Clean target directory
    if codebase_dir.exists():
        print(f"\n🗑️  Cleaning target directory...")
        shutil.rmtree(codebase_dir)
    
    # Step 1: Create empty structure for ALL folders
    print(f"\n🏗️  Creating folder structure for all {len(folders)} folders...")
    for folder in folders:
        print(f"   📁 {folder.name} (structure only)")
        create_empty_structure(folder, codebase_dir / folder.name)
    
    # Step 2: Copy content for SELECTED folders
    print(f"\n📋 Copying content for {len(selected_folders)} selected folders...")
    total_files = 0
    total_bytes = 0
    
    for folder in selected_folders:
        print(f"   📁 {folder.name}...", end=' ')
        files, bytes_copied = copy_folder_content(folder, codebase_dir / folder.name)
        total_files += files
        total_bytes += bytes_copied
        print(f"✅ {files} files, {format_size(bytes_copied)}")
    
    # Summary
    print(f"\n🎉 Copy completed!")
    print(f"📊 Content copied: {total_files} files, {format_size(total_bytes)}")
    print(f"🏗️  Structure preserved: {len(folders)} folders")
    print(f"📁 Target: {codebase_dir}")

if __name__ == '__main__':
    main() 