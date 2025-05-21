# RFP Processor Web Application

A professional web interface for the RFP processing system that allows users to upload and process RFPs with automated language translation and product-specific knowledge retrieval.

## Features

- User authentication with simple password protection
- RFP file upload (CSV format)
- Additional document uploads (PDF, Word) for context
- Language selection for automatic translation (English/German)
- Product selection for targeted knowledge retrieval
- Job queue for managing processing on limited GPU resources
- Email notification when processing is complete
- Real-time job status tracking
- Professional interface design (distinct from the console version)

## Directory Structure

```
rfp/                       # Main RFP project
├── app/                   # Web application directory
│   ├── app.py             # Main Flask application
│   ├── job_processor.py   # Background job processing script
│   ├── main_parser.py     # Command line argument parser
│   ├── requirements.txt   # Python dependencies
│   ├── README.md          # Web app documentation
│   ├── uploads/           # Uploaded files storage
│   ├── results/           # Processed results
│   └── templates/         # HTML templates
│       ├── base.html      # Base template with common layout
│       ├── login.html     # Login page
│       ├── upload.html    # RFP upload form
│       ├── status.html    # Job status page
│       └── queue.html     # Queue overview page
├── config.py              # Main RFP configuration
├── main.py                # Main RFP processing script
└── ...                    # Other RFP system files
```

## Installation

1. Create the app directory in your RFP project:

```bash
cd ~/llms-env/llmrag/rfp
mkdir -p app/templates app/uploads app/results
```

2. Install the Flask dependencies:

```bash
cd app
pip install flask==2.3.2 werkzeug==2.3.6 gunicorn==21.2.0
```

## Configuration

Before running the application, you may want to configure the following:

1. **Web-specific Google Sheet**: By default, the web app uses the same Google Sheet ID as your main RFP system. You can change this by setting the `WEB_GOOGLE_SHEET_ID` environment variable:

```bash
export WEB_GOOGLE_SHEET_ID="your-specific-web-sheet-id"
```

2. **Email Settings**: For email notifications to work, update the EMAIL_CONFIG in job_processor.py with your SMTP server details.

3. **Password**: The default password is "fluxforce". You can change this in app.py by updating the HARDCODED_PASSWORD variable.

## Usage

1. Start the Flask web server:

```bash
cd ~/llms-env/llmrag/rfp/app
python app.py
```

This starts the web server on http://localhost:5000

2. In a separate terminal, start the job processor:

```bash
cd ~/llms-env/llmrag/rfp/app
python job_processor.py
```

3. Access the web application in your browser at http://localhost:5000

4. Log in with the password "fluxforce"

## Notes

- The web interface is designed to be professional in appearance while the console version maintains its original theme
- Both interfaces share the same underlying processing code and functionality
- Each RFP submission gets a unique ID for tracking and reference