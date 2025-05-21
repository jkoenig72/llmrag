import os
import sys
import time
import json
import logging
import datetime
import threading
import smtplib
import traceback
import subprocess
import shutil
import csv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Configure logging with more verbose output
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("job_processor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Add the parent directory to sys.path to import from the main codebase
parent_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.append(parent_dir)
logger.info(f"Parent directory path: {parent_dir}")
logger.info(f"Python sys.path: {sys.path}")

# Import directly from the parent directory config.py
try:
    # Import directly from parent directory using relative path
    sys.path.insert(0, parent_dir)
    from config import RFP_DOCUMENTS_DIR, GOOGLE_CREDENTIALS_FILE
    logger.info(f"Successfully imported config from parent directory")
    logger.info(f"RFP_DOCUMENTS_DIR = {RFP_DOCUMENTS_DIR}")
    logger.info(f"GOOGLE_CREDENTIALS_FILE = {GOOGLE_CREDENTIALS_FILE}")
except ImportError as e:
    logger.error(f"Failed to import from config.py: {e}")
    logger.error(f"Please ensure that config.py exists in the parent directory: {parent_dir}")
    sys.exit(1)

# Directory structure
BASE_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
PENDING_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'pending')
PROCESSING_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'processing')
COMPLETED_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'completed')
FAILED_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'failed')

# Dedicated Google Sheet ID for web submissions
# You can override this with an environment variable if needed
WEB_GOOGLE_SHEET_ID = os.environ.get("WEB_GOOGLE_SHEET_ID", "1Ri42Zi1vz4WlRJEAJUx9tf3veZVpR6KgwrlHm9wqnXE")
logger.info(f"Using Google Sheet ID: {WEB_GOOGLE_SHEET_ID}")

# Ensure directories exist
for directory in [PENDING_FOLDER, PROCESSING_FOLDER, COMPLETED_FOLDER, FAILED_FOLDER]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Ensuring directory exists: {directory}")

# Email configuration for Gmail
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': 'jkoenig72@gmail.com',
    'password': 'vwez hbgq xutu jhjj',  # Replace with your Gmail App Password
    'from_email': 'jkoenig72@gmail.com',
    'reply_to': 'jkoenig72@gmail.com'
}

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


def move_job_to_status(job_id, from_status, to_status):
    """Move a job from one status directory to another"""
    src_dir = os.path.join(BASE_UPLOAD_FOLDER, from_status, job_id)
    dst_dir = os.path.join(BASE_UPLOAD_FOLDER, to_status, job_id)
    
    logger.debug(f"Moving job {job_id} from {from_status} to {to_status}")
    logger.debug(f"Source: {src_dir}")
    logger.debug(f"Destination: {dst_dir}")
    
    if not os.path.exists(src_dir):
        logger.error(f"Source directory does not exist: {src_dir}")
        return False
    
    try:
        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
        
        # List files being moved (for debugging)
        files = os.listdir(src_dir)
        logger.debug(f"Files to be moved: {files}")
        
        # Move directory
        shutil.move(src_dir, dst_dir)
        logger.info(f"Moved job {job_id} from {from_status} to {to_status}")
        return True
    except Exception as e:
        logger.error(f"Error moving job {job_id} from {from_status} to {to_status}: {e}")
        return False


