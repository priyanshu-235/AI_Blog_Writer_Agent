from fastapi import APIRouter, HTTPException

from backend.db.repository import delete_blog, get_blog, list_blogs
from backend.services.cloudinary import destroy_cloudinary_image

router = APIRouter(tags=["blogs"])


@router.get("/api/blogs")
def list_saved_blogs():
    return {"blogs": list_blogs()}


@router.get("/api/blogs/{blog_id}")
def read_blog(blog_id: str):
    blog = get_blog(blog_id)

    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")

    return blog


@router.delete("/api/blogs/{blog_id}")
def remove_blog(blog_id: str):
    blog = delete_blog(blog_id)

    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found.")

    for diagram in blog.get("diagrams") or []:
        public_id = diagram.get("cloudinary_public_id")

        if not public_id:
            continue

        try:
            destroy_cloudinary_image(public_id)
        except Exception:
            pass

    return {"message": "Blog deleted successfully", "id": blog["id"]}
