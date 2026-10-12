#!/usr/bin/env python3
"""
Add headers and footers to reference ODT document.
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

# Register namespaces
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

def modify_styles_xml(styles_file):
    """Add headers and footers to master pages in styles.xml."""
    tree = ET.parse(styles_file)
    root = tree.getroot()
    
    # Find master-styles section
    master_styles = root.find('office:master-styles', NS)
    if master_styles is None:
        print("No master-styles found!")
        return False
    
    # Clear existing master pages
    for mp in master_styles.findall('style:master-page', NS):
        master_styles.remove(mp)
    
    # Create new master page with headers and footers
    master_page = ET.SubElement(master_styles, f'{{{NS["style"]}}}master-page')
    master_page.set(f'{{{NS["style"]}}}name', 'Standard')
    master_page.set(f'{{{NS["style"]}}}page-layout-name', 'Mpm1')
    
    # Add header (odd pages)
    header = ET.SubElement(master_page, f'{{{NS["style"]}}}header')
    header_p = ET.SubElement(header, f'{{{NS["text"]}}}p')
    header_p.set(f'{{{NS["text"]}}}style-name', 'Header')
    header_span = ET.SubElement(header_p, f'{{{NS["text"]}}}span')
    header_span.text = 'Terran Society: A New Social Contract'
    
    # Add footer
    footer = ET.SubElement(master_page, f'{{{NS["style"]}}}footer')
    footer_p = ET.SubElement(footer, f'{{{NS["text"]}}}p')
    footer_p.set(f'{{{NS["text"]}}}style-name', 'Footer')
    
    # Page number
    page_num = ET.SubElement(footer_p, f'{{{NS["text"]}}}page-number')
    page_num.set(f'{{{NS["text"]}}}select-page', 'current')
    page_num.text = '1'
    
    footer_span = ET.SubElement(footer_p, f'{{{NS["text"]}}}span')
    footer_span.text = ' — Draft v1.0 — 2025'
    
    # Write back
    tree.write(styles_file, encoding='utf-8', xml_declaration=True)
    print(f"✓ Modified {styles_file}")
    return True

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
    
    print(f"✓ Repackaged {output_file}")

def main():
    base_dir = Path(__file__).parent.parent
    extract_dir = base_dir / 'book' / 'ref_temp'
    output_file = base_dir / 'book' / 'reference.odt'
    
    styles_file = extract_dir / 'styles.xml'
    
    if not styles_file.exists():
        print(f"Error: {styles_file} not found!")
        return 1
    
    # Modify styles.xml
    if not modify_styles_xml(styles_file):
        return 1
    
    # Repackage ODT
    repackage_odt(extract_dir, output_file)
    
    print(f"✓ Headers and footers added to {output_file}")
    return 0

if __name__ == '__main__':
    exit(main())
