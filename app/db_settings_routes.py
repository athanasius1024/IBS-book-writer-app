"""Database connection settings routes."""
from flask import render_template, request, redirect, url_for, flash, jsonify
import os
import json
from pathlib import Path

def register_db_settings_routes(app):
    """Register database settings routes with the Flask app."""
    
    @app.route('/settings/database', methods=['GET', 'POST'])
    def database_settings():
        """Database connection configuration page."""
        config_file = Path(app.config['BASE_DIR']) / 'config' / 'db_config.json'
        
        if request.method == 'POST':
            # Save database configuration
            db_config = {
                'host': request.form.get('host', 'localhost'),
                'port': int(request.form.get('port', 5432)),
                'database': request.form['database'],
                'user': request.form['user'],
                'password': request.form['password']
            }
            
            # Create config directory if it doesn't exist
            config_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to JSON file
            with open(config_file, 'w') as f:
                json.dump(db_config, f, indent=2)
            
            # Also set environment variables for immediate use
            os.environ['DB_HOST'] = db_config['host']
            os.environ['DB_PORT'] = str(db_config['port'])
            os.environ['DB_NAME'] = db_config['database']
            os.environ['DB_USER'] = db_config['user']
            os.environ['DB_PASSWORD'] = db_config['password']
            
            flash('Database configuration saved! Please restart the application for changes to take effect.', 'success')
            return redirect(url_for('database_settings'))
        
        # Load existing configuration
        db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'db_terran_society',
            'user': 'rock',
            'password': ''
        }
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                db_config = json.load(f)
        
        return render_template('settings/database.html', config=db_config)
    
    @app.route('/settings/database/test', methods=['POST'])
    def test_database_connection():
        """Test database connection with provided credentials."""
        import psycopg2
        
        try:
            host = request.json.get('host', 'localhost')
            port = int(request.json.get('port', 5432))
            database = request.json['database']
            user = request.json['user']
            password = request.json['password']
            
            # Try to connect
            conn = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                connect_timeout=5
            )
            
            # Test a simple query
            cur = conn.cursor()
            cur.execute('SELECT version();')
            version = cur.fetchone()[0]
            cur.close()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': 'Connection successful!',
                'version': version
            })
            
        except psycopg2.OperationalError as e:
            return jsonify({
                'success': False,
                'error': f'Connection failed: {str(e)}'
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Error: {str(e)}'
            }), 500
