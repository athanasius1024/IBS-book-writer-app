#!/usr/bin/env python3
"""
Generate PDF from markdown using Pandoc + WeasyPrint (HTML→PDF).
WeasyPrint is lightweight and produces good book formatting.
"""
import subprocess
import sys
import re
from pathlib import Path

def get_glossary_terms():
    """Get all glossary terms from the database."""
    import psycopg2
    
    conn = psycopg2.connect(
        host='localhost',
        database='db_terran_society',
        user='rock',
        password='river'
    )
    cur = conn.cursor()
    
    glossary_terms = set()
    
    # Get role names
    cur.execute('SELECT DISTINCT role_name FROM scm_terran_society.role ORDER BY role_name')
    for row in cur.fetchall():
        glossary_terms.add(row[0])
    
    # Get institution names
    cur.execute('SELECT DISTINCT institution_name FROM scm_terran_society.institution ORDER BY institution_name')
    for row in cur.fetchall():
        glossary_terms.add(row[0])
    
    # Common terms
    common_terms = [
        'District', 'Region', 'World', 'Tier', 'Branch',
        'Elder', 'Representative', 'Fair Witness', 'Arbitrator',
        'Jury', 'Cooperative'
    ]
    glossary_terms.update(common_terms)
    
    conn.close()
    return glossary_terms

