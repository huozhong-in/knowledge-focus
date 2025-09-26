"""
图片处理API
处理图片缩略图生成和图片文件服务
"""

import io
import os
import json
from pathlib import Path
from PIL import Image
from sqlmodel import Session, select
from sqlalchemy import Engine
from db_mgr import ParentChunk
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
import logging

logger = logging.getLogger()

def get_router(get_engine: Engine, base_dir: str) -> APIRouter:
    router = APIRouter()

    @router.get("/images/{image_filename}")
    def get_image(image_filename: str, engine: Engine = Depends(get_engine)):
        """
        获取图片文件内容
        
        参数:
        - image_filename: 图片文件名 (例如: image_000000_hash.png)
        
        返回:
        - 图片文件的二进制内容
        """
        try:
            
            # 验证文件名格式（安全检查）
            if not image_filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                return {"success": False, "error": "不支持的图片格式"}
            
            if ".." in image_filename or "/" in image_filename or "\\" in image_filename:
                return {"success": False, "error": "无效的文件名"}
            
            # 获取docling缓存目录
            try:
                # 从数据库引擎获取基础目录
                docling_cache_dir = base_dir / "docling_cache"
                image_path = docling_cache_dir / image_filename
                
            except Exception as e:
                logger.error(f"获取docling缓存目录失败: {e}")
                return {"success": False, "error": "无法确定图片存储位置"}
            
            # 检查图片文件是否存在
            if not image_path.exists():
                logger.warning(f"图片文件不存在: {image_path}")
                return {"success": False, "error": f"图片文件不存在: {image_filename}"}
            
            # 验证这个图片是否属于某个已处理的文档（安全检查）        
            # 查找包含此图片文件名的ParentChunk（在metadata的image_file_path中查找）
            stmt = select(ParentChunk).where(
                ParentChunk.chunk_type == "image",
                ParentChunk.metadata_json.contains(image_filename)
            )
            with Session(engine) as session:
                chunk = session.exec(stmt).first()
                
                if not chunk:
                    logger.warning(f"图片文件未在数据库中找到关联记录: {image_filename}")
                    return {"success": False, "error": "图片文件无效或已过期"}
            
            # 根据文件扩展名确定正确的 MIME 类型
            file_ext = image_filename.lower().split('.')[-1]
            mime_type_map = {
                'png': 'image/png',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'gif': 'image/gif',
                'bmp': 'image/bmp',
                'webp': 'image/webp'
            }
            media_type = mime_type_map.get(file_ext, 'image/png')
            
            # 返回图片文件
            return FileResponse(
                path=str(image_path),
                media_type=media_type,
                headers={"Content-Disposition": "inline"}  # 让浏览器直接显示而不是下载
            )
            
        except Exception as e:
            logger.error(f"获取图片时发生错误: {e}", exc_info=True)
            return {"success": False, "error": f"获取图片失败: {str(e)}"}

    @router.get("/images/by-chunk/{parent_chunk_id}")
    def get_image_by_chunk(parent_chunk_id: int):
        """
        通过ParentChunk ID获取关联的图片
        
        参数:
        - parent_chunk_id: 父块ID
        
        返回:
        - 图片文件的二进制内容，或重定向到图片端点
        """
        try:
            # 查找指定的ParentChunk
            stmt = select(ParentChunk).where(
                ParentChunk.id == parent_chunk_id,
                ParentChunk.chunk_type == "image"
            )
            with Session(get_engine) as session:
                chunk = session.exec(stmt).first()
                
                if not chunk:
                    return {"success": False, "error": f"图片块不存在: {parent_chunk_id}"}
                
                # 从chunk中提取图片文件路径
                image_filename = None
                
                # 从metadata中获取image_file_path
                try:
                    metadata = json.loads(chunk.metadata_json)
                    image_file_path = metadata.get("image_file_path")
                    
                    if image_file_path and os.path.exists(image_file_path):
                        # metadata中有完整的文件路径
                        image_path = Path(image_file_path)
                        image_filename = image_path.name
                        logger.info(f"Found image file from metadata: {image_filename}")
                    else:
                        logger.warning(f"Image file path not found or file does not exist: {image_file_path}")
                                
                except Exception as e:
                    logger.warning(f"无法从metadata提取图片路径: {e}")
                
                if not image_filename:
                    return {"success": False, "error": "无法确定图片文件路径"}
                
                # 重定向到图片获取端点
                return RedirectResponse(url=f"/images/{image_filename}")
            
        except Exception as e:
            logger.error(f"通过chunk获取图片时发生错误: {e}", exc_info=True)
            return {"success": False, "error": f"获取图片失败: {str(e)}"}

    @router.get("/documents/{document_id}/images")
    def get_document_images(document_id: int):
        """
        获取文档中的所有图片列表
        
        参数:
        - document_id: 文档ID
        
        返回:
        - 图片列表，包含chunk_id、文件名、描述等信息
        """
        try:
            # 查找文档中所有的图片块
            stmt = select(ParentChunk).where(
                ParentChunk.document_id == document_id,
                ParentChunk.chunk_type == "image"
            )
            with Session(get_engine) as session:
                image_chunks = session.exec(stmt).all()
                
                images = []
                for chunk in image_chunks:
                    try:
                        # 提取图片文件名 - 从metadata中获取
                        image_filename = None
                        
                        # 从metadata中获取image_file_path
                        try:
                            metadata = json.loads(chunk.metadata_json)
                            image_file_path = metadata.get("image_file_path")
                            
                            if image_file_path and os.path.exists(image_file_path):
                                # metadata中有完整的文件路径
                                image_path = Path(image_file_path)
                                image_filename = image_path.name
                            else:
                                logger.warning(f"Image file path not found or file does not exist for chunk {chunk.id}: {image_file_path}")
                                        
                        except Exception as e:
                            logger.warning(f"处理图片块 {chunk.id} metadata时出错: {e}")
                        
                        # 如果无法确定文件名，跳过这个图片块
                        if not image_filename:
                            logger.warning(f"无法确定图片块 {chunk.id} 的文件名，跳过")
                            continue
                        
                        # 获取图片描述 - 现在直接从content字段获取
                        image_description = chunk.content if chunk.content else ""
                        
                        images.append({
                            "chunk_id": chunk.id,
                            "filename": image_filename,
                            "description": image_description,
                            "image_url": f"/images/{image_filename}",
                            "chunk_url": f"/images/by-chunk/{chunk.id}"
                        })
                        
                    except Exception as e:
                        logger.warning(f"处理图片块 {chunk.id} 时出错: {e}")
                        continue
                
                return {
                    "success": True,
                    "document_id": document_id,
                    "images": images,
                    "total_count": len(images)
                }
            
        except Exception as e:
            logger.error(f"获取文档图片列表时发生错误: {e}", exc_info=True)
            return {"success": False, "error": f"获取图片列表失败: {str(e)}"}


    @router.get("/image/thumbnail")
    async def get_thumbnail(
        file_path: str = Query(..., description="图片文件的完整路径"),
        width: int = Query(150, description="缩略图宽度"),
        height: int = Query(150, description="缩略图高度")
    ):
        """
        生成图片缩略图
        """
        try:
            # 验证文件路径安全性
            if not file_path or ".." in file_path:
                raise HTTPException(status_code=400, detail="Invalid file path")
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Image file not found")
            
            # 检查文件扩展名
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                raise HTTPException(status_code=400, detail="Unsupported image format")
            
            # 打开图片并生成缩略图
            with Image.open(file_path) as img:
                # 转换为RGB模式（处理RGBA等格式）
                if img.mode in ('RGBA', 'LA', 'P'):
                    # 创建白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 创建缩略图（保持宽高比）
                img.thumbnail((width, height), Image.Resampling.LANCZOS)
                
                # 保存到内存
                img_io = io.BytesIO()
                img.save(img_io, format='JPEG', quality=85, optimize=True)
                img_io.seek(0)
                
                # 安全处理文件名，避免中文字符编码问题
                try:
                    safe_filename = Path(file_path).stem.encode('ascii', 'ignore').decode('ascii')
                    if not safe_filename:
                        safe_filename = "thumbnail"
                except Exception:
                    safe_filename = "thumbnail"
                
                return StreamingResponse(
                    io.BytesIO(img_io.getvalue()),
                    media_type="image/jpeg",
                    headers={
                        "Cache-Control": "public, max-age=3600",  # 缓存1小时
                        # 避免在Content-Disposition中使用中文字符
                        "Content-Disposition": f"inline; filename=\"{safe_filename}_thumb.jpg\""
                    }
                )
        
        except Exception as e:
            logger.error(f"Error generating thumbnail for {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Error generating thumbnail")


    @router.get("/image/full")
    async def get_full_image(
        file_path: str = Query(..., description="图片文件的完整路径")
    ):
        """
        返回完整尺寸的图片文件
        """
        try:
            # 验证文件路径安全性
            if not file_path or ".." in file_path:
                raise HTTPException(status_code=400, detail="Invalid file path")
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Image file not found")
            
            # 检查文件扩展名
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                raise HTTPException(status_code=400, detail="Unsupported image format")
            
            # 确定MIME类型
            mime_types = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg', 
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.bmp': 'image/bmp',
                '.webp': 'image/webp'
            }
            mime_type = mime_types.get(file_ext, 'image/jpeg')
            
            # 读取文件并返回
            with open(file_path, 'rb') as f:
                image_data = f.read()
            
            # 安全处理文件名，避免中文字符编码问题
            try:
                safe_filename = Path(file_path).name.encode('ascii', 'ignore').decode('ascii')
                if not safe_filename:
                    safe_filename = f"image.{file_ext[1:]}"  # 使用扩展名作为默认名
            except Exception:
                safe_filename = f"image.{file_ext[1:]}"
            
            return StreamingResponse(
                io.BytesIO(image_data),
                media_type=mime_type,
                headers={
                    "Cache-Control": "public, max-age=3600",  # 缓存1小时
                    # 避免在Content-Disposition中使用中文字符
                    "Content-Disposition": f"inline; filename=\"{safe_filename}\""
                }
            )
        
        except Exception as e:
            logger.error(f"Error serving image {file_path}: {e}")
            raise HTTPException(status_code=500, detail="Error serving image")

    return router