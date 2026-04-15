import logging
import signal
import sys
import time

from app.config import settings
from app.db import Base, engine
from app.services.scheduler_service import start_scheduler
from app.services.post_deploy_sync_service import PostDeploySyncService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

scheduler_started = False
post_deploy_sync_ran = False
keep_running = True


def handle_shutdown(signum, frame):
    global keep_running
    logger.info("🛑 Sinal de encerramento recebido. Finalizando worker...")
    keep_running = False


def safe_run_post_deploy_sync() -> None:
    global post_deploy_sync_ran

    if post_deploy_sync_ran:
        logger.info("⏭️ Pós-deploy sync já executado nesta instância. Ignorando.")
        return

    try:
        logger.info("🔄 Executando sincronização pós-deploy no worker...")
        service = PostDeploySyncService()
        service.run_once()
        post_deploy_sync_ran = True
        logger.info("✅ Sincronização pós-deploy concluída")
    except Exception as e:
        logger.exception("❌ Erro na sincronização pós-deploy: %s", e)


def safe_start_scheduler() -> None:
    global scheduler_started

    if scheduler_started:
        logger.info("⏭️ Scheduler já havia sido iniciado. Ignorando nova inicialização.")
        return

    try:
        start_scheduler()
        scheduler_started = True
        logger.info("⏰ Scheduler iniciado com sucesso")
    except Exception as e:
        logger.exception("❌ Erro ao iniciar scheduler: %s", e)
        raise


def main():
    logger.info("🚀 Iniciando worker...")
    logger.info("📊 Ambiente: %s", settings.app_env)

    # garante tabelas
    Base.metadata.create_all(bind=engine)

    # registra sinais de encerramento
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # roda sync uma vez
    safe_run_post_deploy_sync()

    # inicia scheduler
    safe_start_scheduler()

    logger.info("🟢 Worker em execução.")

    while keep_running:
        time.sleep(5)

    logger.info("🔴 Worker finalizado.")
    sys.exit(0)


if __name__ == "__main__":
    main()