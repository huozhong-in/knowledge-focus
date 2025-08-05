from sqlmodel import Session, create_engine
from typing import Dict, Any
from sqlmodel import Session, select
from db_mgr import (
    FileScreeningResult, FileScreenResult, 
    Task, TaskType, TaskStatus, TaskResult
)
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

class RefineManager:
    """"""
    
    def __init__(self, session: Session):
        self.session = session


# 测试用代码
if __name__ == "__main__":
    from config import TEST_DB_PATH
    session = Session(create_engine(f'sqlite:///{TEST_DB_PATH}'))
