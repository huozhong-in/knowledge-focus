from pydantic import BaseModel
from fastapi import (
    APIRouter,
    # Depends,
    # Body,
)
from tools.co_reading import get_window_list, send_scroll_at_point


class ScrollRequest(BaseModel):
    x: int
    y: int
    dy: int


def get_router(external_get_session: callable) -> APIRouter:
    router = APIRouter()

    @router.get("/tools/windows")
    def list_windows():
        windows = get_window_list()
        return {"windows": windows}

    @router.post("/tools/scroll")
    def scroll_window(scroll_request: ScrollRequest):
        try:
            send_scroll_at_point(
                scroll_request.x, scroll_request.y, scroll_request.dy
            )
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
    
    
    return router
