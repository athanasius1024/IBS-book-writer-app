"""Main Flask application for Terran Society Book Manager."""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from models import db, Tier, Branch, Institution, Role, RoleDuty, RoleExplain, InstitutionExplain, TierExplain, Process, MediaAsset, ContentBlock, EntityContent, BookMetadata, BookAuthor
import config
from datetime import datetime
import subprocess
import os

app = Flask(__name__)
app.config.from_object(config)
app.config['BASE_DIR'] = config.BASE_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
db.init_app(app)

# Register content management routes
from content_routes import register_content_routes
register_content_routes(app)

# Register book metadata routes
from book_routes import register_book_routes
register_book_routes(app)

# Register database settings routes
from db_settings_routes import register_db_settings_routes
register_db_settings_routes(app)

# Dashboard and navigation
@app.route('/')
def index():
    """Main dashboard."""
    # Get statistics
    stats = {
        'tiers': Tier.query.count(),
        'branches': Branch.query.count(),
        'institutions': Institution.query.count(),
        'roles': Role.query.count(),
        'duties': RoleDuty.query.count(),
        'processes': Process.query.count()
    }
    
    # Get recent modifications
    recent_roles = Role.query.order_by(Role.modified_at.desc()).limit(5).all()
    
    # Check if book exists and get stats
    book_file = config.BOOK_OUTPUT_DIR / 'manuscript.md'
    book_stats = None
    if book_file.exists():
        book_stats = {
            'size': book_file.stat().st_size,
            'modified': datetime.fromtimestamp(book_file.stat().st_mtime)
        }
    
    return render_template('index.html', stats=stats, recent_roles=recent_roles, book_stats=book_stats)

# Tier management
@app.route('/tiers')
def tiers_list():
    """List all tiers."""
    tiers = Tier.query.order_by(Tier.sort_order).all()
    return render_template('tiers/list.html', tiers=tiers)

@app.route('/tiers/<int:id>')
def tier_detail(id):
    """Show tier details."""
    tier = Tier.query.get_or_404(id)
    # Get content blocks for this tier
    from content_routes import get_entity_content
    entity_content = get_entity_content('tier', id)
    return render_template('tiers/detail.html', tier=tier, entity_content=entity_content)

# Branch management
@app.route('/branches')
def branches_list():
    """List all branches."""
    branches = Branch.query.order_by(Branch.sort_order).all()
    return render_template('branches/list.html', branches=branches)

@app.route('/branches/<int:id>')
def branch_detail(id):
    """Show branch details."""
    branch = Branch.query.get_or_404(id)
    # Get content blocks for this branch
    from content_routes import get_entity_content
    entity_content = get_entity_content('branch', id)
    return render_template('branches/detail.html', branch=branch, entity_content=entity_content)

# Institution management
@app.route('/institutions')
def institutions_list():
    """List all institutions."""
    tier_filter = request.args.get('tier')
    branch_filter = request.args.get('branch')
    
    query = Institution.query
    if tier_filter:
        query = query.filter_by(tier_id=tier_filter)
    if branch_filter:
        query = query.filter_by(branch_id=branch_filter)
    
    institutions = query.order_by(Institution.sort_order).all()
    tiers = Tier.query.order_by(Tier.sort_order).all()
    branches = Branch.query.order_by(Branch.sort_order).all()
    
    return render_template('institutions/list.html', institutions=institutions, tiers=tiers, branches=branches)

@app.route('/institutions/<int:id>')
def institution_detail(id):
    """Show institution details with roles."""
    institution = Institution.query.get_or_404(id)
    # Get content blocks for this institution
    from content_routes import get_entity_content
    entity_content = get_entity_content('institution', id)
    return render_template('institutions/detail.html', institution=institution, entity_content=entity_content)

@app.route('/institutions/new', methods=['GET', 'POST'])
def institution_new():
    """Create new institution."""
    if request.method == 'POST':
        institution = Institution(
            institution_name=request.form['institution_name'],
            institution_desc=request.form.get('institution_desc'),
            tier_id=request.form['tier_id'],
            branch_id=request.form.get('branch_id') or None,
            sort_order=request.form.get('sort_order', 0)
        )
        db.session.add(institution)
        db.session.commit()
        flash(f'Institution "{institution.institution_name}" created successfully!', 'success')
        return redirect(url_for('institution_detail', id=institution.institution_id))
    
    tiers = Tier.query.order_by(Tier.sort_order).all()
    branches = Branch.query.order_by(Branch.sort_order).all()
    return render_template('institutions/form.html', tiers=tiers, branches=branches)

