import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud import storage as gcs_storage
import google.auth

# Attempt to initialize Firebase with dynamic project detection and bucket creation
try:
    # 1. Get Project ID dynamically
    try:
        _, project_id = google.auth.default()
    except Exception:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    
    if not project_id:
        # Fallback for local development or if project ID cannot be determined
        project_id = "id-gallery-app" # Default placeholder

    # 2. Configure Bucket Name
    bucket_name = f"{project_id}-gallery-submissions"

    # 3. Initialize Firebase Admin
    if not firebase_admin._apps:
        try:
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })
        except Exception as e:
            # Fallback for local dev without ADC
            print(f"Notice: Initializing without Application Default Credentials. Error: {e}")
            firebase_admin.initialize_app()

    db = firestore.client()
    
    # 4. Handle Bucket Creation
    # We use the native GCS client for bucket management as it's more direct for creation
    storage_client = gcs_storage.Client()
    bucket = storage_client.bucket(bucket_name)
    
    if not bucket.exists():
        print(f"Creating storage bucket: {bucket_name}")
        bucket = storage_client.create_bucket(bucket_name, location="us") # Default to us location
        # Make bucket public for public gallery access (read-only)
        bucket.make_public(recursive=False, future=True)
    
    FIREBASE_ENABLED = True
except Exception as e:
    print(f"Warning: Firebase could not be fully initialized. Falling back to local/in-memory. Error: {e}")
    FIREBASE_ENABLED = False
    db = None
    bucket = None

def get_db():
    """Returns Firestore client or None if disabled."""
    if not FIREBASE_ENABLED:
        return None
    return db

def get_bucket():
    """Returns Storage bucket or None if disabled."""
    if not FIREBASE_ENABLED:
        return None
    # Ensure we return the firebase_admin bucket for easier blob operations if needed,
    # but the storage_client bucket created/found above is also valid.
    return storage.bucket(bucket_name)

def is_firebase_enabled():
    """Returns True if Firebase (Firestore & Storage) is configured."""
    return FIREBASE_ENABLED
