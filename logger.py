import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    filename=os.path.dirname(os.path.realpath(__file__)) + "/workLog.txt",
    filemode='w')
logger = logging.getLogger(__name__)
