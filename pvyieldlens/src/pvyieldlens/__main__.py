import json
import logging
import os
from pathlib import Path

import uvicorn


def main():
    level = os.getenv('PVYL_LOG_LEVEL', 'info')
    options = Path('/data/options.json')
    if os.getenv('SUPERVISOR_TOKEN') and options.exists():
        level = json.loads(options.read_text()).get('log_level', level)
    if level not in ('debug', 'info', 'warning', 'error'):
        raise ValueError('invalid_log_level')
    logging.basicConfig(level=level.upper(), format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    uvicorn.run('pvyieldlens.web:app_from_environment', factory=True, host='0.0.0.0', port=8099,
                proxy_headers=False, access_log=False, log_level=level)


if __name__ == '__main__':
    main()
