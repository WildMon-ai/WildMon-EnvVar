# GIS Pipeline

A data science pipeline for processing and analyzing geospatial data using Google Earth Engine.

## Overview

This project provides tools and workflows for geospatial data analysis, including authentication services for Google Earth Engine and data processing pipelines implemented in Jupyter notebooks.

## Features

- **Google Earth Engine Integration**: Seamless authentication and initialization
- **Service Account Support**: Both user authentication and service account credentials
- **Pipeline Processing**: Jupyter notebook-based data processing workflows

## Prerequisites

- Python 3.11+
- Google Earth Engine account

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd ds-gis-pipeline
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```


## Usage

### Authentication

The project includes an `AuthenticationService` class that handles Google Earth Engine authentication:

```python
from src.auth import AuthenticationService

# Using default user authentication
success = AuthenticationService.authenticate(project_id="your-project-id")

# Using service account
success = AuthenticationService.authenticate(
    project_id="your-project-id",
    service_account="your-service-account@project.iam.gserviceaccount.com",
    key_file="path/to/service-account-key.json"
)
```

### Running the Pipeline

Execute the main pipeline using the provided Jupyter notebook:

```bash
jupyter notebook pipeline.ipynb
```

## Project Structure

```
ds-gis-pipeline/
├── README.md
├── pipeline.ipynb          # Main data processing pipeline
└── src/
    └── auth.py            # Google Earth Engine authentication service
```

## Configuration

- Default project ID: `wide-office-411000`
- Authentication methods supported:
  - User authentication (browser-based)
  - Service account authentication
