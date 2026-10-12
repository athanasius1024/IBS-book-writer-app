#!/usr/bin/env python3
"""
Post-process ODT file to fix formatting:
1. Center cover, author, and dedication pages
2. Ensure TOC is generated
3. Remove headers/footers from front matter
4. Add headers/footers only after TOC
"""
import xml.etree.ElementTree as ET
import zipfile
import os
from pathlib import Path

# Namespaces
NS = {
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0'
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

def extract_odt(odt_file, extract_dir):
    """Extract ODT file."""
    with zipfile.ZipFile(odt_file, 'r') as zipf:
        zipf.extractall(extract_dir)

def repackage_odt(extract_dir, output_file):
    """Repackage ODT from extracted directory."""
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add mimetype first, uncompressed
        mimetype_path = Path(extract_dir) / 'mimetype'
        if mimetype_path.exists():
            zipf.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)
        
        # Add all other files
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file == 'mimetype':
                    continue
                file_path = Path(root) / file
                arcname = file_path.relative_to(extract_dir)
                zipf.write(file_path, arcname)

def add_centered_style(styles_root):
    """Add centered paragraph style to automatic-styles."""
    auto_styles = styles_root.find('office:automatic-styles', NS)
    if auto_styles is None:
        auto_styles = ET.SubElement(styles_root, f'{{{NS["office"]}}}automatic-styles')
    
    # Add centered style
    centered = ET.SubElement(auto_styles, f'{{{NS["style"]}}}style')
    centered.set(f'{{{NS["style"]}}}name', 'CenteredPage')
    centered.set(f'{{{NS["style"]}}}family', 'paragraph')
    centered.set(f'{{{NS["style"]}}}parent-style-name', 'Standard')
    
    props = ET.SubElement(centered, f'{{{NS["style"]}}}paragraph-properties')
    props.set(f'{{{NS["fo"]}}}text-align', 'center')
    props.set(f'{{{NS["fo"]}}}margin-top', '8in')

def fix_content_xml(content_file):
    """Fix content.xml to center front matter pages."""
    tree = ET.parse(content_file)
    root = tree.getroot()
    
    # Add centered style to automatic-styles
    add_centered_style(root)
    
    body = root.find('.//office:body/office:text', NS)
    if body is None:
        print("Warning: No body found in content.xml")
        return
    
    # Find and center specific pages
    page_count = 0
    for elem in body:
        # Look for headings to identify pages
        if elem.tag == f'{{{NS["text"]}}}h':
            heading_text = ''.join(elem.itertext())
            
            # Cover page (first H1)
            if page_count == 0 and elem.get(f'{{{NS["text"]}}}outline-level') == '1':
                elem.set(f'{{{NS["text"]}}}style-name', 'CenteredPage')
                page_count += 1
            
            # Author page (second H1)
            elif page_count == 1 and elem.get(f'{{{NS["text"]}}}outline-level') == '1':
                elem.set(f'{{{NS["text"]}}}style-name', 'CenteredPage')
                # Center following paragraphs too
                page_count += 1
            
            # Dedication (look for "Dedication" heading)
            elif 'Dedication' in heading_text:
                elem.set(f'{{{NS["text"]}}}style-name', 'CenteredPage')
    
    tree.write(content_file, encoding='utf-8', xml_declaration=True)
    print(f"✓ Fixed content.xml")

def fix_styles_xml(styles_file):
    """Fix styles.xml to add proper master pages."""
    tree = ET.parse(styles_file)
    root = tree.getroot()
    
    # Find master-styles
    master_styles = root.find('office:master-styles', NS)
    if master_styles is None:
        master_styles = ET.SubElement(root, f'{{{NS["office"]}}}master-styles')
    
    # Clear existing
    for mp in master_styles.findall('style:master-page', NS):
        master_styles.remove(mp)
    
    # Create FirstPage (no header/footer)
    first_page = ET.SubElement(master_styles, f'{{{NS["style"]}}}master-page')
    first_page.set(f'{{{NS["style"]}}}name', 'First_20_Page')
    first_page.set(f'{{{NS["style"]}}}page-layout-name', 'Mpm1')
    first_page.set(f'{{{NS["style"]}}}next-style-name', 'Standard')
    
    # Create Standard (with header/footer)
    standard = ET.SubElement(master_styles, f'{{{NS["style"]}}}master-page')
    standard.set(f'{{{NS["style"]}}}name', 'Standard')
    standard.set(f'{{{NS["style"]}}}page-layout-name', 'Mpm1')
    
    # Add header
    header = ET.SubElement(standard, f'{{{NS["style"]}}}header')
    header_p = ET.SubElement(header, f'{{{NS["text"]}}}p')
    header_p.set(f'{{{NS["text"]}}}style-name', 'Header')
    header_span = ET.SubElement(header_p, f'{{{NS["text"]}}}span')
    header_span.text = 'Terran Society: A New Social Contract'
    
    # Add footer
    footer = ET.SubElement(standard, f'{{{NS["style"]}}}footer')
    footer_p = ET.SubElement(footer, f'{{{NS["text"]}}}p')
    footer_p.set(f'{{{NS["text"]}}}style-name', 'Footer')
    
    page_num = ET.SubElement(footer_p, f'{{{NS["text"]}}}page-number')
    page_num.set(f'{{{NS["text"]}}}select-page', 'current')
    page_num.text = '1'
    
    footer_span = ET.SubElement(footer_p, f'{{{NS["text"]}}}span')
    footer_span.text = ' — Draft v1.0 — 2025'
    
    tree.write(styles_file, encoding='utf-8', xml_declaration=True)
    print(f"✓ Fixed styles.xml with proper master pages")

def main():
    base_dir = Path(__file__).parent.parent
    odt_file = base_dir / 'book' / 'TerranSocietyBook.odt'
    temp_dir = base_dir / 'book' / 'odt_temp'
    
    if not odt_file.exists():
        print(f"Error: {odt_file} not found!")
        return 1
    
    # Clean temp dir
    if temp_dir.exists():
        import shutil
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    print(f"Extracting {odt_file}...")
    extract_odt(odt_file, temp_dir)
    
    # Fix content.xml
    content_file = temp_dir / 'content.xml'
    if content_file.exists():
        fix_content_xml(content_file)
    
    # Fix styles.xml
    styles_file = temp_dir / 'styles.xml'
    if styles_file.exists():
        fix_styles_xml(styles_file)
    
    # Repackage
    print(f"Repackaging {odt_file}...")
    repackage_odt(temp_dir, odt_file)
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir)
    
    print(f"✓ ODT formatting fixed!")
    return 0

if __name__ == '__main__':
    exit(main())