@app.route('/institutions/<int:id>/edit', methods=['GET', 'POST'])
def institution_edit(id):
    """Edit institution."""
    institution = Institution.query.get_or_404(id)
    
    if request.method == 'POST':
        institution.institution_name = request.form['institution_name']
        institution.institution_desc = request.form.get('institution_desc')
        institution.tier_id = request.form['tier_id']
        institution.branch_id = request.form.get('branch_id') or None
        institution.sort_order = request.form.get('sort_order', 0)
        institution.modified_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Institution "{institution.institution_name}" updated successfully!', 'success')
        return redirect(url_for('institution_detail', id=institution.institution_id))
    
    tiers = Tier.query.order_by(Tier.sort_order).all()
    branches = Branch.query.order_by(Branch.sort_order).all()
    return render_template('institutions/form.html', institution=institution, tiers=tiers, branches=branches)

@app.route('/institutions/<int:id>/delete', methods=['POST'])
def institution_delete(id):
    """Delete institution."""
    institution = Institution.query.get_or_404(id)
    name = institution.institution_name
    db.session.delete(institution)
    db.session.commit()
    flash(f'Institution "{name}" deleted successfully!', 'success')
    return redirect(url_for('institutions_list'))

# Role management
@app.route('/roles')
def roles_list():
    """List all roles."""
    institution_filter = request.args.get('institution')
    
    query = Role.query.join(Institution)
    if institution_filter:
        query = query.filter(Institution.institution_id == institution_filter)
    
    roles = query.order_by(Institution.institution_name, Role.sort_order).all()
    institutions = Institution.query.order_by(Institution.institution_name).all()
    
    return render_template('roles/list.html', roles=roles, institutions=institutions)

@app.route('/roles/<int:id>')
def role_detail(id):
    """Show role details with duties and explanations."""
    role = Role.query.get_or_404(id)
    # Get content blocks for this role
    from content_routes import get_entity_content
    entity_content = get_entity_content('role', id)
    return render_template('roles/detail.html', role=role, entity_content=entity_content)

@app.route('/roles/new', methods=['GET', 'POST'])
def role_new():
    """Create new role."""
    if request.method == 'POST':
        role = Role(
            role_name=request.form['role_name'],
            role_desc=request.form.get('role_desc'),
            institution_id=request.form['institution_id'],
            sort_order=request.form.get('sort_order', 0)
        )
        db.session.add(role)
        db.session.commit()
        flash(f'Role "{role.role_name}" created successfully!', 'success')
        return redirect(url_for('role_detail', id=role.role_id))
    
    institutions = Institution.query.order_by(Institution.institution_name).all()
    return render_template('roles/form.html', institutions=institutions)

@app.route('/roles/<int:id>/edit', methods=['GET', 'POST'])
def role_edit(id):
    """Edit role."""
    role = Role.query.get_or_404(id)
    
    if request.method == 'POST':
        role.role_name = request.form['role_name']
        role.role_desc = request.form.get('role_desc')
        role.institution_id = request.form['institution_id']
        role.sort_order = request.form.get('sort_order', 0)
        role.modified_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Role "{role.role_name}" updated successfully!', 'success')
        return redirect(url_for('role_detail', id=role.role_id))
    
    institutions = Institution.query.order_by(Institution.institution_name).all()
    return render_template('roles/form.html', role=role, institutions=institutions)

@app.route('/roles/<int:id>/delete', methods=['POST'])
def role_delete(id):
    """Delete role."""
    role = Role.query.get_or_404(id)
    name = role.role_name
    db.session.delete(role)
    db.session.commit()
    flash(f'Role "{name}" deleted successfully!', 'success')
    return redirect(url_for('roles_list'))

