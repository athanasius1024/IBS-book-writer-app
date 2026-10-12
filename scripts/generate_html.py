#!/usr/bin/env python3
"""
Generate HTML version of the book optimized for web viewing.
Includes glossary term hyperlinking.
"""
import subprocess
import sys
import re
from pathlib import Path
import psycopg2

# PostgreSQL connection settings
PG_HOST = 'localhost'
PG_DATABASE = 'db_terran_society'
PG_USER = 'rock'
PG_PASSWORD = 'river'

def get_glossary_terms():
    """Get all glossary terms from the database."""
    conn = psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
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
    
    # Common terms that should be linked
    common_terms = [
        'District', 'Region', 'World', 'Tier', 'Branch',
        'Elder', 'Representative', 'Fair Witness', 'Arbitrator',
        'Jury', 'Cooperative'
    ]
    glossary_terms.update(common_terms)
    
    conn.close()
    return glossary_terms

def move_toc_after_dedication(html_content):
    """Move TOC after dedication page and add book title/subtitle."""
    # Extract TOC
    toc_match = re.search(r'(<nav id="TOC"[^>]*>.*?</nav>)', html_content, re.DOTALL)
    if not toc_match:
        print("Warning: Could not find TOC")
        return html_content
    
    toc_html = toc_match.group(1)
    
    # Add book title, subtitle, and "Table of Contents" heading to TOC
    toc_with_header = '''<div class="toc-page">
<h1 class="toc-title">Terran Society</h1>
<h2 class="toc-subtitle">A New Social Contract</h2>
<h3 class="toc-heading">Table of Contents</h3>
''' + toc_html + '</div>'
    
    # Remove TOC from original position
    html_content = html_content.replace(toc_match.group(1), '<!-- TOC MOVED -->')
    
    # Find dedication section
    dedication_match = re.search(r'(<section[^>]*dedication[^>]*>.*?</section>)', html_content, re.DOTALL)
    if not dedication_match:
        print("Warning: Could not find dedication section")
        return html_content
    
    # Insert TOC after dedication
    dedication_end = dedication_match.end()
    html_content = html_content[:dedication_end] + '\n' + toc_with_header + html_content[dedication_end:]
    
    return html_content

def add_header_and_sidebar(html_content):
    """Add sticky header and floating sidebar navigation."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Create header
    header = soup.new_tag('div', attrs={'class': 'book-header'})
    header_title = soup.new_tag('div', attrs={'class': 'book-header-title'})
    header_title.string = 'Terran Society: A New Social Contract'
    header_nav = soup.new_tag('div', attrs={'class': 'book-header-nav'})
    toc_link = soup.new_tag('a', href='#TOC')
    toc_link.string = 'Table of Contents'
    header_nav.append(toc_link)
    header.append(header_title)
    header.append(header_nav)
    
    # Create sidebar navigation from main headings
    sidebar = soup.new_tag('div', attrs={'class': 'sidebar-nav'})
    sidebar_title = soup.new_tag('h4')
    sidebar_title.string = 'Navigation'
    sidebar.append(sidebar_title)
    sidebar_ul = soup.new_tag('ul')
    
    # Find all H2 headings (main sections)
    for h2 in soup.find_all('h2'):
        if h2.get('id'):
            li = soup.new_tag('li')
            a = soup.new_tag('a', href=f"#{h2.get('id')}")
            a.string = h2.get_text()[:50]  # Truncate long titles
            li.append(a)
            sidebar_ul.append(li)
    
    sidebar.append(sidebar_ul)
    
    # Insert header and sidebar after body tag
    body = soup.find('body')
    if body:
        body.insert(0, sidebar)
        body.insert(0, header)
    
    return str(soup)

def add_glossary_links(html_content, glossary_terms):
    """Add hyperlinks to glossary terms in the HTML content using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Note: BeautifulSoup not installed - skipping glossary links")
        print("Install with: pip3 install beautifulsoup4")
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the glossary section to get the anchor ID
    glossary_section = soup.find(id='glossary')
    if not glossary_section:
        print("Warning: Glossary section not found")
        return html_content
    
    # Sort terms by length (longest first) to avoid partial matches
    sorted_terms = sorted(glossary_terms, key=len, reverse=True)
    
    # Find all paragraph and list item elements (main content)
    content_tags = soup.find_all(['p', 'li'])
    
    for tag in content_tags:
        # Skip if this is in TOC or glossary itself
        if tag.find_parent(id='TOC') or tag.find_parent(id='glossary'):
            continue
        
        # Process text nodes
        for text_node in tag.find_all(string=True, recursive=True):
            # Skip if already in a link
            if text_node.find_parent('a'):
                continue
            
            text = str(text_node)
            modified = False
            
            for term in sorted_terms:
                # Case-insensitive word boundary match
                pattern = r'\b(' + re.escape(term) + r')\b'
                if re.search(pattern, text, re.IGNORECASE):
                    # Create URL-safe anchor ID for the term
                    anchor_id = 'glossary-' + term.lower().replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '')
                    # Create new content with link to specific term
                    new_html = re.sub(
                        pattern,
                        rf'<a href="#{anchor_id}" class="glossary-term" title="See glossary: \1">\1</a>',
                        text,
                        count=1,  # Only link first occurrence in each text node
                        flags=re.IGNORECASE
                    )
                    if new_html != text:
                        # Replace text node with new HTML
                        new_soup = BeautifulSoup(new_html, 'html.parser')
                        text_node.replace_with(new_soup)
                        modified = True
                        break  # Only link one term per text node to avoid over-linking
    
    return str(soup)

def main():
    base_dir = Path(__file__).parent.parent
    manuscript = base_dir / 'book' / 'manuscript.md'
    html_file = base_dir / 'book' / 'TerranSocietyBook_web.html'
    output_html = base_dir / 'book' / 'TerranSocietyBook.html'  # Final output
    
    if not manuscript.exists():
        print(f"Error: {manuscript} not found. Generate the book first.")
        return 1
    
    print(f"Generating HTML from {manuscript}...")
    
    # Step 1: Convert markdown to HTML with Pandoc (without CSS - we'll embed it)
    html_cmd = [
        'pandoc',
        str(manuscript),
        '-o', str(html_file),
        '--standalone',
        '--toc',
        '--toc-depth=3',
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
    
    # Step 2: Post-process HTML - move TOC and add title
    print("Post-processing HTML...")
    
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Move TOC after dedication and add book title/subtitle
    html_content = move_toc_after_dedication(html_content)
    
    # Get glossary terms from database
    glossary_terms = get_glossary_terms()
    print(f"Found {len(glossary_terms)} glossary terms")
    
    # Add glossary links (simplified - only in main content sections)
    # This is a basic implementation - you may want to refine the matching logic
    html_content = add_glossary_links(html_content, glossary_terms)
    
    # Step 3: Embed CSS
    print("Embedding CSS...")
    css_file = base_dir / 'templates' / 'book_html.css'
    with open(css_file, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    # Insert CSS into HTML head
    html_content = html_content.replace(
        '</head>',
        f'<style>{css_content}</style>\n</head>'
    )
    
    # Step 4: Add header and sidebar navigation
    print("Adding header and sidebar navigation...")
    html_content = add_header_and_sidebar(html_content)
    
    # Write final output
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ HTML with glossary links generated: {output_html}")
    print(f"  Size: {output_html.stat().st_size / 1024:.1f} KB")
    
    # Clean up temp file
    if html_file.exists() and html_file != output_html:
        html_file.unlink()
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
