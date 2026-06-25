import logging

# ==================== CONFIGURACIÓN DEL LOGGER ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Logger global para todo el proyecto
logger = logging.getLogger("Guaribe")
