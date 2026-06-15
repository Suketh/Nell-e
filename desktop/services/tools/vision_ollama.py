from llm.ollama_client import OllamaClient
def describe_image(ollama: OllamaClient, image_path: str):
    return ollama.vision(image_path, prompt="Give 3 insights about this image.")
