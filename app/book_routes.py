"""Book metadata and author management routes."""
from flask import render_template, request, redirect, url_for, flash
from models import db, BookMetadata, BookAuthor
from datetime import datetime, date

def register_book_routes(app):
    """Register book management routes with the Flask app."""
    
    @app.route('/book/metadata')
    def book_metadata():
        """View book metadata."""
        metadata = BookMetadata.query.first()
        if not metadata:
            # Create default metadata if doesn't exist
            metadata = BookMetadata(
                title='Terran Society: A New Social Contract',
                copyright_holder='Terran Society',
                copyright_year=datetime.now().year,
                current_version='0.1',
                version_date=date.today(),
                draft_watermark=True
            )
            db.session.add(metadata)
            db.session.commit()
        
        authors = BookAuthor.query.order_by(BookAuthor.sort_order).all()
        return render_template('book/metadata.html', metadata=metadata, authors=authors)
    
    @app.route('/book/metadata/edit', methods=['GET', 'POST'])
    def book_metadata_edit():
        """Edit book metadata."""
        metadata = BookMetadata.query.first()
        if not metadata:
            metadata = BookMetadata()
            db.session.add(metadata)
        
        if request.method == 'POST':
            metadata.title = request.form['title']
            metadata.subtitle = request.form.get('subtitle')
            metadata.copyright_holder = request.form['copyright_holder']
            metadata.copyright_year = request.form.get('copyright_year', type=int)
            metadata.dedication_text = request.form.get('dedication_text')
            metadata.dedication_attribution = request.form.get('dedication_attribution')
            metadata.current_version = request.form['current_version']
            
            # Parse version_date
            version_date_str = request.form.get('version_date')
            if version_date_str:
                try:
                    metadata.version_date = datetime.strptime(version_date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash('Invalid date format', 'error')
                    return redirect(url_for('book_metadata_edit'))
            
            metadata.draft_watermark = 'draft_watermark' in request.form
            metadata.header_odd_template = request.form.get('header_odd_template')
            metadata.header_even_template = request.form.get('header_even_template')
            metadata.footer_template = request.form.get('footer_template')
            metadata.modified_at = datetime.utcnow()
            
            db.session.commit()
            flash('Book metadata updated successfully!', 'success')
            return redirect(url_for('book_metadata'))
        
        return render_template('book/metadata_form.html', metadata=metadata)
    
    @app.route('/book/authors')
    def book_authors():
        """List all authors."""
        authors = BookAuthor.query.order_by(BookAuthor.sort_order).all()
        return render_template('book/authors.html', authors=authors)
    
    @app.route('/book/authors/new', methods=['GET', 'POST'])
    def book_author_new():
        """Add new author."""
        if request.method == 'POST':
            author = BookAuthor(
                author_name=request.form['author_name'],
                author_bio=request.form.get('author_bio'),
                author_role=request.form.get('author_role'),
                sort_order=request.form.get('sort_order', 0, type=int)
            )
            db.session.add(author)
            db.session.commit()
            flash(f'Author "{author.author_name}" added successfully!', 'success')
            return redirect(url_for('book_authors'))
        
        return render_template('book/author_form.html')
    
    @app.route('/book/authors/<int:id>/edit', methods=['GET', 'POST'])
    def book_author_edit(id):
        """Edit author."""
        author = BookAuthor.query.get_or_404(id)
        
        if request.method == 'POST':
            author.author_name = request.form['author_name']
            author.author_bio = request.form.get('author_bio')
            author.author_role = request.form.get('author_role')
            author.sort_order = request.form.get('sort_order', 0, type=int)
            author.modified_at = datetime.utcnow()
            
            db.session.commit()
            flash(f'Author "{author.author_name}" updated successfully!', 'success')
            return redirect(url_for('book_authors'))
        
        return render_template('book/author_form.html', author=author)
    
    @app.route('/book/authors/<int:id>/delete', methods=['POST'])
    def book_author_delete(id):
        """Delete author."""
        author = BookAuthor.query.get_or_404(id)
        name = author.author_name
        db.session.delete(author)
        db.session.commit()
        flash(f'Author "{name}" deleted successfully!', 'success')
        return redirect(url_for('book_authors'))
