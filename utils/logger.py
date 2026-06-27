import logging
import sys

# Configuración del logger con flush inmediato
class InmediateStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        InmediateStreamHandler(stream=sys.stdout)
    ]
)

logger = logging.getLogger("Guaribe")
