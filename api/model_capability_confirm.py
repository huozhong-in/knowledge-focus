from db_mgr import (
    ModelCapability,
    ModelConfiguration,
)
from sqlmodel import Session, select
import json
from typing import List

# 每种能力都需要一段测试程序来确认模型是否具备
class ModelCapabilityConfirm:
    def __init__(self, session: Session):
        self.session = session

    # 返回排序的能力名枚举，供前端使用
    def get_sorted_capability_names(self) -> List[str]:
        return [
            ModelCapability.TEXT.value,
            ModelCapability.REASONING.value,
            ModelCapability.VISION.value,
            ModelCapability.TOOL_USE.value,
            ModelCapability.WEB_SEARCH.value,
            ModelCapability.EMBEDDING.value,
            ModelCapability.RERANKER.value,
        ]

    def confirm(self, config_id: int, capa: ModelCapability) -> bool:
        """
        确认模型是否具备指定能力
        """
        with Session() as session:
            config: ModelConfiguration = session.exec(select(ModelConfiguration).where(ModelConfiguration.id == config_id)).first()
            if config is None:
                return False
            capabilities_json: List[str] = json.loads(config.capabilities_json)
            if capa.value in capabilities_json:
                # TODO 这里可以添加一些逻辑来确认模型是否具备该能力
                return True
            else:
                return False
    
    def add_capability(self, config_id: int, capa: ModelCapability) -> bool:
        """
        给指定模型增加能力
        """
        with Session() as session:
            config: ModelConfiguration = session.exec(select(ModelConfiguration).where(ModelConfiguration.id == config_id)).first()
            if config is None:
                return False
            try:
                capabilities_json: List[str] = json.loads(config.capabilities_json)
                if capa.value not in capabilities_json:
                    capabilities_json.append(capa.value)
                    config.capabilities_json = json.dumps(capabilities_json)
                    session.add(config)
                    session.commit()
                return True
            except Exception as e:
                print(f"Error adding capability: {e}")
                return False

    def del_capability(self, config_id: int, capa: ModelCapability) -> bool:
        """
        删除指定模型的能力
        """
        with Session() as session:
            config: ModelConfiguration = session.exec(select(ModelConfiguration).where(ModelConfiguration.id == config_id)).first()
            if config is None:
                return False
            try:
                capabilities_json: List[str] = json.loads(config.capabilities_json)
                if capa.value in capabilities_json:
                    capabilities_json.remove(capa.value)
                    config.capabilities_json = json.dumps(capabilities_json)
                    session.add(config)
                    session.commit()
                    return True
            except Exception as e:
                print(f"Error deleting capability: {e}")
                return False


if __name__ == "__main__":
    pass