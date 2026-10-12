"""SQLAlchemy models for Terran Society database."""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Tier(db.Model):
    __tablename__ = 'tier'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    tier_id = db.Column(db.Integer, primary_key=True)
    tier_name = db.Column(db.String(50), nullable=False, unique=True)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    institutions = db.relationship('Institution', back_populates='tier')
    tier_explains = db.relationship('TierExplain', back_populates='tier')

class Branch(db.Model):
    __tablename__ = 'branch'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    branch_id = db.Column(db.Integer, primary_key=True)
    branch_name = db.Column(db.String(50), nullable=False, unique=True)
    branch_header = db.Column(db.String(100))
    branch_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    institutions = db.relationship('Institution', back_populates='branch')

class Institution(db.Model):
    __tablename__ = 'institution'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    institution_id = db.Column(db.Integer, primary_key=True)
    institution_name = db.Column(db.String(100), nullable=False, unique=True)
    institution_header = db.Column(db.String(150))
    institution_desc = db.Column(db.Text)
    tier_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.tier.tier_id'), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.branch.branch_id'))
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tier = db.relationship('Tier', back_populates='institutions')
    branch = db.relationship('Branch', back_populates='institutions')
    roles = db.relationship('Role', back_populates='institution', cascade='all, delete-orphan')
    institution_explains = db.relationship('InstitutionExplain', back_populates='institution', cascade='all, delete-orphan')

class Role(db.Model):
    __tablename__ = 'role'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    role_id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(100), nullable=False)
    role_desc = db.Column(db.Text)
    institution_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.institution.institution_id'), nullable=False)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    institution = db.relationship('Institution', back_populates='roles')
    duties = db.relationship('RoleDuty', back_populates='role', cascade='all, delete-orphan')
    role_explains = db.relationship('RoleExplain', back_populates='role', cascade='all, delete-orphan')

class RoleDuty(db.Model):
    __tablename__ = 'role_duty'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    duty_id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.role.role_id'), nullable=False)
    duty_header = db.Column(db.String(100), nullable=False)
    duty_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    role = db.relationship('Role', back_populates='duties')

class RoleExplain(db.Model):
    __tablename__ = 'role_explain'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    explain_id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.role.role_id'), nullable=False)
    explain_header = db.Column(db.String(100))
    explain_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    role = db.relationship('Role', back_populates='role_explains')

class InstitutionExplain(db.Model):
    __tablename__ = 'institution_explain'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    explain_id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.institution.institution_id'), nullable=False)
    explain_header = db.Column(db.String(100))
    explain_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    institution = db.relationship('Institution', back_populates='institution_explains')

class TierExplain(db.Model):
    __tablename__ = 'tier_explain'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    explain_id = db.Column(db.Integer, primary_key=True)
    tier_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.tier.tier_id'), nullable=False)
    explain_header = db.Column(db.String(100))
    explain_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    tier = db.relationship('Tier', back_populates='tier_explains')

class Process(db.Model):
    __tablename__ = 'process'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    process_id = db.Column(db.Integer, primary_key=True)
    process_name = db.Column(db.String(100), nullable=False, unique=True)
    process_header = db.Column(db.String(150))
    process_desc = db.Column(db.Text)
    sort_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MediaAsset(db.Model):
    __tablename__ = 'media_asset'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    asset_id = db.Column(db.Integer, primary_key=True)
    asset_name = db.Column(db.Text, nullable=False)
    asset_type = db.Column(db.Text, nullable=False)  # image, icon, document, chart
    file_path = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.Text)
    alt_text = db.Column(db.Text)
    caption = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    content_blocks = db.relationship('ContentBlock', back_populates='asset')

class ContentBlock(db.Model):
    __tablename__ = 'content_block'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    block_id = db.Column(db.Integer, primary_key=True)
    block_type = db.Column(db.Text, nullable=False)  # text, table, chart, image, icon, heading, list
    content_text = db.Column(db.Text)  # Markdown text
    content_data = db.Column(db.JSON)  # For tables/charts
    asset_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.media_asset.asset_id'))
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    asset = db.relationship('MediaAsset', back_populates='content_blocks')
    entity_links = db.relationship('EntityContent', back_populates='content_block', cascade='all, delete-orphan')

class EntityContent(db.Model):
    __tablename__ = 'entity_content'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    entity_content_id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.Text, nullable=False)  # tier, branch, institution, role, duty, process
    entity_id = db.Column(db.Integer, nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('scm_terran_society.content_block.block_id'), nullable=False)
    section_name = db.Column(db.Text)  # e.g., "Overview", "Details", "Examples"
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    content_block = db.relationship('ContentBlock', back_populates='entity_links')

class BookMetadata(db.Model):
    __tablename__ = 'book_metadata'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    metadata_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False, default='Terran Society: A New Social Contract')
    subtitle = db.Column(db.Text)
    copyright_holder = db.Column(db.Text, default='Terran Society')
    copyright_year = db.Column(db.Integer)
    dedication_text = db.Column(db.Text)
    dedication_attribution = db.Column(db.Text)
    current_version = db.Column(db.Text, default='0.1')
    version_date = db.Column(db.Date)
    draft_watermark = db.Column(db.Boolean, default=True)
    header_odd_template = db.Column(db.Text, default='Terran Society: A New Social Contract    {chapter_title}')
    header_even_template = db.Column(db.Text, default='{section_title}    Terran Society')
    footer_template = db.Column(db.Text, default='{page_number}    Draft v{version} – {date}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BookAuthor(db.Model):
    __tablename__ = 'book_author'
    __table_args__ = {'schema': 'scm_terran_society'}
    
    author_id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.Text, nullable=False)
    author_bio = db.Column(db.Text)
    author_role = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
