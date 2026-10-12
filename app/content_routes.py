"""Content management routes for Terran Society Book Manager."""
from flask import render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from models import db, ContentBlock, MediaAsset, EntityContent
import os
from datetime import datetime
import config

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'pdf', 'doc', 'docx'}
UPLOAD_FOLDER = 'static/uploads'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_entity_content(entity_type, entity_id):
    """Get all content blocks for an entity."""
    links = EntityContent.query.filter_by(
        entity_type=entity_type,
        entity_id=entity_id
    ).order_by(EntityContent.section_name, EntityContent.sort_order).all()
    
    return [link.content_block for link in links]

# Content block management (HTMX)
def content_new(app):
    @app.route('/content/new', methods=['POST'])
    def content_block_new():
        """Create new content block (HTMX)."""
        block = ContentBlock(
            block_type=request.form['block_type'],
            content_text=request.form.get('content_text'),
            sort_order=request.form.get('sort_order', 0)
        )
        db.session.add(block)
        db.session.flush()  # Get the ID
        
        # Link to entity
        entity_link = EntityContent(
            entity_type=request.form['entity_type'],
            entity_id=request.form['entity_id'],
            block_id=block.block_id,
            section_name=request.form.get('section_name'),
            sort_order=request.form.get('sort_order', 0)
        )
        db.session.add(entity_link)
        db.session.commit()
        
        return render_template('content/_content_block.html', block=block, entity_link=entity_link)

    @app.route('/content/<int:id>/edit', methods=['POST'])
    def content_block_edit(id):
        """Edit content block (HTMX)."""
        block = ContentBlock.query.get_or_404(id)
        block.content_text = request.form['content_text']
        block.modified_at = datetime.utcnow()
        db.session.commit()
        
        entity_link = EntityContent.query.filter_by(block_id=id).first()
        return render_template('content/_content_block.html', block=block, entity_link=entity_link)

    @app.route('/content/<int:id>/delete', methods=['DELETE'])
    def content_block_delete(id):
        """Delete content block (HTMX)."""
        block = ContentBlock.query.get_or_404(id)
        db.session.delete(block)
        db.session.commit()
        return '', 200

    @app.route('/content/<int:id>/reorder', methods=['POST'])
    def content_block_reorder(id):
        """Reorder content block (HTMX)."""
        block_link = EntityContent.query.get_or_404(id)
        new_order = request.form.get('sort_order', type=int)
        block_link.sort_order = new_order
        db.session.commit()
        return jsonify({'success': True})

# Media upload
def media_upload(app):
    @app.route('/media/upload', methods=['POST'])
    def media_upload_file():
        """Upload media file."""
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            asset_type = request.form.get('asset_type', 'image')
            
            # Create type-specific subdirectory
            upload_path = os.path.join(UPLOAD_FOLDER, f'{asset_type}s')
            os.makedirs(upload_path, exist_ok=True)
            
            # Add timestamp to filename to avoid conflicts
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(upload_path, filename)
            
            file.save(filepath)
            
            # Create media asset record
            asset = MediaAsset(
                asset_name=request.form.get('asset_name', filename),
                asset_type=asset_type,
                file_path=filepath,
                file_size=os.path.getsize(filepath),
                mime_type=file.content_type,
                alt_text=request.form.get('alt_text'),
                caption=request.form.get('caption')
            )
            db.session.add(asset)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'asset_id': asset.asset_id,
                'file_path': filepath,
                'asset_name': asset.asset_name
            })
        
        return jsonify({'error': 'Invalid file type'}), 400

    @app.route('/media/<int:id>/delete', methods=['DELETE'])
    def media_delete(id):
        """Delete media asset."""
        asset = MediaAsset.query.get_or_404(id)
        
        # Delete file
        if os.path.exists(asset.file_path):
            os.remove(asset.file_path)
        
        db.session.delete(asset)
        db.session.commit()
        return jsonify({'success': True})

    @app.route('/media/list')
    def media_list():
        """List all media assets."""
        asset_type = request.args.get('type')
        query = MediaAsset.query
        if asset_type:
            query = query.filter_by(asset_type=asset_type)
        assets = query.order_by(MediaAsset.created_at.desc()).all()
        return render_template('content/media_library.html', assets=assets)

def register_content_routes(app):
    """Register all content management routes."""
    content_new(app)
    media_upload(app)
