from db_mgr import (
    ModelProvider,
    ModelCapability,
    ModelConfiguration,
    SystemConfig,
)
from sqlmodel import Session, select
import json
from typing import List
from openai import AsyncOpenAI
import httpx
from pydantic import BaseModel
import base64

class ModelUseInterface(BaseModel):
    model_identifier: str
    base_url: str
    api_key: str
    use_proxy: bool

# 每种能力都需要一段测试程序来确认模型是否具备
class ModelCapabilityConfirm:
    def __init__(self, session: Session):
        self.session = session
        self.system_proxy = self.session.exec(select(SystemConfig).where(SystemConfig.key == "proxy")).first()

    # 返回排序的能力名枚举，供前端使用
    def get_sorted_capability_names(self) -> List[str]:
        return [
            ModelCapability.TEXT.value,
            # ModelCapability.REASONING.value,
            ModelCapability.VISION.value,
            ModelCapability.TOOL_USE.value,
            # ModelCapability.WEB_SEARCH.value,
            ModelCapability.EMBEDDING.value,
            # ModelCapability.RERANKER.value,
        ]

    def confirm(self, config_id: int, capa: ModelCapability) -> bool:
        """
        确认模型是否具备指定能力
        """
        if capa == ModelCapability.TEXT:
            return self.confirm_text_capability(config_id)
        elif capa == ModelCapability.VISION:
            return self.confirm_vision_capability(config_id)
        elif capa == ModelCapability.TOOL_USE:
            return self.confirm_tooluse_capability(config_id)
        elif capa == ModelCapability.EMBEDDING:
            return self.confirm_embedding_capability(config_id)
        else:
            return False

    def _get_spec_model_config(self, config_id: int) -> ModelUseInterface:
        """
        获取指定模型的配置
        """
        with self.session as session:
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
            )
    
    async def confirm_text_capability(self, config_id: int) -> bool:
        """
        确认模型是否有文字处理能力
        # TODO 还要测一下结构化输出能力
        """
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        if model_interface.use_proxy == True:
            http_client = httpx.AsyncClient(proxy=self.system_proxy)
        else:
            http_client = httpx.AsyncClient()
        client = AsyncOpenAI(
            api_key=model_interface.api_key if model_interface.api_key else "",
            base_url=model_interface.base_url,
            max_retries=3,
            http_client=http_client,
        )
        try:
            await client.chat.completions.create(
                model=model_interface.model_identifier,
                messages=[
                    {"role": "user", "content": "Hello, world!"}
                ],
                max_tokens=30,
            )
            return True
        except Exception as e:
            print(f"Error testing text capability: {e}")
            return False
    
    async def confirm_vision_capability(self, config_id: int) -> bool:
        """
        确认模型是否有视觉处理能力
        """
        
        def encode_image(image_path):
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")

        base64_image = encode_image("dog.png")
        
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        if model_interface.use_proxy == True:
            http_client = httpx.AsyncClient(proxy=self.system_proxy)
        else:
            http_client = httpx.AsyncClient()
        client = AsyncOpenAI(
            api_key=model_interface.api_key if model_interface.api_key else "",
            base_url=model_interface.base_url,
            max_retries=3,
            http_client=http_client,
        )
        try:
            response = await client.chat.completions.create(
                model=model_interface.model_identifier,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "What is in this image?"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=100,
            )
            # print(response.choices[0].message.content)
            return True
        except Exception as e:
            print(f"Error testing vision capability: {e}")
            return False

    async def confirm_embedding_capability(self, config_id: int) -> bool:
        """
        确认模型是否有向量化能力
        """
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        if model_interface.use_proxy == True:
            http_client = httpx.AsyncClient(proxy=self.system_proxy)
        else:
            http_client = httpx.AsyncClient()
        client = AsyncOpenAI(
            api_key=model_interface.api_key if model_interface.api_key else "",
            base_url=model_interface.base_url,
            max_retries=3,
            http_client=http_client,
        )
        try:
            response = await client.embeddings.create(
                model=model_interface.model_identifier,
                input="Hello, world!",
            )
            # print(len(response.data[0].embedding))
            return True
        except Exception as e:
            print(f"Error testing embedding capability: {e}")
            return False

    async def confirm_tooluse_capability(self, config_id: int) -> bool:
        """
        确认模型是否有工具调用能力
        """
        model_interface = self._get_spec_model_config(config_id)
        if model_interface is None:
            return False
        if model_interface.use_proxy == True:
            http_client = httpx.AsyncClient(proxy=self.system_proxy)
        else:
            http_client = httpx.AsyncClient()
        client = AsyncOpenAI(
            api_key=model_interface.api_key if model_interface.api_key else "",
            base_url=model_interface.base_url,
            max_retries=3,
            http_client=http_client,
        )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                        },
                        "required": ["location"],
                    },
                },
            }
        ]
        try:
            response_message = await client.chat.completions.create(
                model=model_interface.model_identifier,
                messages=[
                    {
                        "role": "user",
                        "content": "What is the weather like in San Francisco?",
                    }
                ],
                tools=tools,
                tool_choice="required",
            )
            # if response_message.choices[0].message.tool_calls:
            #     for tool_call in response_message.choices[0].message.tool_calls:
            #         function_name = tool_call.function.name
            #         arguments = tool_call.function.arguments
            #         print(f"Tool call: {function_name} with arguments {arguments}")
            return True
        except Exception as e:
            print(f"Error testing tool use capability: {e}")
            return False

    def add_capability(self, config_id: int, capa: ModelCapability) -> bool:
        """
        给指定模型增加一项能力
        """
        with self.session as session:
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
        删除指定模型的一项能力
        """
        with self.session as session:
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
    import asyncio

    from sqlmodel import create_engine
    from config import TEST_DB_PATH
    
    async def main():
        engine = create_engine(f'sqlite:///{TEST_DB_PATH}')
        with Session(engine) as session:
            mgr = ModelCapabilityConfirm(session)
            print(await mgr.confirm_text_capability(40))
            print(await mgr.confirm_tooluse_capability(40))
            print(await mgr.confirm_vision_capability(40))
            print(await mgr.confirm_embedding_capability(39))

    asyncio.run(main())
