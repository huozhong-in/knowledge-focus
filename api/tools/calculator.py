
"""
计算器工具 - 简单的通用工具示例

这是 AGENT_DEV_PLAN.md 阶段2任务3 要求的测试工具
"""

from typing import Union

def calculator_add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的和
    
    Args:
        a: 第一个数
        b: 第二个数
        
    Returns:
        两数之和
    """
    return a + b

def calculator_multiply(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的乘积
    
    Args:
        a: 第一个数
        b: 第二个数
        
    Returns:
        两数之积
    """
    return a * b

def calculator_subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的差
    
    Args:
        a: 被减数
        b: 减数
        
    Returns:
        差值
    """
    return a - b

def calculator_divide(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的商
    
    Args:
        a: 被除数
        b: 除数
        
    Returns:
        商值
        
    Raises:
        ValueError: 当除数为0时
    """
    if b == 0:
        raise ValueError("除数不能为0")
    return a / b

def calculator_power(base: Union[int, float], exponent: Union[int, float]) -> Union[int, float]:
    """
    计算幂运算
    
    Args:
        base: 底数
        exponent: 指数
        
    Returns:
        幂运算结果
    """
    return base ** exponent

def calculator_sqrt(x: Union[int, float]) -> float:
    """
    计算平方根
    
    Args:
        x: 被开方数
        
    Returns:
        平方根
        
    Raises:
        ValueError: 当输入为负数时
    """
    if x < 0:
        raise ValueError("不能计算负数的平方根")
    return x ** 0.5

def calculator_bmi(weight: float, height: float) -> float:
    """
    Calculate Body Mass Index (BMI).
    Args:
        weight: Weight in kilograms.
        height: Height in meters.
    """
    if height <= 0:
        raise ValueError("Height must be positive.")
    return weight / (height ** 2)


if __name__ == "__main__":
    # 测试计算器功能
    print("=== 计算器工具测试 ===")
    print(f"加法: 3 + 5 = {calculator_add(3, 5)}")
    print(f"减法: 10 - 3 = {calculator_subtract(10, 3)}")
    print(f"乘法: 4 * 6 = {calculator_multiply(4, 6)}")
    print(f"除法: 15 / 3 = {calculator_divide(15, 3)}")
    print(f"幂运算: 2^3 = {calculator_power(2, 3)}")
    print(f"平方根: √16 = {calculator_sqrt(16)}")
    print(f"BMI: 70kg, 1.75m = {calculator_bmi(70, 1.75):.2f}")
    print("所有测试通过！")
