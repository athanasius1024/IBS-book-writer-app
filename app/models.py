"""SQLAlchemy models for IBS Book Writer."""
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from werkzeug.security import check_password_hash, generate_password_hash

from config import DB_SCHEMA

db = SQLAlchemy(metadata=MetaData(schema=DB_SCHEMA))


def fk(target):
    """Schema-aware foreign key target, e.g. fk('book.book_id')."""
    return f'{DB_SCHEMA}.{target}' if DB_SCHEMA else target


STATUS_DRAFT = 'draft'
STATUS_COMPLETED = 'completed'

# (panel key, human label) in the order they are displayed.
COVER_PANELS = [
    ('front', 'Front Cover'),
    ('spine', 'Spine (Binding)'),
    ('back', 'Back Cover'),
    ('inside_front', 'Inside Front Cover'),
    ('inside_back', 'Inside Back Cover'),
]
COVER_PANEL_KEYS = [key for key, _ in COVER_PANELS]


class User(UserMixin, db.Model):
    __tablename__ = 'app_user'

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    username_key = db.Column(db.String(50), nullable=False, unique=True)  # lower-cased
    password_hash = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    books = db.relationship('Book', back_populates='owner', cascade='all, delete-orphan',
                            order_by='Book.modified_at.desc()')

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Book(db.Model):
    __tablename__ = 'book'
    __table_args__ = (
        db.CheckConstraint("status IN ('draft', 'completed')", name='ck_book_status'),
    )

    book_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(fk('app_user.user_id'), ondelete='CASCADE'),
                        nullable=False, index=True)
    title = db.Column(db.Text, nullable=False)
    subtitle = db.Column(db.Text)
    author_name = db.Column(db.Text)
    copyright_holder = db.Column(db.Text)
    copyright_year = db.Column(db.Integer)
    version = db.Column(db.String(20), nullable=False, default='0.1')
    status = db.Column(db.String(20), nullable=False, default=STATUS_DRAFT)
    completed_at = db.Column(db.DateTime)
    derived_from_book_id = db.Column(db.Integer, db.ForeignKey(fk('book.book_id'), ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = db.relationship('User', back_populates='books')
    covers = db.relationship('BookCover', back_populates='book', cascade='all, delete-orphan')
    chapters = db.relationship('Chapter', back_populates='book', cascade='all, delete-orphan',
                               order_by='Chapter.sort_order, Chapter.chapter_id')
    derived_from = db.relationship('Book', remote_side=[book_id], foreign_keys=[derived_from_book_id])

    @property
    def is_completed(self):
        return self.status == STATUS_COMPLETED

    def touch(self):
        self.modified_at = datetime.utcnow()

    def cover(self, panel):
        for c in self.covers:
            if c.panel == panel:
                return c
        return None

    def init_covers(self):
        """Create the five cover panels (idempotent)."""
        existing = {c.panel for c in self.covers}
        for key in COVER_PANEL_KEYS:
            if key in existing:
                continue
            text = ''
            if key == 'front':
                text = '\n\n'.join(p for p in (f'# {self.title}', self.subtitle, self.author_name) if p)
            elif key == 'spine':
                text = ' - '.join(p for p in (self.title, self.author_name) if p)
            self.covers.append(BookCover(panel=key, content_text=text))

    def duplicate(self, new_title=None):
        """Deep-copy this book (covers, chapters, content blocks) into a new draft.

        Uploaded media files are shared by reference; nothing is committed here.
        """
        copy = Book(
            user_id=self.user_id,
            title=new_title or f'{self.title} (copy)',
            subtitle=self.subtitle,
            author_name=self.author_name,
            copyright_holder=self.copyright_holder,
            copyright_year=self.copyright_year,
            version=self.version,
            status=STATUS_DRAFT,
            derived_from_book_id=self.book_id,
        )
        for c in self.covers:
            copy.covers.append(BookCover(
                panel=c.panel, content_text=c.content_text, asset_id=c.asset_id,
                background_color=c.background_color, text_color=c.text_color))
        copy.init_covers()
        for ch in self.chapters:
            new_ch = Chapter(title=ch.title, sort_order=ch.sort_order)
            for blk in ch.blocks:
                new_ch.blocks.append(ContentBlock(content_text=blk.content_text, sort_order=blk.sort_order))
            copy.chapters.append(new_ch)
        return copy


class BookCover(db.Model):
    __tablename__ = 'book_cover'
    __table_args__ = (
        db.UniqueConstraint('book_id', 'panel', name='uq_book_cover_panel'),
        db.CheckConstraint(
            "panel IN ('front', 'spine', 'back', 'inside_front', 'inside_back')",
            name='ck_book_cover_panel'),
    )

    cover_id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey(fk('book.book_id'), ondelete='CASCADE'),
                        nullable=False, index=True)
    panel = db.Column(db.String(20), nullable=False)
    content_text = db.Column(db.Text, default='')
    asset_id = db.Column(db.Integer, db.ForeignKey(fk('media_asset.asset_id'), ondelete='SET NULL'))
    background_color = db.Column(db.String(7), nullable=False, default='#ffffff')
    text_color = db.Column(db.String(7), nullable=False, default='#000000')
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    book = db.relationship('Book', back_populates='covers')
    asset = db.relationship('MediaAsset')

    @property
    def label(self):
        return dict(COVER_PANELS).get(self.panel, self.panel)


class Chapter(db.Model):
    __tablename__ = 'chapter'

    chapter_id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey(fk('book.book_id'), ondelete='CASCADE'),
                        nullable=False, index=True)
    title = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    book = db.relationship('Book', back_populates='chapters')
    blocks = db.relationship('ContentBlock', back_populates='chapter', cascade='all, delete-orphan',
                             order_by='ContentBlock.sort_order, ContentBlock.block_id')


class ContentBlock(db.Model):
    """A markdown text block inside a chapter."""
    __tablename__ = 'content_block'

    block_id = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey(fk('chapter.chapter_id'), ondelete='CASCADE'),
                           nullable=False, index=True)
    content_text = db.Column(db.Text, nullable=False, default='')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapter = db.relationship('Chapter', back_populates='blocks')


class MediaAsset(db.Model):
    __tablename__ = 'media_asset'

    asset_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(fk('app_user.user_id'), ondelete='CASCADE'),
                        nullable=False, index=True)
    asset_name = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.Text, nullable=False)  # relative to UPLOAD_DIR
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
