import httpx
import jwt
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User

# Configuration
# In production, these should be loaded from environment variables
WIKIMEDIA_CLIENT_ID = os.getenv("WIKIMEDIA_CLIENT_ID", "9f0f090b0ef2fd6757f51900b52df19b")
WIKIMEDIA_CLIENT_SECRET = os.getenv("WIKIMEDIA_CLIENT_SECRET", "e8c9f202c985f7598a273ad483b277324f80c1b5")
REDIRECT_URI = os.getenv("OAUTH_CALLBACK_URL", "https://live.toolforge.org/oauth/callback")

# OAuth Endpoints
AUTHORIZE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/authorize"
TOKEN_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"
PROFILE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile"

# JWT Config
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
ALGORITHM = "HS256"

router = APIRouter()

@router.get("/login")
def login():
    """Redirects the user to the Wikimedia OAuth 2.0 authorization page."""
    url = f"{AUTHORIZE_URL}?client_id={WIKIMEDIA_CLIENT_ID}&response_type=code"
    # We do not strictly need redirect_uri in the authorize step if it's strictly registered, but good practice
    return RedirectResponse(url)

@router.get("/callback")
async def callback(code: str, response: Response, db: Session = Depends(get_db)):
    """Handles the OAuth callback, exchanges code for token, and creates a JWT session."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
        
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for access token
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": WIKIMEDIA_CLIENT_ID,
            "client_secret": WIKIMEDIA_CLIENT_SECRET
            # redirect_uri is optional if exactly one is registered, but we can include it
        }
        
        token_res = await client.post(TOKEN_URL, data=token_data)
        if token_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve access token")
            
        access_token = token_res.json().get("access_token")
        
        # 2. Get user profile
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_res = await client.get(PROFILE_URL, headers=headers)
        
        if profile_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to retrieve user profile")
            
        profile = profile_res.json()
        username = profile.get("username")
        
        if not username:
            raise HTTPException(status_code=400, detail="Username not found in profile")
            
    # 3. Create or update user in database
    user = db.query(User).filter(User.username == username).first()
    if not user:
        # Determine if this is the superadmin
        role = "superadmin" if username == "MdsShakil" else "user"
        user = User(username=username, role=role)
        db.add(user)
        db.commit()
    elif username == "MdsShakil" and user.role != "superadmin":
        user.role = "superadmin"
        db.commit()
        
    # 4. Create JWT and set cookie
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {"sub": username, "role": user.role, "exp": expire}
    token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    
    # We redirect to the dashboard after login
    response = RedirectResponse(url="/dashboard.html", status_code=302)
    response.set_cookie(key="session", value=token, httponly=True, max_age=7*24*60*60)
    
    return response

@router.post("/logout")
def logout():
    response = {"message": "Logged out"}
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session")
    return response

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")
            
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_superadmin(current_user: User = Depends(get_current_user)):
    if current_user.role != "superadmin":
        raise HTTPException(status_code=403, detail="Not authorized. Superadmin access required.")
    return current_user
