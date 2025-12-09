from fastapi import FastAPI, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from .utils.settings import settings
from .utils.models import UserQuery
from .orchestrator import Orchestrator
from dotenv import load_dotenv
load_dotenv(override=True)  # ensure latest .env is used
from .utils.images import resolve_images
from typing import List, Dict


app = FastAPI(default_response_class=ORJSONResponse)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or your frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


orch = Orchestrator()

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/chat")
async def chat(q: UserQuery):
    res = await orch.handle(q)
    return res.model_dump()

# KG-only cards (no live scrape)
@app.post("/best_cards")
async def best_cards(q: UserQuery):
    rows = await orch.best_with_images(q, stores=None, limit=6)
    return {"items": rows}

from loguru import logger
from fastapi.responses import JSONResponse
@app.post("/best_cards_live")
async def best_cards_live(q: UserQuery):
    try:
        items = await orch.best_cards_live(q, limit=6)
        # Always return a JSON object
        return {"results": items}
    except Exception as e:
        logger.exception(f"/best_cards_live failed: {e}")
        # Still return JSON so your curl|json.tool doesn't choke
        return JSONResponse({"results": [], "error": str(e)}, status_code=500)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .utils.models import UserQuery
from .orchestrator import Orchestrator

app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
orch = Orchestrator()

@app.post("/best_cards_live")
async def best_cards_live(q: UserQuery):
    rows = await orch.best_cards_live(q, limit=6)
    return {"results": rows}

# --- add near your other imports ---
from pydantic import BaseModel
from app.utils.images import resolve_images  # you already have this

# --- add this model ---
class ResolveImageReq(BaseModel):
    product_url: str

class ResolveImageResp(BaseModel):
    image_url: str | None = None

# --- add this route ---
# @app.post("/resolve_image", response_model=ResolveImageResp)
# async def resolve_image(req: ResolveImageReq):
#     """
#     Resolve a product page to an image_url (best-effort).
#     Uses your existing resolve_images([]) utility.
#     """
#     # resolve_images accepts a list of dicts where each has product_url
#     rows = await resolve_images([{"product_url": req.product_url}])
#     url = None
#     if rows and isinstance(rows, list):
#         url = rows[0].get("image_url")
#     return ResolveImageResp(image_url=url)

# @app.post("/resolve_images")
# async def resolve_images_api(items: List[Dict] = Body(..., example=[{"product_url": "https://..."}])):
#     """
#     Accepts: [{"product_url": "..."}]
#     Returns: same list with image_url injected when found.
#     """
#     out = await resolve_images(items)
#     return {"items": out}

from fastapi import Body, HTTPException
from fastapi.responses import StreamingResponse
import httpx, io

# ... keep your existing FastAPI app instance, CORS, etc.

# 1) Image resolver API (calls your existing utils.images.resolve_images)
from .utils.images import resolve_images as _resolve_images
from typing import Dict, List
from fastapi import Body

@app.post("/resolve_images")
async def resolve_images_api(payload: dict = Body(...)):
    """
    Accepts: {"items":[{"product_url":"https://..."}, ...]}
    Returns: {"items":[{"product_url":"...","image_url":"https://..."}, ...]}
    """
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = [items]
    try:
        resolved = await _resolve_images(items)
    except Exception as e:
        # never blow up frontend
        resolved = items
    return {"items": resolved}

# 2) Image proxy to avoid hotlink/CORS issues
@app.get("/img")
async def img_proxy(url: str):
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(
                url,
                headers={
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                    "referer": "",  # strip referer if the origin checks it
                },
            )
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail="Upstream error")
        return StreamingResponse(io.BytesIO(resp.content),
                                 media_type=resp.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Proxy failed: {e}")