def add_glossary_links_to_pdf(html_content, glossary_terms):
    """Add glossary links to PDF HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Note: BeautifulSoup not installed - skipping glossary links in PDF")
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Check if glossary section exists
    glossary_section = soup.find(id='glossary')
    if not glossary_section:
        return html_content
    
    # Sort terms by length (longest first)
    sorted_terms = sorted(glossary_terms, key=len, reverse=True)
    
    # Find all paragraph and list item elements
    content_tags = soup.find_all(['p', 'li'])
    
    for tag in content_tags:
        # Skip if in TOC or glossary
        if tag.find_parent(id='TOC') or tag.find_parent(id='glossary'):
            continue
        
        # Process text nodes
        for text_node in tag.find_all(string=True, recursive=True):
            if text_node.find_parent('a'):
                continue
            
            text = str(text_node)
            
            for term in sorted_terms:
                pattern = r'\b(' + re.escape(term) + r')\b'
                if re.search(pattern, text, re.IGNORECASE):
                    # Create anchor ID
                    anchor_id = 'glossary-' + term.lower().replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '')
                    # Create link
                    new_html = re.sub(
                        pattern,
                        rf'<a href="#{anchor_id}" class="glossary-term" title="See glossary: \1">\1</a>',
                        text,
                        count=1,
                        flags=re.IGNORECASE
                    )
                    if new_html != text:
                        new_soup = BeautifulSoup(new_html, 'html.parser')
                        text_node.replace_with(new_soup)
                        break
    
    return str(soup)

def fix_html_formatting(html_file):
    """Post-process HTML to fix TOC placement, hide Pandoc title block, and add blank pages."""
    with open(html_file, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 1. Hide Pandoc's title-block-header (we use custom cover page instead)
    html = html.replace(
        '<header id="title-block-header">',
        '<header id="title-block-header" style="display: none;">'
    )
    
    # 2. Extract TOC section
    import re
    toc_match = re.search(r'(<nav id="TOC"[^>]*>.*?</nav>)', html, re.DOTALL)
    if not toc_match:
        print("Warning: Could not find TOC in HTML")
        return
    
    toc_html = toc_match.group(1)
    
    # Add "Table of Contents" heading to TOC
    toc_html = toc_html.replace(
        '<nav id="TOC"',
        '<nav id="TOC" style="page-break-before: always;"'
    )
    if '<h1>' not in toc_html:
        toc_html = toc_html.replace(
            '<nav id="TOC" style="page-break-before: always;" role="doc-toc">',
            '<nav id="TOC" style="page-break-before: always;" role="doc-toc"><h1>Table of Contents</h1>'
        )
    
    # 3. Remove TOC from original position
    html = html.replace(toc_match.group(1), '<!-- TOC MOVED -->')
    
    # 4. Find dedication section and insert blank page + TOC after it
    dedication_pos = html.find('id="dedication"')
    if dedication_pos == -1:
        print("Warning: Could not find dedication section")
        return
    
    # Find the page-break-after div after dedication (may have whitespace/newlines)
    dedication_end_pattern = re.search(r'(</section>\s*<div style="page-break-after: always;">\s*</div>)', html[dedication_pos:], re.DOTALL)
    if not dedication_end_pattern:
        print("Warning: Could not find dedication end")
        return
    
    # Insert: blank page + TOC after dedication's page break
    actual_dedication_end = dedication_pos + dedication_end_pattern.end()
    html = html[:actual_dedication_end] + '\n<div class="blank-page"></div>\n' + toc_html + html[actual_dedication_end:]
    
    # 5. Add blank page after cover
    html = re.sub(
        r'(<section id="terran-society" class="cover-page">.*?</section>\s*<div style="page-break-after: always;">\s*</div>)',
        r'\1\n<div class="blank-page"></div>',
        html,
        count=1,
        flags=re.DOTALL
    )
    
    # 6. Remove duplicate page breaks
    # Remove page-break-before after TOC (it will be right before Introduction H1)
    html = re.sub(
        r'(</nav>)\s*<div style="page-break-before: always;">\s*</div>',
        r'\1',
        html,
        flags=re.DOTALL
    )
    
    # Remove duplicate blank pages (two consecutive blank-page divs)
    while '<div class="blank-page"></div>\n<div class="blank-page"></div>' in html:
        html = html.replace(
            '<div class="blank-page"></div>\n<div class="blank-page"></div>',
            '<div class="blank-page"></div>'
        )
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("✓ HTML formatted: TOC moved after dedication, blank pages added, title block hidden")

def main():
    base_dir = Path(__file__).parent.parent
    manuscript = base_dir / 'book' / 'manuscript.md'
    html_file = base_dir / 'book' / 'TerranSocietyBook_pdf.html'  # PDF-specific HTML
    output_pdf = base_dir / 'book' / 'TerranSocietyBook.pdf'
    
    if not manuscript.exists():
        print(f"Error: {manuscript} not found. Generate the book first.")
        return 1
    
    print(f"Generating HTML from {manuscript}...")
    
    # Step 1: Convert markdown to HTML with Pandoc
    html_cmd = [
        'pandoc',
        str(manuscript),
        '-o', str(html_file),
        '--standalone',
        '--toc',
        '--toc-depth=3',
        '--css', str(base_dir / 'templates' / 'book.css'),
        '--metadata', 'title=Terran Society',
    ]
    
    try:
        result = subprocess.run(
            html_cmd,
            capture_output=True,
            text=True,
            cwd=str(base_dir)
        )
        
        if result.returncode != 0:
            print(f"Error generating HTML: {result.stderr}")
            return 1
        
        print(f"✓ HTML generated: {html_file}")
        
    except FileNotFoundError:
        print("Error: pandoc not found.")
        print("Install with: sudo apt-get install pandoc")
        return 1
    
    # Step 2: Add glossary links
    print("Adding glossary term links...")
    glossary_terms = get_glossary_terms()
    print(f"Found {len(glossary_terms)} glossary terms")
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    html_content = add_glossary_links_to_pdf(html_content, glossary_terms)
    
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # Step 3: Post-process HTML formatting
    fix_html_formatting(html_file)
    
    # Step 4: Convert HTML to PDF with WeasyPrint
    print(f"Converting HTML to PDF...")
    
    try:
        from weasyprint import HTML
        
        HTML(filename=str(html_file)).write_pdf(str(output_pdf))
        
        print(f"✓ PDF generated successfully: {output_pdf}")
        print(f"  Size: {output_pdf.stat().st_size / 1024:.1f} KB")
        return 0
        
    except ImportError:
        print("Error: WeasyPrint not found.")
        print("Install with: pip3 install weasyprint")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
