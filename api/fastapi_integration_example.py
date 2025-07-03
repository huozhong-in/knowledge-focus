'''
我们解决了FastAPI调用ParsingMgr类时可能出现的警告问题：

模块级别的过滤器：保留了原有的warnings.filterwarnings()设置，这会在导入模块时生效。

全局初始化函数：添加了configure_parsing_warnings()函数，可以在任何应用启动时调用，确保警告被正确过滤。

类内部初始化：在ParsingMgr的初始化方法中添加了日志级别设置，确保每个实例都能正确过滤警告。

FastAPI集成示例：提供了一个示例文件fastapi_integration_example.py，展示如何在FastAPI应用中正确设置这些过滤器：

使用lifespan在应用启动时调用configure_parsing_warnings()
提供了两个API端点示例，演示如何处理任务和单个文件
同时展示了如何在直接运行文件时配置警告过滤
使用这种方法，无论是通过命令行运行parsing_mgr.py，还是通过FastAPI应用调用ParsingMgr类，都能确保来自pdfminer和markitdown的警告被正确过滤，不会出现在控制台或日志文件中。

在实际的FastAPI应用中，您只需要：

在应用启动时调用configure_parsing_warnings()
正常使用ParsingMgr类
这样就能确保警告得到有效过滤。
'''
from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, create_engine
from typing import Dict, Any, List
import logging
from contextlib import asynccontextmanager

# 导入解析管理器及其配置函数
from parsing_mgr import ParsingMgr, configure_parsing_warnings
from db_mgr import FileScreeningResult

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('api.log')
    ]
)

# 全局日志记录器
logger = logging.getLogger("api")

# 创建数据库连接
DB_FILE = "/Users/dio/Library/Application Support/knowledge-focus.huozhong.in/knowledge-focus.db"
engine = create_engine(f'sqlite:///{DB_FILE}')

def get_session():
    with Session(engine) as session:
        yield session

# 在应用启动时配置警告过滤
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 配置警告过滤器 - 这会在应用启动时执行
    configure_parsing_warnings()
    logger.info("Application startup: Parsing warnings configured")
    yield
    # 应用关闭时的清理工作
    logger.info("Application shutdown")

# 创建FastAPI应用
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Knowledge Focus API"}

@app.post("/parse_task/{task_id}")
async def parse_task(task_id: int, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """
    处理特定任务ID的所有文件
    """
    try:
        # 创建ParsingMgr实例 - 它已经在初始化时配置了日志级别
        parsing_mgr = ParsingMgr(session)
        
        # 处理任务
        result = parsing_mgr.process_files_for_task(task_id)
        return result
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing task: {str(e)}")

@app.post("/parse_file")
async def parse_file(file_path: str, session: Session = Depends(get_session)) -> Dict[str, Any]:
    """
    处理单个文件并生成标签
    """
    try:
        # 获取文件筛选结果
        from screening_mgr import ScreeningManager
        screening_mgr = ScreeningManager(session)
        result = screening_mgr.get_by_path(file_path)
        
        if not result:
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        
        # 创建ParsingMgr并处理文件
        parsing_mgr = ParsingMgr(session)
        success = parsing_mgr.parse_and_tag_file(result)
        session.commit()
        
        return {
            "success": success,
            "file_id": result.id,
            "file_path": file_path,
            "tags": result.tags_display_ids
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing file {file_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Error parsing file: {str(e)}")

# 如果直接运行此文件
if __name__ == "__main__":
    import uvicorn
    # 应用启动前配置警告过滤
    configure_parsing_warnings()
    uvicorn.run(app, host="0.0.0.0", port=8000)
