from db_mgr import (
    ModelProvider,
    ModelCapability,
    ModelConfiguration,
)
import json
from pathlib import Path
from sqlmodel import Session, select
from sqlalchemy import Engine
from pydantic import BaseModel, Field
from typing import List, Dict
from pydantic_ai import Agent, BinaryContent, RunContext, PromptedOutput
# from pydantic_ai.usage import UsageLimits
from model_config_mgr import ModelConfigMgr, ModelUseInterface
from config import VLM_MODEL
import logging

logger = logging.getLogger()

class ModelCapabilityConfirm:
    """每种能力都需要一段测试程序来确认模型是否具备"""
    def __init__(self, engine: Engine, base_dir: str):
        self.engine = engine
        self.base_dir = base_dir
        self.model_config_mgr = ModelConfigMgr(engine)
        proxy = self.model_config_mgr.get_proxy_value()
        if proxy is not None and proxy.value is not None and proxy.value != "":
            self.system_proxy = proxy.value
        else:
            self.system_proxy = None

    def get_sorted_capability_names(self) -> List[str]:
        """
        返回排序的能力名枚举，供前端和“builtin模型是否该自动加载”使用
        # * 只返回ModelCapability的子集，也就是经过筛选的
        """
        return [
            ModelCapability.TEXT.value,
            ModelCapability.VISION.value,
            ModelCapability.TOOL_USE.value,
            ModelCapability.STRUCTURED_OUTPUT.value,
        ]

    async def confirm_model_capability_dict(self, config_id: int, save_config: bool = True) -> Dict[str, bool]:
        """
        测试并返回一个模型能力的字典
        """
        capability_dict = {}
        for capa in self.get_sorted_capability_names():
            capability_dict[capa] = await self.confirm(config_id, ModelCapability(capa))
        if save_config:
            with Session(self.engine) as session:
                model_config: ModelConfiguration = session.exec(select(ModelConfiguration).where(ModelConfiguration.id == config_id)).first()
                model_config.capabilities_json = [capa for capa in capability_dict if capability_dict[capa]]
                session.add(model_config)
                session.commit()
        return capability_dict

    async def confirm(self, config_id: int, capa: ModelCapability) -> bool:
        """
        确认模型是否具备指定能力
        """
        if capa == ModelCapability.TEXT:
            return await self.confirm_text_capability(config_id)
        elif capa == ModelCapability.VISION:
            return await self.confirm_vision_capability(config_id)
        elif capa == ModelCapability.TOOL_USE:
            return await self.confirm_tooluse_capability(config_id)
        elif capa == ModelCapability.STRUCTURED_OUTPUT:
            return await self.confirm_structured_output_capability(config_id)
        else:
            return False

    def _get_spec_model_config(self, config_id: int) -> ModelUseInterface:
        """
        获取指定模型的配置
        """
        with Session(self.engine) as session:
            model_config: ModelConfiguration = session.exec(select(ModelConfiguration).where(ModelConfiguration.id == config_id)).first()
            if model_config is None:
                return None
            model_provider: ModelProvider = session.exec(select(ModelProvider).where(ModelProvider.id == model_config.provider_id)).first()
            if model_provider is None:
                return None
            
            return ModelUseInterface(
                model_identifier=model_config.model_identifier,
                base_url=model_provider.base_url,
                api_key=model_provider.api_key if model_provider.api_key else "",
                use_proxy=model_provider.use_proxy,
                max_context_length=model_config.max_context_length,
                max_output_tokens=model_config.max_output_tokens,
            )
    
    async def confirm_text_capability(self, config_id: int) -> bool:
        """
        确认模型是否有文字处理能力
        """
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        model = self.model_config_mgr.model_adapter(model_interface)
        agent = Agent(
            model=model,
        )
        try:
            result = await agent.run(
                user_prompt="Hello, how are you?",
                # usage_limits=UsageLimits(output_tokens_limit=100),
            )
            if isinstance(result.output, str) and len(result.output) > 0:
                return True
            else:
                logger.warning(f"Unexpected output format for text capability: {result.output}")
                return False
        except Exception as e:
            logger.error(f"Error testing text capability: {e}")
            return False
    
    async def confirm_vision_capability(self, config_id: int) -> bool:
        """
        确认模型是否有视觉处理能力
        """
        # 确保使用绝对路径
        script_dir = Path(__file__).resolve().parent
        image_path = script_dir / "dog.png"
        
        if not image_path.exists():
            logger.warning(f"Warning: Test image not found at {image_path}")
            logger.info(f"Script directory: {script_dir}")
            logger.info(f"Current working directory: {Path.cwd()}")
            return False

        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        model = self.model_config_mgr.model_adapter(model_interface)
        agent = Agent(
            model=model,
        )
        try:
            result = await agent.run(user_prompt=
                [
                    'What is in this image?',
                    BinaryContent(data=image_path.read_bytes(), media_type='image/png'),
                ]
            )
            # logger.info(result.output)
            if 'dog' in result.output.lower():
                return True
            if 'puppy' in result.output.lower():
                return True
            return False
        except Exception as e:
            logger.error(f"Error testing vision capability: {e}")
            return False

    async def confirm_embedding_capability(self) -> bool:
        """
        确认向量化模型是否可用
        """
        try:
            from models_mgr import ModelsMgr
            model_mgr = ModelsMgr(engine=self.engine, base_dir=self.base_dir)
            text_embeds = model_mgr.get_embedding("I like reading")
            # logger.info(len(text_embeds))
            if text_embeds is not None and len(text_embeds) > 0:
                return True
            logger.warning(f"Unexpected embedding format: {text_embeds}")
            return False
        except Exception as e:
            logger.error(f"Error confirming embedding capability: {e}")
            return False

    async def confirm_tooluse_capability(self, config_id: int) -> bool:
        """
        确认模型是否有工具调用能力
        """
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        model = self.model_config_mgr.model_adapter(model_interface)
        agent = Agent(model=model)

        @agent.tool
        def get_current_weather(ctx: RunContext, location: str, unit: str = "celsius") -> str:
            """
            Get the current weather in a given location.
            Args:
                location (str): The name of the city and state, e.g. San Francisco, CA.
                unit (str): The unit of temperature (celsius or fahrenheit).
            """
            return f"The current weather in {location} is 20 degrees {unit}."

        try:
            await agent.run('What is the weather like in San Francisco?')
            return True
        except Exception as e:
            logger.error(f"Error testing tool use capability: {e}")
            return False
    
    async def confirm_structured_output_capability(self, config_id: int) -> bool:
        """
        确认模型是否有结构化数据处理能力
        """
        
        class CityLocation(BaseModel):
            city: str = Field(description="The name of the city")
            country: str = Field(description="The name of the country")

        model_interface = self._get_spec_model_config(config_id)
        model = self.model_config_mgr.model_adapter(model_interface)
        try:
            agent = Agent(
                model=model,
                # mlx_vlm加载模型使用 PromptedOutput 强制 prompt-based 模式，避免 tool calling
                output_type=PromptedOutput(CityLocation) if model_interface.model_identifier == VLM_MODEL else CityLocation,
            )
            result = await agent.run('Where were the olympics held in 2012?')
            # logger.info(f"Structured output result: {result}")
            if isinstance(result.output, CityLocation):
                return True
            return False
        except Exception as e:
            logger.error(f"Error testing structured output capability: {e}")
            return False

    def add_capability(self, config_id: int, capa: ModelCapability) -> bool:
        """
        给指定模型增加一项能力
        """
        with Session(self.engine) as session:
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
                logger.error(f"Error adding capability: {e}")
                return False

    def del_capability(self, config_id: int, capa: ModelCapability) -> bool:
        """
        删除指定模型的一项能力
        """
        with Session(self.engine) as session:
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
                logger.error(f"Error deleting capability: {e}")
                return False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # 输出到控制台
        ]
    )
    
    import asyncio

    from sqlmodel import create_engine
    from config import TEST_DB_PATH
    
    async def main():
        engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
        mgr = ModelCapabilityConfirm(engine, base_dir=Path(TEST_DB_PATH).parent)
        logger.info(await mgr.confirm_text_capability(1))
        logger.info(await mgr.confirm_tooluse_capability(1))
        logger.info(await mgr.confirm_structured_output_capability(1))
        logger.info(await mgr.confirm_vision_capability(1))

        # logger.info(await mgr.confirm_embedding_capability())

        # logger.info(await mgr.confirm_model_capability_dict(2, save_config=False))

    asyncio.run(main())
