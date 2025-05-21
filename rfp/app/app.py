import os
import secrets
import datetime
import json
import shutil
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for more verbose output
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("web_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
BASE_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PENDING_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'pending')
PROCESSING_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'processing')
COMPLETED_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'completed')
FAILED_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'failed')

ALLOWED_CSV_EXTENSIONS = {'csv'}
ALLOWED_DOC_EXTENSIONS = {'pdf', 'docx', 'doc'}
HARDCODED_PASSWORD = "fluxforce"  # In a real app, use hashed passwords in a database
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload size
MAX_DOCS_PER_RFP = 10  # Maximum number of additional documents per RFP

# Dedicated Google Sheet ID for web submissions
# You can override this with an environment variable if needed
WEB_GOOGLE_SHEET_ID = os.environ.get("WEB_GOOGLE_SHEET_ID", "1Ri42Zi1vz4WlRJEAJUx9tf3veZVpR6KgwrlHm9wqnXE")
logger.info(f"Using Google Sheet ID: {WEB_GOOGLE_SHEET_ID}")

# Available products (this should match the products available in your system)
AVAILABLE_PRODUCTS = [
    "Sales Cloud", 
    "Service Cloud", 
    "Marketing Cloud", 
    "Platform", 
    "Experience Cloud", 
    "Communications Cloud", 
    "Data Cloud",
    "Agentforce", 
    "MuleSoft"
]

# Ensure directories exist
for directory in [PENDING_FOLDER, PROCESSING_FOLDER, COMPLETED_FOLDER, FAILED_FOLDER]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Ensuring directory exists: {directory}")

# Configure app
app.config['UPLOAD_FOLDER'] = BASE_UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def get_job_metadata(job_id, status=None):
    """Get job metadata from its directory"""
    logger.debug(f"Looking for job metadata. job_id={job_id}, status={status}")
    
    if status:
        job_dir = os.path.join(BASE_UPLOAD_FOLDER, status, job_id)
        logger.debug(f"Checking specific directory: {job_dir}")
    else:
        # Search in all status directories
        logger.debug(f"Searching all status directories for job_id={job_id}")
        for status_dir in ['pending', 'processing', 'completed', 'failed']:
            potential_dir = os.path.join(BASE_UPLOAD_FOLDER, status_dir, job_id)
            logger.debug(f"Checking: {potential_dir}")
            if os.path.exists(potential_dir):
                job_dir = potential_dir
                status = status_dir
                logger.debug(f"Found job in {status} directory")
                break
        else:
            logger.debug(f"Job {job_id} not found in any status directory")
            return None
    
    metadata_file = os.path.join(job_dir, 'metadata.json')
    logger.debug(f"Looking for metadata file: {metadata_file}")
    
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                metadata['status'] = status
                logger.debug(f"Successfully loaded metadata for job {job_id}")
                return metadata
        except Exception as e:
            logger.error(f"Error loading job metadata for {job_id}: {e}")
            return None
    else:
        logger.debug(f"Metadata file not found: {metadata_file}")
    return None


def save_job_metadata(job_id, metadata, status):
    """Save job metadata to its directory"""
    job_dir = os.path.join(BASE_UPLOAD_FOLDER, status, job_id)
    metadata_file = os.path.join(job_dir, 'metadata.json')
    
    logger.debug(f"Saving metadata for job {job_id} to {metadata_file}")
    
    try:
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.debug(f"Successfully saved metadata for job {job_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving job metadata for {job_id}: {e}")
        return False


def get_all_jobs():
    """Get all jobs from all status directories"""
    jobs = []
    
    for status in ['pending', 'processing', 'completed', 'failed']:
        status_dir = os.path.join(BASE_UPLOAD_FOLDER, status)
        if os.path.exists(status_dir):
            for job_id in os.listdir(status_dir):
                job_path = os.path.join(status_dir, job_id)
                if os.path.isdir(job_path):
                    metadata = get_job_metadata(job_id, status)
                    if metadata:
                        metadata['id'] = job_id
                        jobs.append(metadata)
    
    # Sort jobs by timestamp (newest first)
    jobs.sort(key=lambda x: x.get('submitted_at', ''), reverse=True)
    return jobs


