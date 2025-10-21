"""
测试 FastAPI 依赖注入中的单例行为
"""
from functools import wraps

def singleton(cls):
    """单例装饰器"""
    instances = {}
    
    @wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance

@singleton
class MyManager:
    def __init__(self):
        self.counter = 0
        print(f"MyManager.__init__ called, id={id(self)}")
    
    def increment(self):
        self.counter += 1
        return self.counter

# 测试 1: 直接调用类（看起来像创建新实例）
print("\n=== 测试 1: 直接调用 MyManager() ===")
m1 = MyManager()
print(f"m1.increment() = {m1.increment()}")
print(f"m1.increment() = {m1.increment()}")
print(f"m1 id = {id(m1)}")

m2 = MyManager()
print(f"m2.increment() = {m2.increment()}")  # 应该是 3，因为共享状态
print(f"m2 id = {id(m2)}")
print(f"m1 is m2? {m1 is m2}")

# 测试 2: 通过辅助函数返回
print("\n=== 测试 2: 通过函数返回 ===")
def get_manager_v1():
    """方式 1: 看起来像创建新实例"""
    return MyManager()

def get_manager_v2():
    """方式 2: 显式返回（但其实一样）"""
    return MyManager()

m3 = get_manager_v1()
print(f"m3.increment() = {m3.increment()}")  # 应该是 4
print(f"m3 id = {id(m3)}")
print(f"m1 is m3? {m1 is m3}")

m4 = get_manager_v2()
print(f"m4.increment() = {m4.increment()}")  # 应该是 5
print(f"m4 id = {id(m4)}")
print(f"m1 is m4? {m1 is m4}")

print("\n=== 结论 ===")
print(f"所有对象的 id 相同: {id(m1) == id(m2) == id(m3) == id(m4)}")
print(f"counter 的最终值: {m1.counter}")
print("\n👉 关键点: @singleton 装饰器让 MyManager() 变成了 get_instance() 的调用")
print("   无论你写 MyManager() 还是在函数里 return MyManager()")
print("   都会执行 get_instance() 函数，返回同一个实例！")
