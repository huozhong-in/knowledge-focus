
def bmi(weight: float, height: float) -> float:
    """
    Calculate Body Mass Index (BMI).
    """
    if height <= 0:
        raise ValueError("Height must be positive.")
    return weight / (height ** 2)
