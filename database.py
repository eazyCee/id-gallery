import os
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud import storage as gcs_storage
import google.auth

# Attempt to initialize Firebase and GCS with Default Service Account
try:
    # 1. Get Project ID and Credentials dynamically
    # This will automatically pick up the Default Compute Service Account on Google Cloud
    auth_credentials, project_id = google.auth.default()
    
    if not project_id:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "id-gallery-app")

    # 2. Configure Bucket Name
    bucket_name = f"{project_id}-gallery-submissions"

    # 3. Initialize Firebase Admin with Application Default Credentials
    if not firebase_admin._apps:
        try:
            # Use the credentials discovered by google.auth.default() or standard ADC
            firebase_cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(firebase_cred, {
                'storageBucket': bucket_name
            })
        except Exception as e:
            print(f"Notice: Falling back to default firebase initialization. Error: {e}")
            firebase_admin.initialize_app()

    db = firestore.client()
    
    # 4. Initialize GCS Client with explicit project and credentials
    storage_client = gcs_storage.Client(project=project_id, credentials=auth_credentials)
    bucket = storage_client.bucket(bucket_name)
    
    if not bucket.exists():
        print(f"Creating storage bucket: {bucket_name}")
        bucket = storage_client.create_bucket(bucket_name, location="asia-southeast1") # Indonesian focus
        bucket.make_public(recursive=False, future=True)
    
    FIREBASE_ENABLED = True
except Exception as e:
    print(f"Warning: Firebase/GCS could not be fully initialized. Error: {e}")
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