def get_queue_stats():
    """Get queue statistics"""
    stats = {
        'pending': 0,
        'processing': 0,
        'completed': 0,
        'failed': 0
    }
    
    for status in stats.keys():
        status_dir = os.path.join(BASE_UPLOAD_FOLDER, status)
        if os.path.exists(status_dir):
            stats[status] = len([name for name in os.listdir(status_dir) 
                              if os.path.isdir(os.path.join(status_dir, name))])
        else:
            stats[status] = 0
    
    return stats


def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


# Add datetime context processor to make 'now' available in all templates
@app.context_processor
def inject_now():
    return {'now': datetime.datetime.now()}


@app.route('/')
def home():
    # Redirect to login if not authenticated
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    return redirect(url_for('upload_form'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        
        if password == HARDCODED_PASSWORD:
            session['authenticated'] = True
            flash('Login successful', 'success')
            return redirect(url_for('upload_form'))
        else:
            flash('Invalid password', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


@app.route('/upload', methods=['GET', 'POST'])
def upload_form():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # Get form data
        email = request.form.get('email')
        language = request.form.get('language')
        
        # Get selected products
        selected_products = []
        for product in AVAILABLE_PRODUCTS:
            if request.form.get(f'product_{product.replace(" ", "_")}'):
                selected_products.append(product)
        
        # Check if CSV file was uploaded
        if 'rfp_file' not in request.files:
            flash('No RFP file provided', 'danger')
            return redirect(request.url)
        
        rfp_file = request.files['rfp_file']
        
        # If user does not select file, browser might submit an empty file
        if rfp_file.filename == '':
            flash('No RFP file selected', 'danger')
            return redirect(request.url)
        
        # Validate email
        if not email or '@' not in email:
            flash('Please provide a valid email address', 'danger')
            return redirect(request.url)
        
        # Create a job ID
        job_id = secrets.token_hex(8)
        logger.info(f"Creating new job with ID: {job_id}")
        
        # Create a directory for this job in the pending folder - FIXED PATH
        job_dir = os.path.join(PENDING_FOLDER, job_id)
        logger.info(f"Creating job directory at: {job_dir}")
        os.makedirs(job_dir, exist_ok=True)
        
        # Save CSV file if it's valid
        if rfp_file and allowed_file(rfp_file.filename, ALLOWED_CSV_EXTENSIONS):
            csv_filename = secure_filename(rfp_file.filename)
            rfp_file_path = os.path.join(job_dir, csv_filename)
            logger.info(f"Saving RFP file to: {rfp_file_path}")
            rfp_file.save(rfp_file_path)
        else:
            flash('Invalid RFP file. Please upload a CSV file.', 'danger')
            shutil.rmtree(job_dir)  # Clean up the job directory
            return redirect(request.url)
        
        # Save additional documents if provided
        doc_filenames = []
        if 'additional_docs' in request.files:
            additional_docs = request.files.getlist('additional_docs')
            
            # Check if too many files were uploaded
            if len(additional_docs) > MAX_DOCS_PER_RFP:
                flash(f'Too many additional documents. Maximum allowed is {MAX_DOCS_PER_RFP}.', 'danger')
                shutil.rmtree(job_dir)  # Clean up the job directory
                return redirect(request.url)
            
            for doc in additional_docs:
                if doc.filename != '' and allowed_file(doc.filename, ALLOWED_DOC_EXTENSIONS):
                    doc_filename = secure_filename(doc.filename)
                    doc_path = os.path.join(job_dir, doc_filename)
                    logger.info(f"Saving additional document to: {doc_path}")
                    doc.save(doc_path)
                    doc_filenames.append(doc_filename)
                elif doc.filename != '':
                    flash(f'Invalid document type: {doc.filename}. Please upload PDF or DOCX files only.', 'warning')
        
        # Create and save job metadata
        metadata = {
            'email': email,
            'language': language,
            'products': selected_products,
            'rfp_file': csv_filename,
            'additional_docs': doc_filenames,
            'submitted_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'started_at': None,
            'completed_at': None,
            'result_file': None
        }
        
        logger.info(f"Saving metadata: {metadata}")
        save_job_metadata(job_id, metadata, 'pending')
        
        logger.info(f"Job {job_id} submitted by {email} with {len(doc_filenames)} additional documents")
        
        # Redirect to status page
        flash(f'Your RFP has been submitted. Job ID: {job_id}', 'success')
        return redirect(url_for('job_status', job_id=job_id))
    
    # If GET request, show the upload form
    queue_stats = get_queue_stats()
    
    if queue_stats['pending'] > 0 or queue_stats['processing'] > 0:
        queue_status = f"Current queue: {queue_stats['pending']} waiting, {queue_stats['processing']} processing"
    else:
        queue_status = "No active jobs"
    
    return render_template(
        'upload.html', 
        products=AVAILABLE_PRODUCTS,
        queue_status=queue_status,
        max_docs=MAX_DOCS_PER_RFP
    )


@app.route('/status/<job_id>')
def job_status(job_id):
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # Get job metadata
    job = get_job_metadata(job_id)
    
    if not job:
        flash('Job not found', 'danger')
        return redirect(url_for('upload_form'))
    
    # Add job ID to the metadata
    job['id'] = job_id
    
    # Find position in queue if pending
    queue_position = None
    if job['status'] == 'pending':
        # List all pending jobs sorted by submission time
        pending_jobs = []
        pending_dir = os.path.join(BASE_UPLOAD_FOLDER, 'pending')
        for pending_id in os.listdir(pending_dir):
            pending_path = os.path.join(pending_dir, pending_id)
            if os.path.isdir(pending_path):
                metadata = get_job_metadata(pending_id, 'pending')
                if metadata:
                    metadata['id'] = pending_id
                    pending_jobs.append(metadata)
        
        # Sort by submission time
        pending_jobs.sort(key=lambda x: x.get('submitted_at', ''))
        
        # Find position
        for i, pending_job in enumerate(pending_jobs):
            if pending_job['id'] == job_id:
                queue_position = i + 1
                break
    
    # Check if results file exists
    result_file = None
    if job['status'] == 'completed' and job.get('result_file'):
        result_path = os.path.join(COMPLETED_FOLDER, job_id, job['result_file'])
        if os.path.exists(result_path):
            result_file = job['result_file']
    
    return render_template('status.html', job=job, queue_position=queue_position, result_file=result_file)


@app.route('/download/<job_id>')
def download_results(job_id):
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # Get job metadata
    job = get_job_metadata(job_id)
    
    if not job or job['status'] != 'completed' or not job.get('result_file'):
        flash('Results not available', 'danger')
        return redirect(url_for('upload_form'))
    
    result_path = os.path.join(COMPLETED_FOLDER, job_id, job['result_file'])
    if not os.path.exists(result_path):
        flash('Result file not found', 'danger')
        return redirect(url_for('job_status', job_id=job_id))
    
    return send_file(result_path, as_attachment=True, download_name=f"RFP_Results_{job_id}.csv")


@app.route('/queue')
def view_queue():
    if not session.get('authenticated'):
        return redirect(url_for('login'))
    
    # Get all jobs from all status directories
    jobs = get_all_jobs()
    
    return render_template('queue.html', jobs=jobs)


@app.errorhandler(413)
def too_large(e):
    flash(f'File too large. Maximum allowed size is {MAX_CONTENT_LENGTH // (1024 * 1024)}MB', 'danger')
    return redirect(url_for('upload_form'))


if __name__ == '__main__':
    logger.info("Starting Flask web server...")
    logger.info(f"Web server configured with Google Sheet ID: {WEB_GOOGLE_SHEET_ID}")
    logger.info(f"Job directories: pending={PENDING_FOLDER}, processing={PROCESSING_FOLDER}, completed={COMPLETED_FOLDER}, failed={FAILED_FOLDER}")
    app.run(debug=True, host='0.0.0.0', port=5000)