def update_job_status(job_id, from_status, to_status, additional_data=None):
    """Update job status and metadata"""
    try:
        # Get current metadata
        logger.debug(f"Updating job {job_id} status from {from_status} to {to_status}")
        metadata = get_job_metadata(job_id, from_status)
        if not metadata:
            logger.error(f"Failed to get metadata for job {job_id}")
            return False
        
        # Update status-specific timestamps
        if to_status == 'processing':
            metadata['started_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug(f"Updated started_at timestamp: {metadata['started_at']}")
        
        if to_status in ['completed', 'failed']:
            metadata['completed_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug(f"Updated completed_at timestamp: {metadata['completed_at']}")
        
        # Update additional data
        if additional_data:
            for key, value in additional_data.items():
                metadata[key] = value
                logger.debug(f"Updated metadata field: {key}={value}")
        
        # Move the job to the new status directory
        if not move_job_to_status(job_id, from_status, to_status):
            return False
        
        # Save updated metadata in the new location
        result = save_job_metadata(job_id, metadata, to_status)
        if result:
            logger.debug(f"Successfully updated job {job_id} status to {to_status}")
        return result
        
    except Exception as e:
        logger.error(f"Error updating job status: {e}")
        return False


def get_next_job():
    """Get the next job to process from the pending directory"""
    try:
        # Check if there are any jobs in the pending directory
        logger.debug("Looking for next job in pending directory")
        if not os.path.exists(PENDING_FOLDER):
            logger.debug(f"Pending folder not found: {PENDING_FOLDER}")
            return None
        
        # List all items in the pending directory
        items = os.listdir(PENDING_FOLDER)
        logger.debug(f"Items in pending directory: {items}")
        
        pending_jobs = []
        
        # Get all job directories in the pending folder
        for job_id in items:
            job_dir = os.path.join(PENDING_FOLDER, job_id)
            if os.path.isdir(job_dir):
                logger.debug(f"Found pending job directory: {job_dir}")
                metadata = get_job_metadata(job_id, 'pending')
                if metadata:
                    metadata['id'] = job_id
                    pending_jobs.append(metadata)
                    logger.debug(f"Added job {job_id} to pending jobs list")
                else:
                    logger.warning(f"No metadata found for job directory: {job_dir}")
        
        if not pending_jobs:
            logger.debug("No pending jobs found")
            return None
            
        # Sort by submission time (oldest first)
        pending_jobs.sort(key=lambda x: x.get('submitted_at', ''))
        
        # Log the order of jobs
        job_order = [f"{job['id']} ({job.get('submitted_at', 'unknown')})" for job in pending_jobs]
        logger.debug(f"Pending jobs in order: {job_order}")
        
        # Return the oldest job
        oldest_job = pending_jobs[0]
        logger.info(f"Selected job {oldest_job['id']} as next job (submitted at {oldest_job.get('submitted_at', 'unknown')})")
        return oldest_job
        
    except Exception as e:
        logger.error(f"Error getting next job: {e}")
        logger.error(traceback.format_exc())
        return None


def send_email_notification(job_id, status, result_file_path=None):
    """Send email notification about job status"""
    try:
        # Get job metadata
        logger.debug(f"Preparing email notification for job {job_id} with status {status}")
        job = get_job_metadata(job_id, status)
        if not job:
            logger.error(f"Failed to get metadata for job {job_id}")
            return False
            
        # Add job ID to the metadata
        job['id'] = job_id
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['from_email']
        msg['To'] = job['email']
        msg['Reply-To'] = EMAIL_CONFIG['reply_to']
        
        logger.debug(f"Creating email for {job['email']}")
        
        if status == 'completed':
            msg['Subject'] = f"RFP Processing Complete - Job {job_id}"
            body = f"""
            <html>
            <body>
                <h2>RFP Processing Complete</h2>
                <p>Your RFP has been successfully processed.</p>
                <p><strong>Job ID:</strong> {job_id}</p>
                <p><strong>Products:</strong> {', '.join(job['products'])}</p>
                <p><strong>Submitted:</strong> {job['submitted_at']}</p>
                <p><strong>Completed:</strong> {job['completed_at']}</p>
                <p>Please find the results attached to this email.</p>
                <p>Thank you for using our RFP Processor.</p>
            </body>
            </html>
            """
            
            # Attach results file
            if result_file_path and os.path.exists(result_file_path):
                logger.debug(f"Attaching result file: {result_file_path}")
                attachment = open(result_file_path, "rb")
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(result_file_path)}")
                msg.attach(part)
                logger.debug(f"File attached successfully")
                
        elif status == 'failed':
            msg['Subject'] = f"RFP Processing Failed - Job {job_id}"
            body = f"""
            <html>
            <body>
                <h2>RFP Processing Failed</h2>
                <p>We encountered an error while processing your RFP.</p>
                <p><strong>Job ID:</strong> {job_id}</p>
                <p><strong>Products:</strong> {', '.join(job['products'])}</p>
                <p><strong>Submitted:</strong> {job['submitted_at']}</p>
                <p>Please contact support for assistance.</p>
                {'<p><strong>Error:</strong> ' + job.get('error', 'Unknown error') + '</p>' if 'error' in job else ''}
            </body>
            </html>
            """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Send email via Gmail SMTP
        logger.info(f"Sending email notification to {job['email']} for job {job_id}")
        
        try:
            # Connect to Gmail SMTP
            server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
            server.ehlo()
            server.starttls()
            server.ehlo()
            
            # Login to Gmail
            server.login(EMAIL_CONFIG['username'], EMAIL_CONFIG['password'])
            
            # Send email
            text = msg.as_string()
            server.sendmail(EMAIL_CONFIG['from_email'], job['email'], text)
            server.quit()
            
            logger.info(f"Email successfully sent to {job['email']}")
            return True
        except Exception as e:
            logger.error(f"SMTP Error: {e}")
            # Still return True so job processing continues even if email fails
            return True
        
    except Exception as e:
        logger.error(f"Error preparing email notification: {e}")
        logger.error(traceback.format_exc())
        return False


def process_rfp(job):
    """Process the RFP using the main codebase"""
    job_id = job['id']
    
    try:
        logger.info(f"==================== PROCESSING JOB {job_id} ====================")
        logger.info(f"Job details: Language={job['language']}, Products={', '.join(job['products'])}")
        
        # Move job from pending to processing
        logger.info(f"Moving job from pending to processing status...")
        if not update_job_status(job_id, 'pending', 'processing'):
            logger.error(f"Failed to update job status for {job_id}")
            return False
        
        # Get updated job metadata and paths
        job = get_job_metadata(job_id, 'processing')
        job_dir = os.path.join(PROCESSING_FOLDER, job_id)
        rfp_file_path = os.path.join(job_dir, job['rfp_file'])
        
        logger.info(f"Job directory: {job_dir}")
        logger.info(f"RFP file: {rfp_file_path}")
        
        # List all files in job directory
        files_in_dir = os.listdir(job_dir)
        logger.info(f"Files in job directory: {files_in_dir}")
        
        # Import necessary modules from the main codebase
        logger.info(f"Importing modules from main codebase...")
        try:
            # We already imported RFP_DOCUMENTS_DIR at the top of the file
            from sheets_handler import GoogleSheetHandler
        except ImportError as e:
            error_msg = f"Failed to import required modules: {e}"
            logger.error(error_msg)
            logger.error("Python path: {}".format(sys.path))
            logger.error("Working directory: {}".format(os.getcwd()))
            update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
            send_email_notification(job_id, 'failed')
            return False
        
        # Create a job-specific folder in RFP_DOCUMENTS_DIR
        customer_dir = os.path.join(RFP_DOCUMENTS_DIR, f"job_{job_id}")
        os.makedirs(customer_dir, exist_ok=True)
        logger.info(f"Created customer context directory: {customer_dir}")
        
        
        # Copy additional documents for RAG context
        doc_count = 0
        logger.info(f"Copying additional documents to customer context directory...")
        logger.info(f"Additional documents in job: {job.get('additional_docs', [])}")
        
        for doc in job.get('additional_docs', []):
            src_path = os.path.join(job_dir, doc)
            dst_path = os.path.join(customer_dir, doc)
            logger.info(f"Copying {src_path} -> {dst_path}")
            
            if os.path.exists(src_path):
                shutil.copy2(src_path, dst_path)
                doc_count += 1
                logger.info(f"Successfully copied {doc}")
            else:
                logger.warning(f"Source file not found: {src_path}")
        
        logger.info(f"Copied {doc_count} additional documents for RAG context")
        
        # List files in customer directory
        files_in_customer_dir = os.listdir(customer_dir)
        logger.info(f"Files in customer context directory: {files_in_customer_dir}")
        
        # Initialize Google Sheet handler with the web-specific sheet ID
        logger.info(f"Initializing Google Sheet handler with sheet ID: {WEB_GOOGLE_SHEET_ID}")
        try:
            sheet_handler = GoogleSheetHandler(WEB_GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_FILE)
            sheet = sheet_handler.sheet
            
            # Clear the sheet
            sheet.clear()
            logger.info(f"Cleared Google Sheet {WEB_GOOGLE_SHEET_ID} for job {job_id}")
        except Exception as e:
            error_msg = f"Failed to initialize Google Sheet: {e}"
            logger.error(error_msg)
            update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
            send_email_notification(job_id, 'failed')
            return False
        
        # Load CSV and write to Google Sheet
        logger.info(f"Loading CSV file and writing to Google Sheet...")
        try:
            with open(rfp_file_path, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                rows = list(csv_reader)
            
            logger.info(f"CSV file loaded with {len(rows)} rows")
            
            # Write data to Google Sheet (preserving exact structure)
            if rows:
                logger.info(f"Writing {len(rows)} rows to Google Sheet...")
                sheet.update('A1', rows)
                logger.info(f"Successfully uploaded {len(rows)} rows to Google Sheet for job {job_id}")
            else:
                error_msg = "CSV file is empty"
                logger.error(error_msg)
                update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
                send_email_notification(job_id, 'failed')
                return False
        except Exception as e:
            error_msg = f"Failed to process CSV file: {e}"
            logger.error(error_msg)
            update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
            send_email_notification(job_id, 'failed')
            return False
        
        # Prepare command-line arguments for main.py
        main_script = os.path.join(parent_dir, "main.py")
        
        # Build command with all required parameters
        cmd = [
            "python", 
            main_script,
            "--web-mode",
            "--job-id", job_id,
            "--sheet-id", WEB_GOOGLE_SHEET_ID,
            "--language", job['language'],
            "--customer-folder", f"job_{job_id}"
        ]
        
        # Add products if specified
        if job['products']:
            cmd.extend(["--products", ",".join(job['products'])])
        
        # Run the process
        logger.info(f"Running main script: {' '.join(cmd)}")
        logger.info(f"Working directory: {parent_dir}")
        
        try:
            logger.info(f"Executing subprocess...")
            result = subprocess.run(
                cmd,
                cwd=parent_dir,
                text=True,
                capture_output=True
            )
            
            # Log the subprocess output
            logger.info(f"Subprocess STDOUT:\n{result.stdout}")
            
            if result.stderr:
                logger.warning(f"Subprocess STDERR:\n{result.stderr}")
            
            if result.returncode != 0:
                error_msg = f"Process exited with code {result.returncode}: {result.stderr}"
                logger.error(error_msg)
                update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
                send_email_notification(job_id, 'failed')
                return False
                
            logger.info(f"Main script completed successfully for job {job_id}")
        except Exception as e:
            error_msg = f"Error executing main script: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
            send_email_notification(job_id, 'failed')
            return False
        
        # Get the processed results
        try:
            logger.info(f"Retrieving results from Google Sheet...")
            all_values = sheet.get_all_values()
            
            if not all_values:
                error_msg = "No results found in Google Sheet after processing"
                logger.error(error_msg)
                update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
                send_email_notification(job_id, 'failed')
                return False
                
            logger.info(f"Retrieved {len(all_values)} rows of results from Google Sheet")
            
            # Create results file in the job directory
            result_filename = f"RFP_Results_{job_id}.csv"
            result_file_path = os.path.join(job_dir, result_filename)
            
            logger.info(f"Saving results to {result_file_path}")
            with open(result_file_path, 'w', newline='', encoding='utf-8') as f:
                csv_writer = csv.writer(f)
                csv_writer.writerows(all_values)
            
            logger.info(f"Successfully saved results to {result_file_path}")
            
            # Move job from processing to completed with updated metadata
            logger.info(f"Updating job status to completed...")
            update_job_status(job_id, 'processing', 'completed', {
                'result_file': result_filename
            })
            
            # Send email notification
            logger.info(f"Sending email notification...")
            send_email_notification(job_id, 'completed', result_file_path)
            
            logger.info(f"==================== JOB {job_id} COMPLETED SUCCESSFULLY ====================")
            return True
            
        except Exception as e:
            error_msg = f"Error handling results: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            update_job_status(job_id, 'processing', 'failed', {'error': error_msg})
            send_email_notification(job_id, 'failed')
            return False
            
    except Exception as e:
        error_msg = f"Unexpected error: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        try:
            # Try to update status to failed
            update_job_status(job_id, 'processing', 'failed', {'error': str(e)})
            send_email_notification(job_id, 'failed')
        except:
            logger.error(f"Could not update failed status for job {job_id}")
        return False
    finally:
        # Make sure we always clean up
        try:
            # Clean up customer directory in RFP_DOCUMENTS_DIR if processing failed
            job = get_job_metadata(job_id)
            if job and job.get('status') == 'failed':
                customer_dir = os.path.join(RFP_DOCUMENTS_DIR, f"job_{job_id}")
                if os.path.exists(customer_dir):
                    logger.info(f"Cleaning up customer directory for failed job: {customer_dir}")
                    shutil.rmtree(customer_dir)
                    logger.info(f"Cleaned up customer directory for failed job {job_id}")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
def process_queue():
    """Process jobs in the queue"""
    logger.info("Starting queue processor thread")
    
    while True:
        try:
            # Get the next job
            logger.debug("Checking for pending jobs...")
            job = get_next_job()
            
            if job:
                logger.info(f"Processing job {job['id']} (Language: {job['language']}, Products: {', '.join(job['products'])})")
                process_rfp(job)
            else:
                logger.debug("No jobs in queue, sleeping...")
                
            time.sleep(10)  # Sleep for 10 seconds before checking again
            
        except Exception as e:
            logger.error(f"Error in process_queue: {e}\n{traceback.format_exc()}")
            time.sleep(30)  # Sleep for 30 seconds on error


def cleanup_old_jobs(days=7):
    """Clean up old jobs from completed and failed directories"""
    try:
        logger.info(f"Cleaning up jobs older than {days} days")
        
        current_time = datetime.datetime.now()
        cleaned_count = 0
        
        # Check completed and failed directories
        for status_dir in [COMPLETED_FOLDER, FAILED_FOLDER]:
            if not os.path.exists(status_dir):
                logger.debug(f"Directory does not exist: {status_dir}")
                continue
                
            logger.debug(f"Checking directory: {status_dir}")
            for job_id in os.listdir(status_dir):
                job_dir = os.path.join(status_dir, job_id)
                if not os.path.isdir(job_dir):
                    logger.debug(f"Skipping non-directory: {job_dir}")
                    continue
                    
                # Get job metadata
                logger.debug(f"Checking job: {job_id}")
                metadata = get_job_metadata(job_id, os.path.basename(status_dir))
                if not metadata or 'completed_at' not in metadata:
                    logger.debug(f"Job {job_id} has no metadata or completion timestamp, skipping")
                    continue
                    
                # Calculate job age
                try:
                    completion_time = datetime.datetime.strptime(metadata['completed_at'], "%Y-%m-%d %H:%M:%S")
                    age_days = (current_time - completion_time).days
                    logger.debug(f"Job {job_id} age: {age_days} days (completed at {metadata['completed_at']})")
                    
                    if age_days > days:
                        logger.info(f"Cleaning up job {job_id} (age: {age_days} days)")
                        
                        # Clean up job directory
                        logger.debug(f"Removing job directory: {job_dir}")
                        shutil.rmtree(job_dir)
                        
                        # Clean up customer documents
                        customer_dir = os.path.join(RFP_DOCUMENTS_DIR, f"job_{job_id}")
                        logger.debug(f"Checking for customer directory: {customer_dir}")
                        if os.path.exists(customer_dir):
                            logger.debug(f"Removing customer directory: {customer_dir}")
                            shutil.rmtree(customer_dir)
                            logger.info(f"Removed customer directory for job {job_id}")
                                
                        cleaned_count += 1
                        logger.info(f"Successfully cleaned up job {job_id}")
                except Exception as e:
                    logger.error(f"Error processing job {job_id} for cleanup: {e}")
                    continue
        
        if cleaned_count > 0:
            logger.info(f"Removed {cleaned_count} old jobs")
        else:
            logger.info(f"No jobs older than {days} days found to clean up")
            
    except Exception as e:
        logger.error(f"Error in cleanup_old_jobs: {e}")
        logger.error(traceback.format_exc())


def main():
    """Main function to start the job processor"""
    logger.info("===============================================================")
    logger.info("                 STARTING RFP JOB PROCESSOR                    ")
    logger.info("===============================================================")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Parent directory: {parent_dir}")
    logger.info(f"Upload folders: {BASE_UPLOAD_FOLDER}")
    
    # Ensure all required directories exist
    for directory in [PENDING_FOLDER, PROCESSING_FOLDER, COMPLETED_FOLDER, FAILED_FOLDER]:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
    
    # Count jobs in each status
    job_counts = {}
    for status in ['pending', 'processing', 'completed', 'failed']:
        status_dir = os.path.join(BASE_UPLOAD_FOLDER, status)
        if os.path.exists(status_dir):
            job_counts[status] = len([name for name in os.listdir(status_dir) 
                                   if os.path.isdir(os.path.join(status_dir, name))])
        else:
            job_counts[status] = 0
    
    logger.info(f"Current job counts: pending={job_counts['pending']}, processing={job_counts['processing']}, completed={job_counts['completed']}, failed={job_counts['failed']}")
    
    # Log all jobs in pending
    if job_counts['pending'] > 0:
        logger.info("Pending jobs:")
        pending_dir = os.path.join(BASE_UPLOAD_FOLDER, 'pending')
        for job_id in os.listdir(pending_dir):
            job_path = os.path.join(pending_dir, job_id)
            if os.path.isdir(job_path):
                metadata = get_job_metadata(job_id, 'pending')
                if metadata:
                    logger.info(f"  - Job {job_id}: {metadata.get('language', 'unknown')}, Products: {metadata.get('products', [])}, Submitted: {metadata.get('submitted_at', 'unknown')}")
    
    # Move any processing jobs back to pending (in case of restart)
    if job_counts['processing'] > 0:
        logger.info("Found interrupted jobs in processing state, moving back to pending:")
        processing_dir = os.path.join(BASE_UPLOAD_FOLDER, 'processing')
        for job_id in os.listdir(processing_dir):
            job_path = os.path.join(processing_dir, job_id)
            if os.path.isdir(job_path):
                try:
                    # Get job metadata
                    metadata = get_job_metadata(job_id, 'processing')
                    if metadata:
                        # Move job back to pending
                        if move_job_to_status(job_id, 'processing', 'pending'):
                            logger.info(f"  - Moved interrupted job {job_id} back to pending")
                except Exception as e:
                    logger.error(f"Error moving interrupted job {job_id} back to pending: {e}")
    
    # Create and start the queue processor thread
    logger.info("Starting job queue processor thread...")
    queue_thread = threading.Thread(target=process_queue, daemon=True)
    queue_thread.start()
    
    # Create and start cleanup thread (runs once per day)
    logger.info("Starting cleanup thread (will run daily)...")
    def cleanup_thread_func():
        # Run cleanup immediately on startup
        cleanup_old_jobs(days=7)
        
        while True:
            # Sleep for 24 hours
            logger.debug("Cleanup thread sleeping for 24 hours...")
            time.sleep(86400)
            
            # Run cleanup again
            logger.info("Running scheduled cleanup...")
            cleanup_old_jobs(days=7)
            
    cleanup_thread = threading.Thread(target=cleanup_thread_func, daemon=True)
    cleanup_thread.start()
    
    try:
        # Keep the main thread alive
        logger.info("Job processor running. Press Ctrl+C to stop.")
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Job processor stopped by user")


if __name__ == "__main__":
    main()