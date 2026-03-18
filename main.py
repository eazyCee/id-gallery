from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Response, Request, Depends, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import os
from typing import List
import uuid
from datetime import datetime, timezone

# In a real application, database imported from database.py would connect to Firestore.
# For local dev without credentials, we will use an in-memory fallback.
from database import get_db, get_bucket, is_firebase_enabled

app = FastAPI(title="ID Googlers Gallery API")

# Ensure static directory and local uploads directory exist
os.makedirs("static", exist_ok=True)
os.makedirs("local_uploads", exist_ok=True)

# Mount the static directory to serve HTML, CSS, JS
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="local_uploads"), name="local_uploads")

# Fallback in-memory database if Firebase is not configured
IN_MEMORY_DB = []

# Credentials from Environment Variables
ADMIN_USERNAME = os.getenv("GALLERY_USERNAME", "cultureclubadmin")
ADMIN_PASSWORD = os.getenv("GALLERY_PASSWORD", "cultureclubidcgkpcp1745")
AUTH_COOKIE_NAME = "admin_session"
AUTH_TOKEN = "secret_admin_token_123"

async def get_current_user(admin_session: str = Cookie(None)):
    if admin_session != AUTH_TOKEN:
        return None
    return ADMIN_USERNAME

def login_required(user: str = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Not authorized")
    return user

@app.get("/")
async def root():
    # Redirect to the gallery
    return Response(status_code=302, headers={"Location": "/gallery"})

@app.get("/gallery")
async def gallery_page():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/submissions")
async def submissions_page():
    with open("static/submit.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/login")
async def login_page():
    with open("static/login.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.get("/admin")
async def admin_page(user: str = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    with open("static/admin.html", "r") as f:
        return HTMLResponse(content=f.read())

# --- API ROUTES ---

@app.post("/api/submissions")
async def submit_photo(
    title: str = Form(...),
    photographerName: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...)
):
    # 1. Upload File
    file_id = str(uuid.uuid4())
    ext = file.filename.split(".")[-1]
    filename = f"{file_id}.{ext}"
    
    image_url = ""
    
    if is_firebase_enabled():
        try:
            bucket = get_bucket()
            blob = bucket.blob(f"submissions/{filename}")
            blob.upload_from_file(file.file, content_type=file.content_type)
            blob.make_public()
            image_url = blob.public_url
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to Cloud Storage: {e}")
    else:
        # Local Fallback
        file_path = f"local_uploads/{filename}"
        with open(file_path, "wb") as f:
            f.write(file.file.read())
        image_url = f"/uploads/{filename}"
        
    # 2. Save Database Record
    record = {
        "id": file_id,
        "title": title,
        "photographerName": photographerName,
        "description": description,
        "imageUrl": image_url,
        "status": "PENDING", # All new photos start as pending
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    
    if is_firebase_enabled():
        try:
            db = get_db()
            db.collection("photos").document(file_id).set(record)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save to Firestore: {e}")
    else:
        # Local Fallback
        IN_MEMORY_DB.append(record)
        
    return {"message": "Submission successful", "doc_id": file_id}


@app.get("/api/photos")
async def get_gallery_photos():
    """Returns only DISPLAYED or APPROVED photos for the public gallery (fallback to APPROVED if none DISPLAYED)"""
    photos = []
    
    if is_firebase_enabled():
        db = get_db()
        # Try fetching displayed first
        try:
            displayed_docs = list(db.collection("photos").where("status", "==", "DISPLAYED").stream())
            if displayed_docs:
                for doc in displayed_docs:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    photos.append(data)
            else:
                # Fallback to general approved photos if none are explicitly displayed
                docs = db.collection("photos").where("status", "==", "APPROVED").stream()
                for doc in docs:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    photos.append(data)
        except Exception as e:
            print(f"Error fetching from Firestore (Public Gallery): {e}")
            # Return empty list instead of crashing
            return {"photos": []}
    else:
        # Local Fallback
        displayed = [p for p in IN_MEMORY_DB if p.get("status") == "DISPLAYED"]
        if displayed:
            photos = displayed
        else:
            photos = [p for p in IN_MEMORY_DB if p.get("status") == "APPROVED"]
        
    return {"photos": photos}


@app.post("/api/admin/login")
async def admin_login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response.set_cookie(key=AUTH_COOKIE_NAME, value=AUTH_TOKEN, httponly=True)
        return {"message": "Login successful"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME)
    return {"message": "Logged out"}

@app.get("/api/admin/photos")
async def get_admin_photos(user: str = Depends(login_required)):
    """Returns ALL photos for the admin panel"""
    photos = []
    
    if is_firebase_enabled():
        db = get_db()
        try:
            docs = db.collection("photos").stream()
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                photos.append(data)
        except Exception as e:
            print(f"Error fetching from Firestore (Admin): {e}")
            return {"photos": []}
    else:
        # Local Fallback
        photos = list(IN_MEMORY_DB)
        
    return {"photos": photos}


@app.put("/api/admin/photos/{photo_id}")
async def update_photo_status(photo_id: str, status: str = Form(...), user: str = Depends(login_required)):
    """Approve or Reject a photo"""
    if status not in ["APPROVED", "REJECTED", "PENDING", "DISPLAYED"]:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    if is_firebase_enabled():
        try:
            db = get_db()
            doc_ref = db.collection("photos").document(photo_id)
            doc_ref.update({"status": status})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update Firestore: {e}")
    else:
        # Local Fallback
        found = False
        for p in IN_MEMORY_DB:
            if p["id"] == photo_id:
                p["status"] = status
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Photo not found")
            
    return {"message": f"Photo status updated to {status}"}

@app.put("/api/admin/display/{photo_id}")
async def set_current_display(photo_id: str, user: str = Depends(login_required)):
    """Toggles a photo's DISPLAYED status on or off."""
    if is_firebase_enabled():
        try:
            db = get_db()
            doc_ref = db.collection("photos").document(photo_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Photo not found")
                
            data = doc.to_dict()
            new_status = "APPROVED" if data.get("status") == "DISPLAYED" else "DISPLAYED"
            doc_ref.update({"status": new_status})
            
            return {"message": "Success", "new_status": new_status}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update display status: {e}")
    else:
        found = False
        # Toggle flag
        for p in IN_MEMORY_DB:
            if p["id"] == photo_id:
                new_status = "APPROVED" if p["status"] == "DISPLAYED" else "DISPLAYED"
                p["status"] = new_status
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Photo not found")
            
    return {"message": "Success", "new_status": new_status}
