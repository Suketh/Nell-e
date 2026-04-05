from llm.ollama_client import OllamaClient
def describe_image(ollama: OllamaClient, image_path: str):
    return ollama.vision(image_path, prompt="Beskriv bilden och ge 3 insikter.")
