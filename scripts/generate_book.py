#!/usr/bin/env python3
"""
Generate the Terran Society book manuscript in Markdown format.
"""

import psycopg2
import psycopg2.extras
from pathlib import Path

# PostgreSQL connection settings
PG_HOST = 'localhost'
PG_DATABASE = 'db_terran_society'
PG_USER = 'rock'
PG_PASSWORD = 'river'
PG_SCHEMA = 'scm_terran_society'

INPUTS_PATH = Path(__file__).parent.parent / 'inputs'
OUTPUT_PATH = Path(__file__).parent.parent / 'book' / 'manuscript.md'

def get_connection():
    conn = psycopg2.connect(
        host=PG_HOST,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    )
    return conn

def load_rights():
    """Load Rights of the People from source"""
    rights_file = INPUTS_PATH / 'trifold-basic-rights_2021April-reformatJul2025.txt'
    with open(rights_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract rights section
    rights_start = content.find('01 Each Person')
    rights_end = content.find('~ ~ ~ ~')
    rights_text = content[rights_start:rights_end].strip()
    
    # Parse individual rights
    rights = []
    lines = rights_text.split('\n')
    current_right = []
    current_num = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if starts with number
        if line[:2].isdigit():
            if current_right:
                rights.append((current_num, ' '.join(current_right)))
            current_num = line[:2]
            current_right = [line[2:].strip()]
        else:
            if current_right:
                current_right.append(line)
    
    if current_right:
        rights.append((current_num, ' '.join(current_right)))
    
    return rights

def load_principles():
    """Load Basic Principles"""
    principles = [
        ("Operations Transparency", "Terran Society operations need to be open, transparent and accessible to all members as the base of power is the informed individual."),
        ("Member-Centric Design", "Terran Society services and systems must be designed, developed and administered for the benefit of all members."),
        ("Environmental Stewardship", "We are caretakers in this wonderful world shared with many other beings, pollution of air, water and land is to be avoided and cleaned up."),
        ("Equal Regional Treatment", "Services provided to Regions must be administered equally per Region."),
        ("Sustainable Infrastructure", "Permanent structures & facilities shall be designed to last for future generations, have minimal maintenance and be as energy independent and efficient as is practical."),
        ("Regional Self-Sufficiency", "Each community and region should be self-sufficient in a sustainable way for meeting their basic needs."),
        ("Single Branch Service", "A Person may be on the staff of only one branch of World, Regional or District management or the Defense Force at a time."),
        ("Inviolable Voting Rights", "Voting rights and benefits cannot be revoked as punishment or penalty."),
    ]
    return principles

def load_book_metadata(conn):
    """Load book metadata from database."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM scm_terran_society.book_metadata WHERE metadata_id = 1')
    return cur.fetchone()

def load_authors(conn):
    """Load authors from database."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM scm_terran_society.book_author ORDER BY sort_order')
    return cur.fetchall()

def generate_title_page(metadata):
    """Generate title page with Pandoc metadata."""
    md = f"---\n"
    md += f"title: \"{metadata['title']}\"\n"
    if metadata.get('subtitle'):
        md += f"subtitle: \"{metadata['subtitle']}\"\n"
    md += f"author: \"Angelo Patrick Arteman\"\n"
    
    # Add version and date 
    if metadata.get('current_version'):
        md += f"version: \"{metadata['current_version']}\"\n"
    if metadata.get('version_date'):
        md += f"date: \"{metadata['version_date']}\"\n"
    
    md += f"---\n\n"
    
    # Cover page - title, subtitle, author, date all centered
    md += '<div class="cover-page">\n\n'
    md += f'# {metadata["title"]}\n\n'
    if metadata.get('subtitle'):
        md += f'**{metadata["subtitle"]}**\n\n'
    md += '\n\n\n\n\n\n'  # More white space after subtitle
    md += '<span class="cover-author">Angelo Patrick Arteman</span>\n\n'
    if metadata.get('version_date'):
        md += f'<span class="cover-date">{metadata["version_date"]}</span>\n\n'
    md += '</div>\n\n'
    
    md += "<div style='page-break-after: always;'></div>\n\n"
    return md

def generate_author_page(metadata, authors):
    """Generate author page with title, subtitle, author and copyright - all centered."""
    md = '<div class="author-page">\n\n'
    
    # Title and subtitle
    md += f'{metadata["title"]}\n\n'
    if metadata.get('subtitle'):
        md += f'{metadata["subtitle"]}\n\n'
    
    md += "\n\n\n\n"  # White space
    
    # Author
    for author in authors:
        md += f"{author['author_name']}"
        if author.get('author_role'):
            md += f", {author['author_role']}"
        md += "\n\n"
    
    # Copyright
    if metadata.get('copyright_holder') and metadata.get('copyright_year'):
        md += f"© {metadata['copyright_year']} {metadata['copyright_holder']}\n\n"
    
    md += '</div>\n\n'
    md += "<div style='page-break-after: always;'></div>\n\n"
    # Add blank page before dedication
    md += "<div class='blank-page'></div>\n\n"
    return md

def generate_dedication_page(metadata):
    """Generate dedication page - centered."""
    if not metadata.get('dedication_text'):
        return ""
    
    md = '<div class="dedication-page">\n\n'
    md += "## Dedication\n\n"
    md += f"{metadata['dedication_text']}\n\n"
    if metadata.get('dedication_attribution'):
        md += f"{metadata['dedication_attribution']}\n\n"
    md += '</div>\n\n'
    
    # Page break after dedication - TOC will be inserted here by post-processing
    md += "<div style='page-break-after: always;'></div>\n\n"
    return md

def generate_table_of_contents():
    """Generate placeholder for table of contents."""
    # Pandoc will insert TOC automatically with --toc flag
    # No additional page breaks needed here - TOC will be moved by post-processing
    return ""

def generate_introduction():
    return """# Terran Society: A New Social Contract

## Introduction

Terran Society represents a comprehensive framework for human governance designed to protect individual rights, ensure accountability, and create sustainable prosperity. Unlike traditional systems of governance that concentrate power, Terran Society distributes authority across multiple tiers and branches with built-in checks and balances.

The foundation of this system rests on two pillars: the Rights of the People and the Basic Principles. These establish the core values that guide every aspect of Terran Society's operations. From these foundations emerges an organizational structure spanning three tiers—District, Region, and World—each with specific responsibilities and limitations.

### Core Objectives

Terran Society exists to:

1. **Protect the Rights of the People** – Every member's fundamental rights are guaranteed and actively defended
2. **Meet Basic Needs** – Ensure all members have access to clean food, water, air, shelter, safety, privacy, information, travel, and healthcare
3. **Provide Just Governance** – Create transparent, accountable systems for collective decision-making
4. **Enable Peaceful Resolution** – Establish fair processes for resolving disputes without violence
5. **Ensure Common Defense** – Protect the society and its members from external threats
6. **Foster Sustainability** – Build systems that can endure for generations while respecting the natural world

### Why a New System?

Current governance systems worldwide share common flaws: concentrated power, lack of transparency, erosion of individual rights, and structures that serve special interests rather than the people. Terran Society addresses these systemic problems through:

- **Decentralization** – Power is distributed across regions and branches, preventing dangerous concentrations
- **Transparency** – The Fair Witness branch ensures all Society operations are recorded and public
- **Direct Accountability** – Most major positions are directly elected by the people they serve
- **Rights-First Approach** – The Rights of the People cannot be legislated away
- **Practical Scale** – Regions are sized for responsive governance (maximum 20-25 million people)

### How to Use This Book

This book provides a comprehensive guide to Terran Society's structure and operations. It is organized to build understanding progressively:

- **Basic Principles** – The fundamental values guiding all operations
- **Rights of the People** – The complete enumeration of protected rights
- **Organizational Structure** – Detailed explanation of each tier and branch
- **Roles and Responsibilities** – Clear definitions of every position and duty
- **Processes and Procedures** – How elections, legislation, courts, and other systems operate

Throughout this book, terms appearing in the Glossary are capitalized when referring to specific offices or institutions (e.g., "Administrator" for the office, "administrator" for the general concept).

"""

def generate_principles(principles):
    md = "<div style='page-break-before: always;'></div>\n\n## Basic Principles of Terran Society\n\n"
    md += "These eight principles guide all operations and decisions within Terran Society. They serve as a philosophical foundation ensuring that systems remain focused on member welfare, transparency, and sustainability.\n\n"
    
    for i, (title, desc) in enumerate(principles, 1):
        md += f"### Principle {i}: {title}\n\n"
        md += f"{desc}\n\n"
        
        # Add elaboration
        if i == 1:
            md += "This principle recognizes that an informed citizenry is the only reliable check on power. All meetings of governing bodies must be observed by Fair Witnesses, and records must be freely accessible. Secret legislation or hidden agendas cannot exist in this system.\n\n"
        elif i == 2:
            md += "Society management exists to serve the people, not the other way around. Every system, service, and structure must be evaluated based on whether it benefits all members. Policies that advantage one group at the expense of others violate this principle.\n\n"
        elif i == 3:
            md += "Humans are part of a larger ecological community. Our survival depends on clean air, water, and soil. This principle establishes environmental protection not as an optional add-on, but as a core requirement. The Environmental Guardian role exists at both Regional and World levels to enforce this principle.\n\n"
        elif i == 4:
            md += "No Region should receive preferential treatment in the allocation of resources or services. This ensures fairness and prevents regional rivalry. World-level services are distributed equally per Region regardless of population, wealth, or political influence.\n\n"
        elif i == 5:
            md += "Short-term thinking creates long-term problems. Terran Society requires that infrastructure be built to last generations, minimizing the burden on future members. This principle encourages renewable energy, durable materials, and efficient design.\n\n"
        elif i == 6:
            md += "Resilience comes from local self-sufficiency. While trade and cooperation between Regions are encouraged, each Region should be capable of meeting its own basic needs. This prevents cascading failures and reduces vulnerability to disruption.\n\n"
        elif i == 7:
            md += "To prevent conflicts of interest and ensure focused service, individuals cannot simultaneously serve in multiple branches or tiers. This also distributes leadership opportunities across more people.\n\n"
        elif i == 8:
            md += "Voting rights and membership benefits are fundamental and cannot be revoked as punishment. Even those convicted of crimes retain their voice in society. This prevents the creation of a permanent underclass and ensures that everyone maintains a stake in the system.\n\n"
    
    return md

def generate_rights(rights):
    md = "<div style='page-break-before: always;'></div>\n\n## Rights of the People\n\n"
    md += "These 31 rights form the cornerstone of Terran Society. They are in-alienable, meaning they cannot be legislated away, suspended, or revoked. Every law, every Society action, and every institution must respect these rights.\n\n"
    md += "### Foundational Statement\n\n"
    md += "We are endowed by our Creator with certain in-alienable Rights, among these are Life, Liberty and the Pursuit of Happiness. These Rights are not to be violated by institutions, organizations or individuals. Our duty is to protect these Rights.\n\n"
    md += "### The Rights\n\n"
    
    for num, text in rights:
        md += f"#### Right {num}\n\n"
        md += f"{text}\n\n"
    
    return md

def generate_org_overview(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Organizational Structure Overview\n\n"
    md += "Terran Society is organized into three tiers, each with specific roles and responsibilities. At the Regional and World levels, these tiers are further divided into branches that provide checks and balances on each other.\n\n"
    
    md += "### Organizational Hierarchy\n\n"
    md += "The structure operates on clear hierarchical principles:\n\n"
    md += "**District Level:**\n"
    md += "- Council of Elders (7-9 members)\n"
    md += "- District Representative (to Regional Council)\n\n"
    
    md += "**Regional Level:**\n"
    md += "- **Executive Branch**: Five offices, each headed by an elected official with subordinate staff\n"
    md += "  - Office of Regional Administrator (with Deputy, Directors of Elections/Infrastructure/Public Services)\n"
    md += "  - Office of Regional Treasurer (with Deputy, Directors of Budget/Audits)\n"
    md += "  - Office of Regional Sheriff (with Deputy Sheriff, Marshal, Chief Investigator)\n"
    md += "  - Office of Regional Environmental Guardian (with Deputy, Directors of Monitoring/Restoration)\n"
    md += "  - Office of Regional Ambassador (with Deputy, Economic Development Director, Consular Officer)\n"
    md += "- **Legislative Branch**: Regional Council of the People (one Representative per District)\n"
    md += "- **Judicial Branch**: Three offices\n"
    md += "  - Office of Guarantor of Rights (with Rights Investigator)\n"
    md += "  - Office of Facilitator of the Court (with Court Administrator)\n"
    md += "  - Office of Public Arbitrator\n"
    md += "- **Fair Witness Branch**: Regional Fair Witness Council\n\n"
    
    md += "**World Level:**\n"
    md += "- **Executive Branch**: World Executive Council plus five offices (Administrator, Treasurer, Ambassador, Sheriff, Environmental Guardian)\n"
    md += "- **Legislative Branch**: Council of the Regions (Regional representation) and World Council of the People\n"
    md += "- **Judicial Branch**: World Court (handles inter-Regional disputes)\n"
    md += "- **Fair Witness Branch**: World Fair Witness Council\n"
    md += "- **Military Branch**: World Defense Force, Defense Force Intelligence, Defense Force Council\n\n"
    
    md += "### The Three Tiers\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT t.tier_name, te.explain_desc 
        FROM scm_terran_society.tier t
        LEFT JOIN scm_terran_society.tier_explain te ON t.tier_id = te.tier_id
        ORDER BY t.sort_order
    ''')
    
    for row in cur.fetchall():
        md += f"#### {row['tier_name']}\n\n"
        md += f"{row['explain_desc']}\n\n"
    
    md += "### The Branches\n\n"
    md += "At the Regional and World levels, governance is organized into distinct branches, each with different responsibilities:\n\n"
    
    cur.execute('''
        SELECT branch_name, branch_desc
        FROM scm_terran_society.branch
        ORDER BY sort_order
    ''')
    
    for row in cur.fetchall():
        md += f"**{row['branch_name']} Branch**: {row['branch_desc']}\n\n"
    
    return md

def generate_district_level(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## District Level Governance\n\n"
    md += "The District is the most local tier of Terran Society, designed to be small enough that residents personally know at least one Elder. Districts typically range from 5,000 to 21,000 people.\n\n"
    
    md += "### Council of Elders\n\n"
    md += "The Council of Elders serves as the primary governance body at the District level. Its focus is on community cohesion, family welfare, and peaceful dispute resolution.\n\n"
    
    md += "#### Composition\n\n"
    md += "- Seven to nine elected Elders, depending on District population\n- Three-year terms with staggered elections (one-third up for election each year)\n- No term limits\n- Candidates must demonstrate compassion and love for children\n- Preferably at least 55 years of age\n\n"
    
    md += "#### Responsibilities\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT rd.duty_header, rd.duty_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.role_duty rd ON r.role_id = rd.role_id
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Council of Elders'
        AND r.role_name = 'Elder'
        ORDER BY rd.sort_order
    ''')
    
    for row in cur.fetchall():
        md += f"**{row['duty_header']}**: {row['duty_desc']}\n\n"
    
    md += "#### Safe Haven\n\n"
    md += "Each Council of Elders maintains a safe haven—a secure location where children or family members in crisis can temporarily stay. This provides immediate protection while the Council works to resolve the underlying issues and restore the family unit.\n\n"
    
    md += "#### Limitations\n\n"
    md += "The Council of Elders:\n"
    md += "- Cannot tax or charge service fees (funded through Regional budget allocation)\n"
    md += "- Cannot compel anyone to appear or enforce decisions (unresolved issues escalate to Sheriff or Courts)\n"
    md += "- Serves a voluntary mediation role—parties must agree to Council involvement\n\n"
    
    md += "### District Representative\n\n"
    md += "Each District elects one Representative to the Regional Council of the People. This provides direct representation in Regional legislation and ensures District concerns are heard at the Regional level.\n\n"
    
    md += "### District Elections\n\n"
    md += "District elections occur on a three-year cycle. The Administrator's Department manages the election process, ensuring:\n\n"
    md += "- Transparent candidate disclosure\n"
    md += "- Public forums for debate and questions\n"
    md += "- Physical ballots verified by voters\n"
    md += "- Ballots counted publicly and retained for 10 years\n"
    md += "- No party affiliation required\n"
    md += "- No money in campaigns\n\n"
    
    return md

def generate_fair_witness_chapter(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## The Fair Witness Branch\n\n"
    
    # Get the concept explanation from institution_explain and use it as introduction
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT ie.explain_desc
        FROM scm_terran_society.institution_explain ie
        JOIN scm_terran_society.institution i ON ie.institution_id = i.institution_id
        WHERE i.institution_name = 'Regional Fair Witness Council'
        AND ie.explain_header = 'Fair Witness Concept and Purpose'
        LIMIT 1
    ''')
    
    concept_row = cur.fetchone()
    if concept_row:
        md += f"{concept_row['explain_desc']}\n\n"
    else:
        # Fallback to original text if not found
        md += "The Fair Witness branch provides independent, objective observation and record-keeping for all Society operations. Inspired by Robert A. Heinlein's \"Stranger in a Strange Land\", this concept resolves a critical problem: those in power cannot be trusted to keep proper records on themselves. Fair Witnesses are trained to be impartial, non-biased witnesses with linguistic mastery and keen observation skills. Their independence ensures badly needed credibility, fairness, and openness.\n\n"
    
    md += "### Purpose and Independence\n\n"
    md += "Fair Witnesses resolve the problem of record-keeping through absolute independence. They are trained as impartial, non-biased witnesses with linguistic mastery and keen observation skills. Their role is strictly observational—they have no other authority. This is not a police role.\n\n"
    
    md += "It is a criminal act to influence a Fair Witness in any way that could compromise them. This would be a violation of Rights where the victim is the whole Society. Fair Witnesses are the only designated group with such protective status.\n\n"
    
    # Training Hierarchy
    md += "### Training Hierarchy\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Get Fair Witness roles in order
    cur.execute('''
        SELECT r.role_name, r.role_desc, re.explain_header, re.explain_desc
        FROM scm_terran_society.role r
        LEFT JOIN scm_terran_society.role_explain re ON r.role_id = re.role_id
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name LIKE '%Fair Witness%'
        AND r.role_name IN ('Fair Witness Trainee', 'Fair Witness Apprentice', 'Certified Fair Witness', 'Senior Certified Fair Witness')
        ORDER BY r.sort_order
    ''')
    
    for row in cur.fetchall():
        md += f"#### {row['role_name']}\n\n"
        md += f"{row['role_desc']}\n\n"
        if row['explain_desc']:
            md += f"{row['explain_desc']}\n\n"
    
    # Panel Structure
    md += "### Fair Witness Panels\n\n"
    md += "Fair Witnesses are governed by a two-tiered panel system consistent with the Regional and World structure. These panels oversee administration of the branch, with full authority to de-certify, reprimand, or order additional training of Certified Fair Witnesses.\n\n"
    
    # Get panel institutions (unique only)
    cur.execute('''
        SELECT DISTINCT i.institution_name, i.institution_desc
        FROM scm_terran_society.institution i
        WHERE i.institution_name LIKE '%Fair Witness Council'
        ORDER BY i.institution_name
    ''')
    
    processed_institutions = set()
    for row in cur.fetchall():
        # Skip if already processed
        if row['institution_name'] in processed_institutions:
            continue
        processed_institutions.add(row['institution_name'])
        
        md += f"#### {row['institution_name']}\n\n"
        md += f"{row['institution_desc']}\n\n"
        
        # Add explanations, but skip "Fair Witness Concept and Purpose" since it's at the top
        cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur2.execute('''
            SELECT explain_header, explain_desc
            FROM scm_terran_society.institution_explain ie
            JOIN scm_terran_society.institution i ON ie.institution_id = i.institution_id
            WHERE i.institution_name = %s
            AND ie.explain_header != 'Fair Witness Concept and Purpose'
            ORDER BY ie.sort_order
        ''', (row['institution_name'],))
        
        for explain in cur2.fetchall():
            md += f"**{explain['explain_header']}**: {explain['explain_desc']}\n\n"
    
    # Responsibilities
    md += "### Fair Witness Responsibilities\n\n"
    md += "Fair Witnesses serve as record keepers and librarians for all Society operations:\n\n"
    md += "- **Unrestricted Access**: Fair Witnesses have unrestricted access to Executive, Legislative, and Judicial branch operations\n"
    md += "- **Record Keeping**: Prepare and maintain meeting minutes, logs, and all manner of records\n"
    md += "- **Library Management**: Create and maintain freely accessible libraries of records for all Citizens\n"
    md += "- **Linguistic Mastery**: Must be fluent in all languages used in Society operations\n"
    md += "- **Observation Only**: No other authority beyond observation and documentation\n"
    md += "- **Identification**: Must wear visible badge, symbol, or attire to openly identify their presence\n\n"
    
    # Accountability
    md += "### Accountability and Recall\n\n"
    md += "While Fair Witnesses hold life appointments, they can be removed for breach of trust through a careful process designed to prevent political abuse. A Citizen complaint must be endorsed by both a Regional Representative AND the Regional Executive, then approved by majority vote of the Regional Council. This same-tier requirement ensures Fair Witnesses cannot be removed for political reasons while maintaining accountability to the People.\n\n"
    
    return md

def generate_regional_executive_chapter(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Regional Executive Branch\n\n"
    md += "The Regional Executive Branch administers daily operations, public services, and implementation of legislation. It consists of five major offices, each headed by an elected official with supporting staff.\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Get all Regional Executive institutions in order
    regional_exec_offices = [
        'Office of Regional Administrator',
        'Office of Regional Treasurer',
        'Office of Regional Sheriff',
        'Office of Regional Environmental Guardian',
        'Office of Regional Ambassador'
    ]
    
    for office_name in regional_exec_offices:
        md += f"### {office_name}\n\n"
        
        # Get institution description
        cur.execute('''
            SELECT institution_desc
            FROM scm_terran_society.institution
            WHERE institution_name = %s
        ''', (office_name,))
        inst_row = cur.fetchone()
        if inst_row:
            md += f"{inst_row['institution_desc']}\n\n"
        
        # Get all roles for this office
        cur.execute('''
            SELECT r.role_name, r.role_desc
            FROM scm_terran_society.role r
            JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
            WHERE i.institution_name = %s
            ORDER BY r.sort_order
        ''', (office_name,))
        
        roles = cur.fetchall()
        if not roles:
            continue
        
        # First role is the head of office
        head_role = roles[0]
        md += f"#### {head_role['role_name']}\n\n"
        md += f"{head_role['role_desc']}\n\n"
        
        # Get duties for the head role
        cur.execute('''
            SELECT rd.duty_header, rd.duty_desc
            FROM scm_terran_society.role_duty rd
            JOIN scm_terran_society.role r ON rd.role_id = r.role_id
            JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
            WHERE i.institution_name = %s
            AND r.role_name = %s
            ORDER BY rd.sort_order
        ''', (office_name, head_role['role_name']))
        
        duties = cur.fetchall()
        if duties:
            md += "**Key Responsibilities:**\n\n"
            for duty in duties:
                md += f"- **{duty['duty_header']}**: {duty['duty_desc']}\n"
            md += "\n"
        
        # List subordinate roles if any
        if len(roles) > 1:
            md += "**Subordinate Roles:**\n\n"
            for role in roles[1:]:
                md += f"- **{role['role_name']}**: {role['role_desc']}\n"
            md += "\n"
    
    # Add general Executive Branch information
    md += "### Executive Council Coordination\n\n"
    md += "The five elected heads of the Regional Executive offices form the Executive Council. This council coordinates executive operations, discusses inter-departmental matters, and ensures unified implementation of Regional policy.\n\n"
    
    md += "**Executive Authority:**\n\n"
    md += "- Implement laws passed by the Regional Council\n"
    md += "- Manage Regional budget and operations\n"
    md += "- Provide public services to all Districts\n"
    md += "- Sign or veto legislation (First Executive)\n"
    md += "- Appoint department heads (subject to Council approval)\n"
    md += "- No authority to remove elected officials\n\n"
    
    md += "**Executive Accountability:**\n\n"
    md += "- All executive officials are directly elected by the people\n"
    md += "- Subject to impeachment by Regional Council for cause\n"
    md += "- Operations observed by Fair Witnesses for transparency\n"
    md += "- Budget and spending subject to legislative approval\n\n"
    
    return md

def generate_legislative_chapter(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Legislative Branch\n\n"
    md += "The Legislative Branch is the primary law-making and oversight body within Terran Society. It operates at both District and Regional levels, with elected representatives directly accountable to the people they serve.\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Regional Council of the People
    md += "### Regional Council of the People\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Regional Council of the People'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    
    md += "#### Structure and Composition\n\n"
    md += "The Regional Council consists of elected Representatives, with one Representative per District. This ensures direct representation of local interests at the Regional level.\n\n"
    
    md += "#### Roles and Responsibilities\n\n"
    
    # Get Representative role and duties
    cur.execute('''
        SELECT r.role_name, r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Regional Council of the People'
        AND r.role_name = 'Representative'
    ''')
    rep_row = cur.fetchone()
    if rep_row:
        md += f"**{rep_row['role_name']}**\n\n"
        md += f"{rep_row['role_desc']}\n\n"
        
        # Get duties
        cur.execute('''
            SELECT rd.duty_header, rd.duty_desc
            FROM scm_terran_society.role_duty rd
            JOIN scm_terran_society.role r ON rd.role_id = r.role_id
            JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
            WHERE i.institution_name = 'Regional Council of the People'
            AND r.role_name = 'Representative'
            ORDER BY rd.sort_order
        ''')
        
        for duty in cur.fetchall():
            md += f"- **{duty['duty_header']}**: {duty['duty_desc']}\n"
        md += "\n"
    
    # Council administrative roles
    md += "#### Administrative Roles\n\n"
    cur.execute('''
        SELECT r.role_name, r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Regional Council of the People'
        AND r.role_name != 'Representative'
        ORDER BY r.sort_order
    ''')
    
    for role in cur.fetchall():
        md += f"**{role['role_name']}**: {role['role_desc']}\n\n"
    
    md += "#### Legislative Authority\n\n"
    md += "The Regional Council has authority to:\n\n"
    md += "- Pass laws and spending legislation within their jurisdiction\n"
    md += "- Approve major appointments by the First Executive\n"
    md += "- Conduct investigative hearings and compel witnesses\n"
    md += "- Define representative districts (must be simple, not contorted)\n"
    md += "- Impeach members of the Executive and Judicial branches for cause\n"
    md += "- Charter organizations operating within the Region\n\n"
    
    md += "All laws must conform to the Rights of the People without exception. All meetings must be observed by Fair Witnesses or proceedings are null and void.\n\n"
    
    return md

def generate_judicial_chapter(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Judicial Branch\n\n"
    md += "The Judicial Branch provides dispute resolution, rights protection, and justice through a multi-tiered court system. All judicial proceedings are public, observed by Fair Witnesses, and decided by citizen juries.\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Office of Guarantor of Rights
    md += "### Office of Guarantor of Rights\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Office of Guarantor of Rights'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    
    md += "#### Guarantor of Rights\n\n"
    cur.execute('''
        SELECT r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Guarantor of Rights'
        AND r.role_name = 'Guarantor of Rights'
    ''')
    role = cur.fetchone()
    if role:
        md += f"{role['role_desc']}\n\n"
    
    # Get duties
    cur.execute('''
        SELECT rd.duty_header, rd.duty_desc
        FROM scm_terran_society.role_duty rd
        JOIN scm_terran_society.role r ON rd.role_id = r.role_id
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Guarantor of Rights'
        AND r.role_name = 'Guarantor of Rights'
        ORDER BY rd.sort_order
    ''')
    
    md += "**Responsibilities:**\n\n"
    for duty in cur.fetchall():
        md += f"- **{duty['duty_header']}**: {duty['duty_desc']}\n"
    md += "\n"
    
    # Rights Investigator
    cur.execute('''
        SELECT r.role_name, r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Guarantor of Rights'
        AND r.role_name = 'Rights Investigator'
    ''')
    inv_role = cur.fetchone()
    if inv_role:
        md += f"**{inv_role['role_name']}**: {inv_role['role_desc']}\n\n"
    
    # Office of Facilitator of the Court
    md += "### Office of Facilitator of the Court\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Office of Facilitator of the Court'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    
    md += "#### Facilitator of the Court (Conductor)\n\n"
    cur.execute('''
        SELECT r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Facilitator of the Court'
        AND r.role_name = 'Facilitator of the Court'
    ''')
    role = cur.fetchone()
    if role:
        md += f"{role['role_desc']}\n\n"
    
    # Get duties
    cur.execute('''
        SELECT rd.duty_header, rd.duty_desc
        FROM scm_terran_society.role_duty rd
        JOIN scm_terran_society.role r ON rd.role_id = r.role_id
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Facilitator of the Court'
        AND r.role_name = 'Facilitator of the Court'
        ORDER BY rd.sort_order
    ''')
    
    md += "**Responsibilities:**\n\n"
    for duty in cur.fetchall():
        md += f"- **{duty['duty_header']}**: {duty['duty_desc']}\n"
    md += "\n"
    
    # Court Administrator
    cur.execute('''
        SELECT r.role_name, r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Facilitator of the Court'
        AND r.role_name = 'Court Administrator'
    ''')
    admin_role = cur.fetchone()
    if admin_role:
        md += f"**{admin_role['role_name']}**: {admin_role['role_desc']}\n\n"
    
    # Office of Public Arbitrator
    md += "### Office of Public Arbitrator\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Office of Public Arbitrator'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    
    md += "#### Public Arbitrator\n\n"
    cur.execute('''
        SELECT r.role_desc
        FROM scm_terran_society.role r
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Public Arbitrator'
        AND r.role_name = 'Public Arbitrator'
    ''')
    role = cur.fetchone()
    if role:
        md += f"{role['role_desc']}\n\n"
    
    # Get duties
    cur.execute('''
        SELECT rd.duty_header, rd.duty_desc
        FROM scm_terran_society.role_duty rd
        JOIN scm_terran_society.role r ON rd.role_id = r.role_id
        JOIN scm_terran_society.institution i ON r.institution_id = i.institution_id
        WHERE i.institution_name = 'Office of Public Arbitrator'
        AND r.role_name = 'Public Arbitrator'
        ORDER BY rd.sort_order
    ''')
    
    md += "**Responsibilities:**\n\n"
    for duty in cur.fetchall():
        md += f"- **{duty['duty_header']}**: {duty['duty_desc']}\n"
    md += "\n"
    
    md += "### Court Structure\n\n"
    md += "The Judicial Branch operates three types of courts:\n\n"
    md += "- **Minor Courts**: Handle petty criminal cases with 7-person juries (6-of-7 verdict required)\n"
    md += "- **Major Courts**: Handle serious criminal cases with 14-person juries (12-of-14 verdict required)\n"
    md += "- **Arbitration Courts**: Voluntary binding arbitration for civil disputes\n\n"
    md += "All courts require three Certified Fair Witnesses in attendance. Juries are selected from Citizens, and the Facilitator presides to ensure procedural fairness.\n\n"
    
    return md

def generate_world_level(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## World Level Governance\n\n"
    md += "The World tier coordinates matters that span Regions, including planetary defense, inter-Regional disputes, world-wide infrastructure, and relations with other civilizations. The World level mirrors the Regional structure with Executive, Legislative, Judicial, Fair Witness, and Military branches.\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # World Executive Branch
    md += "### World Executive Branch\n\n"
    md += "The World Executive administers planetary-scale services, infrastructure, and operations. It coordinates between Regions and manages relations with external parties.\n\n"
    
    md += "#### World Executive Council\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'World Executive Council'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "The World Executive Council consists of the First and Second World Executives who provide senior leadership and coordinate all World-level operations.\n\n"
    
    md += "**Key Responsibilities:**\n\n"
    md += "- Sign or veto bills approved by World Legislature\n"
    md += "- Appoint Senior Military Officer (pending Senate approval)\n"
    md += "- Primary civilian oversight of the Military\n"
    md += "- Coordinate world-wide infrastructure projects\n"
    md += "- Space exploration and off-planet civilian operations\n\n"
    
    # World Executive Offices
    world_exec_offices = [
        ('Office of World Administrator', 'Manages World operations, facilities, staffing, and coordinates between Regions'),
        ('Office of World Treasurer', 'Maintains World Treasury, administers world-wide payment systems and financial infrastructure'),
        ('Office of World Ambassador', 'Senior diplomatic role representing Terran Society to other civilizations, manages embassies and treaty negotiations'),
        ('Office of World Sheriff', 'Coordinates inter-Regional criminal investigations and shares best practices between Regional Sheriffs'),
        ('Office of World Environmental Guardian', 'Coordinates planetary environmental protection, monitors global pollution, manages resources spanning multiple Regions')
    ]
    
    for office_name, desc in world_exec_offices:
        md += f"#### {office_name}\n\n"
        cur.execute('''
            SELECT institution_desc
            FROM scm_terran_society.institution
            WHERE institution_name = %s
        ''', (office_name,))
        db_row = cur.fetchone()
        if db_row:
            md += f"{db_row['institution_desc']}\n\n"
        else:
            md += f"{desc}\n\n"
    
    # World Legislative Branch
    md += "### World Legislative Branch\n\n"
    md += "The World Legislature consists of two bodies: the Council of the Regions (similar to a Senate) representing Regional interests, and the World Council of the People providing direct representation.\n\n"
    
    md += "#### Council of the Regions\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Council of the Regions'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "Each Region sends representatives to the Council of the Regions, ensuring equal representation regardless of population. This body provides checks and balances on World legislation.\n\n"
    
    md += "**Authority:**\n\n"
    md += "- Approve Senior Military Officer appointment\n"
    md += "- Approve treaties before submission to Citizens for ratification\n"
    md += "- Provide oversight of World Executive operations\n\n"
    
    md += "#### World Council of the People\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'World Council of the People'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "Representatives elected to provide direct voice of the people at World level. Works with Council of the Regions on World legislation.\n\n"
    
    md += "**Legislative Authority:**\n\n"
    md += "- Military oversight and resource allocation\n"
    md += "- World-wide standards (weights, measures, timekeeping)\n"
    md += "- Laws of world commerce and infrastructure\n"
    md += "- Charter organizations operating on planetary scale or in space\n"
    md += "- Define structure and procedures of World institutions\n\n"
    
    # World Judicial
    md += "### World Judicial System\n\n"
    md += "The World Court operates differently from Regional courts. It handles disputes between Regions or between Terran Society and external parties. It is not a criminal court.\n\n"
    
    md += "**World Court Structure:**\n\n"
    md += "- **Conductor**: Elected by sitting Regional Facilitators, must have served at least one full term at Regional level\n"
    md += "- **Jury**: 21 jurors selected from Citizens who served at least one term in World Legislature\n"
    md += "- **Verdict**: Requires 19-of-21 majority vote\n"
    md += "- **Fair Witnesses**: Three Certified Fair Witnesses required in attendance\n"
    md += "- **Purpose**: Serious dispute resolution between Regions, or between Terran Society and outside parties (other civilizations, non-humans)\n\n"
    
    md += "The World Court's decisions are binding on the parties. Treaty disputes may be resolved here, but any resulting treaty still requires ratification by vote of all Citizens.\n\n"
    
    # World Fair Witness
    md += "### World Fair Witness Branch\n\n"
    md += "The World Fair Witness Council operates at planetary scale, setting standards and criteria for all Fair Witness training, testing, and certification.\n\n"
    
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'World Fair Witness Council'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    
    md += "See the Fair Witness Branch chapter for details on the World Fair Witness Council structure and authority.\n\n"
    
    # Military Branch
    md += "### Military Branch\n\n"
    md += "The Military Branch exists solely at the World level and operates under strict civilian oversight. It is responsible for planetary defense and intelligence gathering.\n\n"
    
    md += "#### World Defense Force\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'World Defense Force'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "Unified military organization responsible for planetary defense, coordinated under civilian authority.\n\n"
    
    md += "**Key Principles:**\n\n"
    md += "- **Civilian Oversight**: Senior Military Officer appointed by World Executive, approved by Senate\n"
    md += "- **Unified Structure**: Single organization with departmentalized functions\n"
    md += "- **Defensive Purpose**: Primary mission is planetary defense, not offensive operations\n"
    md += "- **Limited Authority**: Cannot act without civilian authorization\n"
    md += "- **Transparency**: Operations observed by Fair Witnesses where practical and appropriate\n\n"
    
    md += "#### Defense Force Intelligence\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Defense Force Intelligence'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "Intelligence gathering and analysis operations supporting planetary defense and threat assessment.\n\n"
    
    md += "#### Defense Force Council\n\n"
    cur.execute('''
        SELECT institution_desc
        FROM scm_terran_society.institution
        WHERE institution_name = 'Defense Force Council'
    ''')
    row = cur.fetchone()
    if row:
        md += f"{row['institution_desc']}\n\n"
    else:
        md += "Advisory body providing oversight and coordination of military operations under civilian authority.\n\n"
    
    md += "**Military Accountability:**\n\n"
    md += "- Resource allocation controlled by World Legislature\n"
    md += "- Operations subject to World Executive approval\n"
    md += "- Personnel bound by the Rights of the People\n"
    md += "- Subject to impeachment and removal for violations\n\n"
    
    return md

def generate_processes_chapter(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Processes and Procedures\n\n"
    md += "Terran Society operates through clearly defined processes that ensure transparency, fairness, and accountability. These processes govern elections, judicial proceedings, and Fair Witness certification.\n\n"
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Get all processes grouped by type
    cur.execute('''
        SELECT process_name, process_header, process_desc
        FROM scm_terran_society.process
        ORDER BY sort_order
    ''')
    
    current_category = None
    for row in cur.fetchall():
        # Determine category from process name
        if 'Election' in row['process_name']:
            category = 'Election Processes'
        elif 'Court' in row['process_name']:
            category = 'Judicial Processes'
        elif 'Fair Witness' in row['process_name']:
            category = 'Fair Witness Processes'
        else:
            category = 'Other Processes'
        
        # Add category header if new
        if category != current_category:
            md += f"### {category}\n\n"
            current_category = category
        
        md += f"#### {row['process_header']}\n\n"
        md += f"{row['process_desc']}\n\n"
    
    return md

def generate_glossary(conn):
    md = "<div style='page-break-before: always;'></div>\n\n## Glossary\n\n"
    
    glossary_terms = {
        'Arbitration': 'A method of dispute resolution where parties voluntarily agree to have an Arbitrator hear their case and make a binding decision.',
        'Arbitrator': 'An elected official who conducts arbitration hearings and issues binding rulings.',
        'Cooperative': 'An organization owned and controlled by its members or workers, operating for mutual benefit rather than profit.',
        'District': 'The smallest tier of Terran Society, typically 5,000 to 21,000 people, governed by a Council of Elders.',
        'Elder': 'An elected member of a District Council of Elders.',
        'Facilitator of the Court': 'An elected official (also called Conductor) who presides over Major and Minor Courts.',
        'Fair Witness': 'An independent, certified observer who records Society proceedings objectively.',
        'Jury': 'A group of citizens who decide the outcome of court cases.',
        'Public Service Cooperative': 'A chartered organization that provides public services like utilities, transit, or ports.',
        'Region': 'The primary governance tier, with complete executive, legislative, judicial, and Fair Witness branches. Maximum population 20-25 million.',
        'Representative': 'An elected member of the Regional Council of the People.',
        'World': 'The planetary tier coordinating matters that span regions.',
    }
    
    # Add roles from database
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT DISTINCT r.role_name, r.role_desc
        FROM scm_terran_society.role r
        ORDER BY r.role_name
    ''')
    
    for row in cur.fetchall():
        glossary_terms[row['role_name']] = row['role_desc']
    
    # Add institutions
    cur.execute('''
        SELECT DISTINCT institution_name, institution_desc
        FROM scm_terran_society.institution
        ORDER BY institution_name
    ''')
    
    for row in cur.fetchall():
        if row['institution_name'] not in glossary_terms:
            glossary_terms[row['institution_name']] = row['institution_desc']
    
    # Sort and output with anchor IDs
    for term in sorted(glossary_terms.keys()):
        # Create URL-safe anchor ID from term
        anchor_id = 'glossary-' + term.lower().replace(' ', '-').replace('/', '-').replace('(', '').replace(')', '')
        md += f"<span id=\"{anchor_id}\"></span>**{term}**: {glossary_terms[term]}\n\n"
    
    return md

def main():
    print("Generating Terran Society book manuscript...")
    
    conn = get_connection()
    
    try:
        # Load book metadata and authors
        metadata = load_book_metadata(conn)
        authors = load_authors(conn)
        
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            # Front matter
            f.write(generate_title_page(metadata))
            f.write(generate_author_page(metadata, authors))
            f.write(generate_dedication_page(metadata))
            f.write(generate_table_of_contents())
            
            # Title and introduction
            f.write(generate_introduction())
            
            # Basic Principles
            principles = load_principles()
            f.write(generate_principles(principles))
            
            # Rights of the People
            rights = load_rights()
            f.write(generate_rights(rights))
            
            # Organizational overview
            f.write(generate_org_overview(conn))
            
            # District level
            f.write(generate_district_level(conn))
            
            # Regional Executive Branch
            f.write(generate_regional_executive_chapter(conn))
            
            # Legislative Branch
            f.write(generate_legislative_chapter(conn))
            
            # Judicial Branch
            f.write(generate_judicial_chapter(conn))
            
            # Fair Witness Branch
            f.write(generate_fair_witness_chapter(conn))
            
            # World Level
            f.write(generate_world_level(conn))
            
            # Processes and Procedures
            f.write(generate_processes_chapter(conn))
            
            # TODO: Add Regional Executive level
            
            # Glossary
            f.write(generate_glossary(conn))
        
        print(f"✓ Manuscript generated: {OUTPUT_PATH}")
        print(f"  Size: {OUTPUT_PATH.stat().st_size} bytes")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    main()