# Duty management (HTMX inline editing)
@app.route('/duties/new', methods=['POST'])
def duty_new():
    """Create new duty (HTMX)."""
    duty = RoleDuty(
        role_id=request.form['role_id'],
        duty_header=request.form['duty_header'],
        duty_desc=request.form.get('duty_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(duty)
    db.session.commit()
    
    return render_template('duties/_duty_item.html', duty=duty)

@app.route('/duties/<int:id>/edit', methods=['PUT', 'POST'])
def duty_edit(id):
    """Edit duty (HTMX)."""
    duty = RoleDuty.query.get_or_404(id)
    duty.duty_header = request.form['duty_header']
    duty.duty_desc = request.form.get('duty_desc')
    duty.sort_order = request.form.get('sort_order', duty.sort_order)
    duty.modified_at = datetime.utcnow()
    
    db.session.commit()
    return render_template('duties/_duty_item.html', duty=duty)

@app.route('/duties/<int:id>/delete', methods=['DELETE'])
def duty_delete(id):
    """Delete duty (HTMX)."""
    duty = RoleDuty.query.get_or_404(id)
    db.session.delete(duty)
    db.session.commit()
    return '', 200

@app.route('/duties/restore', methods=['POST'])
def duty_restore():
    """Restore deleted duty (HTMX undo)."""
    duty = RoleDuty(
        role_id=request.form['role_id'],
        duty_header=request.form['duty_header'],
        duty_desc=request.form.get('duty_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(duty)
    db.session.commit()
    
    return render_template('duties/_duty_item.html', duty=duty)

# RoleExplain management (HTMX inline editing)
@app.route('/role-explains/new', methods=['POST'])
def role_explain_new():
    """Create new role explanation (HTMX)."""
    explain = RoleExplain(
        role_id=request.form['role_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_role_explain_item.html', explain=explain)

@app.route('/role-explains/<int:id>/edit', methods=['PUT'])
def role_explain_edit(id):
    """Edit role explanation (HTMX)."""
    explain = RoleExplain.query.get_or_404(id)
    explain.explain_header = request.form.get('explain_header')
    explain.explain_desc = request.form.get('explain_desc')
    explain.sort_order = request.form.get('sort_order', explain.sort_order)
    explain.modified_at = datetime.utcnow()
    
    db.session.commit()
    return render_template('explanations/_role_explain_item.html', explain=explain)

@app.route('/role-explains/<int:id>/delete', methods=['DELETE'])
def role_explain_delete(id):
    """Delete role explanation (HTMX)."""
    explain = RoleExplain.query.get_or_404(id)
    db.session.delete(explain)
    db.session.commit()
    return '', 200

@app.route('/role-explains/restore', methods=['POST'])
def role_explain_restore():
    """Restore deleted role explanation (HTMX undo)."""
    explain = RoleExplain(
        role_id=request.form['role_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_role_explain_item.html', explain=explain)

# InstitutionExplain management (HTMX inline editing)
@app.route('/institution-explains/new', methods=['POST'])
def institution_explain_new():
    """Create new institution explanation (HTMX)."""
    explain = InstitutionExplain(
        institution_id=request.form['institution_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_institution_explain_item.html', explain=explain)

@app.route('/institution-explains/<int:id>/edit', methods=['PUT'])
def institution_explain_edit(id):
    """Edit institution explanation (HTMX)."""
    explain = InstitutionExplain.query.get_or_404(id)
    explain.explain_header = request.form.get('explain_header')
    explain.explain_desc = request.form.get('explain_desc')
    explain.sort_order = request.form.get('sort_order', explain.sort_order)
    explain.modified_at = datetime.utcnow()
    
    db.session.commit()
    return render_template('explanations/_institution_explain_item.html', explain=explain)

@app.route('/institution-explains/<int:id>/delete', methods=['DELETE'])
def institution_explain_delete(id):
    """Delete institution explanation (HTMX)."""
    explain = InstitutionExplain.query.get_or_404(id)
    db.session.delete(explain)
    db.session.commit()
    return '', 200

@app.route('/institution-explains/restore', methods=['POST'])
def institution_explain_restore():
    """Restore deleted institution explanation (HTMX undo)."""
    explain = InstitutionExplain(
        institution_id=request.form['institution_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_institution_explain_item.html', explain=explain)

# TierExplain management (HTMX inline editing)
@app.route('/tier-explains/new', methods=['POST'])
def tier_explain_new():
    """Create new tier explanation (HTMX)."""
    explain = TierExplain(
        tier_id=request.form['tier_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_tier_explain_item.html', explain=explain)

@app.route('/tier-explains/<int:id>/edit', methods=['PUT'])
def tier_explain_edit(id):
    """Edit tier explanation (HTMX)."""
    explain = TierExplain.query.get_or_404(id)
    explain.explain_header = request.form.get('explain_header')
    explain.explain_desc = request.form.get('explain_desc')
    explain.sort_order = request.form.get('sort_order', explain.sort_order)
    explain.modified_at = datetime.utcnow()
    
    db.session.commit()
    return render_template('explanations/_tier_explain_item.html', explain=explain)

@app.route('/tier-explains/<int:id>/delete', methods=['DELETE'])
def tier_explain_delete(id):
    """Delete tier explanation (HTMX)."""
    explain = TierExplain.query.get_or_404(id)
    db.session.delete(explain)
    db.session.commit()
    return '', 200

@app.route('/tier-explains/restore', methods=['POST'])
def tier_explain_restore():
    """Restore deleted tier explanation (HTMX undo)."""
    explain = TierExplain(
        tier_id=request.form['tier_id'],
        explain_header=request.form.get('explain_header'),
        explain_desc=request.form.get('explain_desc'),
        sort_order=request.form.get('sort_order', 0)
    )
    db.session.add(explain)
    db.session.commit()
    
    return render_template('explanations/_tier_explain_item.html', explain=explain)

# Process management
@app.route('/processes')
def processes_list():
    """List all processes."""
    processes = Process.query.order_by(Process.sort_order).all()
    return render_template('processes/list.html', processes=processes)

@app.route('/processes/<int:id>')
def process_detail(id):
    """Show process details."""
    process = Process.query.get_or_404(id)
    # Get content blocks for this process
    from content_routes import get_entity_content
    entity_content = get_entity_content('process', id)
    return render_template('processes/detail.html', process=process, entity_content=entity_content)

@app.route('/processes/new', methods=['GET', 'POST'])
def process_new():
    """Create new process."""
    if request.method == 'POST':
        process = Process(
            process_name=request.form['process_name'],
            process_header=request.form.get('process_header'),
            process_desc=request.form.get('process_desc'),
            sort_order=request.form.get('sort_order', 0)
        )
        db.session.add(process)
        db.session.commit()
        flash(f'Process "{process.process_name}" created successfully!', 'success')
        return redirect(url_for('process_detail', id=process.process_id))
    
    return render_template('processes/form.html')

@app.route('/processes/<int:id>/edit', methods=['GET', 'POST'])
def process_edit(id):
    """Edit process."""
    process = Process.query.get_or_404(id)
    
    if request.method == 'POST':
        process.process_name = request.form['process_name']
        process.process_header = request.form.get('process_header')
        process.process_desc = request.form.get('process_desc')
        process.sort_order = request.form.get('sort_order', 0)
        process.modified_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Process "{process.process_name}" updated successfully!', 'success')
        return redirect(url_for('process_detail', id=process.process_id))
    
    return render_template('processes/form.html', process=process)

@app.route('/processes/<int:id>/delete', methods=['POST'])
def process_delete(id):
    """Delete process."""
    process = Process.query.get_or_404(id)
    name = process.process_name
    db.session.delete(process)
    db.session.commit()
    flash(f'Process "{name}" deleted successfully!', 'success')
    return redirect(url_for('processes_list'))

# Book generation
@app.route('/generate', methods=['POST'])
def generate_book():
    """Generate the book."""
    try:
        result = subprocess.run(
            ['python3', str(config.GENERATE_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(config.BASE_DIR)
        )
        
        if result.returncode == 0:
            flash('Book generated successfully!', 'success')
        else:
            flash(f'Error generating book: {result.stderr}', 'error')
    except Exception as e:
        flash(f'Error generating book: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate PDF directly from markdown using WeasyPrint."""
    try:
        pdf_script = config.BASE_DIR / 'scripts' / 'generate_pdf.py'
        
        if not pdf_script.exists():
            return jsonify({'success': False, 'error': 'PDF generation script not found.'}), 500
        
        result = subprocess.run(
            ['python3', str(pdf_script)],
            capture_output=True,
            text=True,
            cwd=str(config.BASE_DIR)
        )
        
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'PDF generated successfully!'}), 200
        else:
            error_msg = result.stderr or result.stdout
            return jsonify({'success': False, 'error': error_msg}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/view-pdf')
def view_pdf():
    """Serve the PDF file for viewing in browser."""
    pdf_path = config.BOOK_OUTPUT_DIR / 'TerranSocietyBook.pdf'
    if pdf_path.exists():
        return send_file(pdf_path, mimetype='application/pdf')
    else:
        flash('PDF file not found.', 'error')
        return redirect(url_for('index'))

@app.route('/view-html')
def view_html():
    """Serve the HTML version of the book for viewing in browser."""
    html_path = config.BOOK_OUTPUT_DIR / 'TerranSocietyBook.html'
    if html_path.exists():
        return send_file(html_path, mimetype='text/html')
    else:
        flash('HTML file not found. Generate the PDF first to create HTML.', 'error')
        return redirect(url_for('index'))

@app.route('/download-markdown')
def download_markdown():
    """Download the markdown manuscript."""
    md_path = config.BOOK_OUTPUT_DIR / 'manuscript.md'
    if md_path.exists():
        return send_file(
            md_path,
            mimetype='text/markdown',
            as_attachment=True,
            download_name='TerranSociety-manuscript.md'
        )
    else:
        flash('Markdown file not found. Generate the book first.', 'error')
        return redirect(url_for('index'))

@app.route('/download-pdf')
def download_pdf():
    """Download the PDF book."""
    pdf_path = config.BOOK_OUTPUT_DIR / 'TerranSocietyBook.pdf'
    if pdf_path.exists():
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='TerranSociety.pdf'
        )
    else:
        flash('PDF file not found. Generate the PDF first.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
