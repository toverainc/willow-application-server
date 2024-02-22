from logging import getLogger

from app.settings import get_settings


log = getLogger("WAS")
settings = get_settings()

force_openai_model = None

if settings.openai_api_key is not None:
    log.info("Initializing OpenAI Client")
    import openai
    try:
        openai_client = openai.OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        models = openai_client.models.list()
        if len(models.data) == 1:
            force_openai_model = models.data[0].id
            log.info(
                f"Only one model on OpenAI endpoint - forcing model '{force_openai_model}'")
    except Exception as e:
        log.error(f"failed to initialize OpenAI client: {e}")
else:
    openai_client = None


def openai_chat(text, model=settings.openai_model):
    log.info(f"OpenAI Chat request for text '{text}'")
    response = settings.command_not_found
    if force_openai_model is not None:
        log.info(f"Forcing model '{force_openai_model}'")
        model = force_openai_model
    else:
        log.info(f"Using model '{model}'")
    if openai_client is not None:
        try:
            chat_completion = openai_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": settings.openai_system_prompt,
                    },
                    {
                        "role": "user",
                        "content": text,
                    }
                ],
                model=model,
                temperature=settings.openai_temperature,
            )
            response = chat_completion.choices[0].message.content
            # Make it friendly for TTS and display output
            response = response.replace('\n', ' ').replace('\r', '').lstrip()
            log.info(f"Got OpenAI response '{response}'")
        except Exception as e:
            log.info(f"OpenAI failed with '{e}")
    return response
