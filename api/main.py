from fastapi import FastAPI, Body, Depends
from typing import List
import uvicorn
import argparse
import os
import time
from utils import kill_process_on_port
import pathlib
import logging
from sqlmodel import Field, SQLModel, create_engine, Session, select

# 设置日志记录
logger = logging.getLogger()
parents_logs_dir = pathlib.Path(__file__).parent / 'logs'
os.mkdir(parents_logs_dir) if not parents_logs_dir.exists() else None
logger.setLevel(logging.INFO)
handler = logging.FileHandler(parents_logs_dir / 'api_{starttime}.log'.format(starttime=time.strftime('%Y%m%d', time.localtime(time.time()))))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# 表结构设计
class Settings(SQLModel, table=True):
    __tablename__ = "t_settings"
    id: int = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: str
    description: str


app = FastAPI()

# 存储数据库引擎作为应用的属性
app.state.engine = None

# 数据库连接管理
def get_engine():
    """获取数据库引擎"""
    if app.state.engine is None:
        # 确保数据库引擎已初始化
        raise RuntimeError("数据库引擎未初始化")
    return app.state.engine

def get_session():
    """FastAPI依赖函数，用于获取数据库会话"""
    engine = get_engine()
    with Session(engine) as session:
        yield session

# 示例：使用数据库连接的API端点
@app.get("/db-test")
def test_db_connection(session: Session = Depends(get_session)):
    try:
        # 使用SQLModel操作t_settings表
        # 检查是否存在测试数据
        statement = select(Settings).where(Settings.name == "test_setting")
        test_setting = session.exec(statement).first()
        
        if not test_setting:
            # 不存在则创建测试数据
            test_setting = Settings(
                name="test_setting", 
                value="测试数据",
                description="这是一个用于测试数据库连接的设置项"
            )
            session.add(test_setting)
            session.commit()
            session.refresh(test_setting)
        
        # 读取最近的5条设置数据
        statement = select(Settings).order_by(Settings.id.desc()).limit(5)
        recent_settings = session.exec(statement).all()
        
        # 使用model_dump()方法转换为可序列化的字典列表
        settings_data = [s.model_dump() for s in recent_settings]
        
        return {
            "status": "success",
            "message": "数据库连接正常",
            "data": settings_data
        }
    except Exception as e:
        logger.error(f"数据库操作失败: {str(e)}")
        return {
            "status": "error",
            "message": f"数据库操作失败: {str(e)}"
        }

@app.get("/")
def read_root():
    # 现在可以在任何路由中使用 app.state.db_path
    return {"Hello": "World", "db_path": app.state.db_path}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}

# 读取给定绝对路径的文件内容
@app.post("/file-content")
def read_file_content(file_paths: List[str] = Body(...)):
    results = []
    for file_path in file_paths:
        try:
            if not os.path.exists(file_path):
                results.append({
                    "path": file_path,
                    "success": False,
                    "error": "文件不存在",
                    "content": None
                })
                continue
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                results.append({
                    "path": file_path,
                    "success": True,
                    "error": None,
                    "content": content
                })
        except Exception as e:
            results.append({
                "path": file_path,
                "success": False,
                "error": str(e),
                "content": None
            })
    
    return {"results": results}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=60000, help="API服务监听端口")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="API服务监听地址")
    parser.add_argument("--db-path", type=str, default="knowledge-focus.db", help="数据库文件路径")
    
    args = parser.parse_args()
    
    # 检查端口是否被占用，如果被占用则终止占用进程
    kill_process_on_port(args.port)
    time.sleep(2)  # 等待端口释放
    
    # 设置数据库路径
    app.state.db_path = args.db_path
    
    # 初始化数据库引擎
    sqlite_url = f"sqlite:///{args.db_path}"
    engine = create_engine(sqlite_url, echo=False)
    app.state.engine = engine
    
    # 创建所有表
    SQLModel.metadata.create_all(engine)
    
    logging.info(f"API服务启动在: http://{args.host}:{args.port}")
    logging.info(f"数据库路径: {args.db_path}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
