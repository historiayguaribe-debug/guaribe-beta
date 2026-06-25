# utils/logger.py
import logging

# Configuración única del logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Logger global para todo el proyecto
logger = logging.getLogger("Guaribe")
